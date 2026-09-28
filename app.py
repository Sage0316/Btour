"""Seoul Blind Trip — pick a mood, we hide the destinations, you follow the map.

Run:  streamlit run app.py
Env:  NVIDIA_API_KEY (build.nvidia.com) enables Nemotron scoring + multilingual hints.
"""

import datetime as dt
import math
import urllib.parse

import pandas as pd
import pydeck as pdk
import streamlit as st

import llm
from planner import (START_POINTS, THEMES, cuopt_available, load_pois,
                     min_to_hhmm, plan_trip, tag_scores)

LANGS = ["English", "日本語", "简体中文", "Español", "Français", "한국어"]
MODE_ICON = {"walk": "🚶", "subway": "🚇"}

st.set_page_config(page_title="Seoul Blind Trip", page_icon="🙈", layout="centered")
st.markdown("""
<style>
.hint {font-size: 1.35rem; line-height: 1.5; padding: 1.1rem 1.3rem; border-radius: 14px;
       background: rgba(118, 185, 0, 0.12); border-left: 6px solid #76b900; margin: .6rem 0 1rem;}
.ko {font-size: 2.4rem !important; font-weight: 800; line-height: 1.2; margin: .2rem 0;}
.small {opacity: .7; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)

ss = st.session_state
pois = load_pois()


# ---------- helpers ----------

def gmaps_link(a, b):
    q = {"api": 1, "origin": f"{a[0]},{a[1]}", "destination": f"{b[0]},{b[1]}", "travelmode": "transit"}
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(q)


def kakao_link(label, b):
    return f"https://map.kakao.com/link/to/{urllib.parse.quote(label)},{b[0]},{b[1]}"


def text_for(stop, field):
    item = ss.texts.get(stop.poi["id"], {})
    return item.get(field) or stop.poi[field]


def route_map(points, labels):
    df = pd.DataFrame({"lat": [p[0] for p in points], "lon": [p[1] for p in points], "label": labels})
    path = pd.DataFrame({"path": [[[p[1], p[0]] for p in points]]})
    span = max(df.lat.max() - df.lat.min(), df.lon.max() - df.lon.min(), 0.01)
    zoom = min(14, math.log2(360 / span) - 1.3)
    view = pdk.ViewState(latitude=df.lat.mean(), longitude=df.lon.mean(), zoom=zoom)
    st.pydeck_chart(pdk.Deck(
        initial_view_state=view,
        layers=[
            pdk.Layer("PathLayer", path, get_path="path", get_color=[118, 185, 0], width_min_pixels=4),
            pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color=[255, 255, 255],
                      get_line_color=[118, 185, 0], stroked=True, line_width_min_pixels=3,
                      radius_min_pixels=7, pickable=True),
        ],
        tooltip={"text": "{label}"},
    ))


def reset():
    for k in ("plan", "texts", "teaser", "step", "revealed", "meta"):
        ss.pop(k, None)


# ---------- sidebar ----------

with st.sidebar:
    st.header("⚙️ Engine")
    st.markdown(f"**Nemotron (build.nvidia.com):** {'🟢 connected' if llm.available() else '⚪ no API key'}")
    st.markdown(f"**cuOpt (GPU):** {'🟢 available' if cuopt_available() else '⚪ not installed — CPU exact DP'}")
    backend = st.radio("Route solver", ["auto", "cuopt", "cpu"], horizontal=True,
                       help="auto = cuOpt if installed, otherwise CPU exact DP")
    judge = st.toggle("🔍 Judge mode (shows spoilers)")
    if "plan" in ss and st.button("↺ New trip"):
        reset()
        st.rerun()

st.title("🙈 Seoul Blind Trip")
st.caption("Pick a mood. We hide the destinations. You just follow the map.")


# ---------- setup ----------

if "plan" not in ss:
    theme = st.pills("Choose your mood", list(THEMES), format_func=lambda k: THEMES[k][0],
                     default="calm", selection_mode="single") or "calm"
    custom = st.text_input("…or describe your own mood (Nemotron reads it)",
                           placeholder="e.g. rainy day, travelling solo, I love tea and old books")
    c1, c2 = st.columns(2)
    start = c1.selectbox("Where are you staying?", list(START_POINTS))
    lang = c2.selectbox("Clue language", LANGS)
    c3, c4, c5 = st.columns(3)
    day = c3.date_input("Date", dt.date.today())
    default_t = dt.time(18, 0) if theme == "night" else dt.time(10, 0)
    t0 = c4.time_input("Start time", default_t, step=dt.timedelta(minutes=30))
    hours = c5.slider("Hours", 3, 10, 6)
    max_stops = st.slider("Max secret stops", 3, 6, 5)

    if st.button("🎲 Start my blind trip", type="primary", use_container_width=True):
        mood = custom.strip() or THEMES[theme][0]
        with st.status("Planning your secret route…", expanded=True) as status:
            scores, source = tag_scores(pois, theme), "theme tags"
            if llm.available():
                st.write(f"🧠 Nemotron is reading {len(pois)} places for “{mood}”…")
                try:
                    s = llm.score_places(mood, pois)
                    if s:
                        scores, source = s, f"Nemotron · {llm.last_model_used}"
                except Exception as e:
                    st.write(f"⚠️ Nemotron unavailable, using theme tags ({e})")
            elif custom.strip():
                st.write("⚠️ Custom moods need NVIDIA_API_KEY — using the selected theme instead.")

            st.write("🧮 Solving orienteering with time windows (opening hours, stay time, budget)…")
            start_min = t0.hour * 60 + t0.minute
            plan = plan_trip(pois, scores, start, start_min, hours, day.weekday(), max_stops, backend)
            if not plan.stops:
                status.update(label="No route fits", state="error")
                st.error("Nothing fits this time window. Try a longer trip or a different start time.")
                st.stop()

            texts, teaser = {}, None
            if llm.available():
                st.write(f"✍️ Writing spoiler-free clues in {lang}…")
                try:
                    texts, teaser = llm.write_hints(plan.stops, lang, mood)
                    texts = texts or {}
                except Exception as e:
                    st.write(f"⚠️ Using curated English clues ({e})")
            status.update(label="Your secret route is ready!", state="complete")

        ss.update(plan=plan, texts=texts, teaser=teaser, step=0, revealed=False,
                  meta={"mood": mood, "source": source, "lang": lang, "scores": scores})
        st.rerun()
    st.stop()


# ---------- trip ----------

plan, i = ss.plan, ss.step
n = len(plan.stops)
points = [plan.start_point] + [(s.poi["lat"], s.poi["lng"]) for s in plan.stops]

st.info(ss.teaser or f"✨ {n} secret stops are waiting for you. Trust the map.")
m1, m2, m3 = st.columns(3)
m1.metric("Secret stops", n)
m2.metric("Trip length", f"{(plan.end_min - plan.start_min) / 60:.1f} h")
m3.metric("Back by", min_to_hhmm(plan.end_min))

if i >= n:
    st.balloons()
    st.subheader("🎉 Trip complete! Here's where you went")
    for k, s in enumerate(plan.stops, 1):
        st.markdown(f"**{k}. {s.poi['name_en']}** ({s.poi['name_ko']}) · "
                    f"{min_to_hhmm(s.arrive)}–{min_to_hhmm(s.depart)}")
    route_map(points, ["Start"] + [s.poi["name_en"] for s in plan.stops])
    if st.button("Plan another blind trip", type="primary"):
        reset()
        st.rerun()
    st.stop()

stop = plan.stops[i]
here = points[i + 1]
st.progress(i / n, text=f"Stop {i + 1} of {n}")

if not ss.revealed:
    st.subheader(f"🔒 Secret Stop {i + 1}")
    wait = f" · opens {stop.poi['open']}" if stop.wait else ""
    st.markdown(f"{MODE_ICON[stop.mode]} **~{stop.travel_min} min by {stop.mode}** · "
                f"arrive ≈ {min_to_hhmm(stop.arrive)}{wait} · stay ≈ {stop.poi['stay']} min")
    st.markdown(f'<div class="hint">“{text_for(stop, "hint")}”</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.link_button("🧭 Navigate · Google Maps", gmaps_link(points[i], here), use_container_width=True)
    c2.link_button("🗺️ Navigate · Kakao Map", kakao_link(f"Secret Stop {i + 1}", here),
                   use_container_width=True)
    if st.button("📍 I've arrived — reveal!", type="primary", use_container_width=True):
        ss.revealed = True
        st.rerun()
else:
    st.subheader(f"🎉 You found it: {stop.poi['name_en']}")
    st.markdown(f'<div class="ko">{stop.poi["name_ko"]}</div>'
                f'<p class="small">Show this to locals if you need directions</p>', unsafe_allow_html=True)
    st.write(text_for(stop, "reveal"))
    st.success(f"💡 {text_for(stop, 'tip')}")
    label = "Next secret stop →" if i + 1 < n else "Finish trip 🎉"
    if st.button(label, type="primary", use_container_width=True):
        ss.step += 1
        ss.revealed = False
        st.rerun()

found = i + (1 if ss.revealed else 0)
if found:
    with st.expander(f"🗺️ Your journey so far ({found} found)"):
        route_map(points[:found + 1], ["Start"] + [s.poi["name_en"] for s in plan.stops[:found]])


# ---------- judge mode ----------

if judge:
    st.divider()
    st.subheader("🔍 Under the hood")
    meta = ss.meta
    st.markdown(f"- **Mood:** {meta['mood']}\n- **Place scoring:** {meta['source']}\n"
                f"- **Route solver:** {plan.backend} · {plan.solve_ms:.0f} ms over "
                f"{len(plan.candidates)} candidates\n- **Clues:** "
                f"{'Nemotron · ' + meta['lang'] if ss.texts else 'curated English'}")
    if plan.note:
        st.warning(plan.note)
    st.dataframe(pd.DataFrame([
        {"stop": k, "place": s.poi["name_en"], "score": s.score, "mode": s.mode,
         "travel": s.travel_min, "arrive": min_to_hhmm(s.arrive), "leave": min_to_hhmm(s.depart)}
        for k, s in enumerate(plan.stops, 1)
    ]), hide_index=True, use_container_width=True)
    chosen = {s.poi["id"] for s in plan.stops}
    st.caption("Candidates considered (theme score ≥ 4, open, reachable)")
    st.dataframe(pd.DataFrame([
        {"place": p["name_en"], "score": sc, "picked": "✅" if p["id"] in chosen else ""}
        for p, sc in plan.candidates
    ]), hide_index=True, use_container_width=True)
