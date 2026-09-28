"""Seoul Blind Trip — pick a mood, we hide the destinations, you follow the map.

Run:  streamlit run app.py        (from this folder, so .streamlit/config.toml applies)
Env:  NVIDIA_API_KEY (build.nvidia.com) enables Nemotron scoring + multilingual hints.
"""

import datetime as dt
import math
import urllib.parse

import pandas as pd
import pydeck as pdk
import streamlit as st

import llm
import ui
from planner import (START_POINTS, THEMES, cuopt_available, load_pois,
                     min_to_hhmm, plan_trip, tag_scores)

LANGS = ["English", "日本語", "简体中文", "Español", "Français", "한국어"]
MODE_ICON = {"walk": "🚶", "subway": "🚇"}
KIND_BADGE = {"restaurant": "🍽️ Meal stop", "cafe": "☕ Café break", "activity": "🎟️ Activity"}

st.set_page_config(page_title="Seoul Blind Trip", page_icon="🙈", layout="wide")
st.html(ui.CSS)

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
        map_provider="carto", map_style="light",
        initial_view_state=view,
        layers=[
            pdk.Layer("PathLayer", path, get_path="path", get_color=[26, 58, 58], width_min_pixels=4),
            pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color=[255, 77, 139],
                      get_line_color=[255, 255, 255], stroked=True, line_width_min_pixels=3,
                      radius_min_pixels=8, pickable=True),
        ],
        tooltip={"text": "{label}"},
    ))


def badge(stop):
    kind = stop.poi.get("kind")
    if kind in KIND_BADGE:
        return KIND_BADGE[kind]
    return "🍽️ Food stop" if stop.group == "food" else ""


def reset():
    for k in ("plan", "texts", "teaser", "step", "revealed", "meta"):
        ss.pop(k, None)


# ---------- sidebar ----------

with st.sidebar:
    st.html('<p class="bt-label">Engine</p>')
    st.markdown(f"**Nemotron (build.nvidia.com):** {'🟢 connected' if llm.available() else '⚪ no API key'}")
    st.markdown(f"**cuOpt (GPU):** {'🟢 available' if cuopt_available() else '⚪ not installed — CPU exact DP'}")
    backend = st.radio("Route solver", ["auto", "cuopt", "cpu"], horizontal=True,
                       help="auto = cuOpt if installed, otherwise CPU exact DP")
    judge = st.toggle("🔍 Judge mode (shows spoilers)")
    if "plan" in ss and st.button("↺ New trip", width="stretch"):
        reset()
        st.rerun()


# ---------- setup ----------

if "plan" not in ss:
    st.html(ui.width_css(1120))
    st.html(ui.hero())

    with st.container(key="planner"):
        st.html('<p class="bt-label">Choose your mood</p>')
        theme = st.pills("Choose your mood", list(THEMES), format_func=lambda k: THEMES[k][0],
                         default="calm", selection_mode="single", label_visibility="collapsed") or "calm"
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
        max_stops = st.slider("Max secret stops", 3, 7, 5)

        st.html('<p class="bt-label" style="margin-top:8px">Add to my route</p>'
                '<p class="bt-caption" style="margin:-8px 0 4px">The optimizer picks the spot that fits your path and timing.</p>')
        a1, a2 = st.columns(2)
        foodie = theme == "food"
        want_food = a1.toggle("🍽️ A meal or café stop", value=False, disabled=foodie,
                              help="Trips over lunch or dinner get a restaurant at meal time; "
                                   "otherwise a café break. (Foodie Trip is all food already.)")
        want_act = a2.toggle("🎟️ An activity", value=False,
                             help="City tour bus, river cruise, hanbok rental, cable car, karaoke…")
        addons = [k for k, on in (("food", want_food and not foodie), ("activity", want_act)) if on]

        if st.button("🎲 Start my blind trip", type="primary", width="stretch"):
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
                plan = plan_trip(pois, scores, start, start_min, hours, day.weekday(), max_stops,
                                 backend, addons=addons, foodie=foodie)
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

    st.html(ui.how_it_works())
    st.html(ui.footer())
    st.stop()


# ---------- trip ----------

st.html(ui.width_css(760))
plan, i = ss.plan, ss.step
n = len(plan.stops)
points = [plan.start_point] + [(s.poi["lat"], s.poi["lng"]) for s in plan.stops]

st.html(f'<p class="bt-label">Seoul · Blind Trip · from {ui.text(plan.start_name)}</p>'
        f'<h1 class="bt-display-md">Your secret route</h1>'
        f'<div class="bt-band" style="margin-top:24px"><p class="bt-title-md">✨ '
        f'{ui.text(ss.teaser or f"{n} secret stops are waiting for you. Trust the map.")}</p></div>')
m1, m2, m3 = st.columns(3)
m1.metric("Secret stops", n)
m2.metric("Trip length", f"{(plan.end_min - plan.start_min) / 60:.1f} h")
m3.metric("Back by", min_to_hhmm(plan.end_min))
if plan.note:
    st.caption(f"ℹ️ {plan.note}")

if i >= n:
    st.balloons()
    rows = "".join(
        f'<p class="bt-body" style="margin:10px 0"><b>{k}. {ui.text(s.poi["name_en"])}</b> '
        f'<span style="font-family:\'Noto Sans KR\',sans-serif">{ui.text(s.poi["name_ko"])}</span> · '
        f'{min_to_hhmm(s.arrive)}–{min_to_hhmm(s.depart)} {ui.pills([badge(s)])}</p>'
        for k, s in enumerate(plan.stops, 1))
    st.html(f'<div class="bt-band"><p class="bt-label">Trip complete</p>'
            f'<h2 class="bt-display-sm">Here’s where you went 🎉</h2>{rows}</div>')
    route_map(points, ["Start"] + [s.poi["name_en"] for s in plan.stops])
    if st.button("Plan another blind trip", type="primary", width="stretch"):
        reset()
        st.rerun()
else:
    stop = plan.stops[i]
    here = points[i + 1]
    st.progress(i / n, text=f"Stop {i + 1} of {n}")

    if not ss.revealed:
        color = ui.CARD_COLORS[i % len(ui.CARD_COLORS)]
        tone = "on-dark" if color in ui.DARK_CARDS else "on-light"
        wait = f" · opens {stop.poi['open']}" if stop.wait else ""
        with st.container(key=f"stop-{color}"):
            st.html(
                f'<p class="bt-label" style="color:inherit;opacity:.75">Secret stop {i + 1} of {n}</p>'
                + ui.pills([badge(stop),
                            f"{MODE_ICON[stop.mode]} ~{stop.travel_min} min by {stop.mode}",
                            f"arrive ≈ {min_to_hhmm(stop.arrive)}{wait}",
                            f"stay ≈ {stop.poi['stay']} min"], tone)
                + f'<p class="bt-hint">🔒 “{ui.text(text_for(stop, "hint"))}”</p>')
            c1, c2 = st.columns(2)
            c1.link_button("🧭 Google Maps", gmaps_link(points[i], here), width="stretch")
            c2.link_button("🗺️ Kakao Map", kakao_link(f"Secret Stop {i + 1}", here), width="stretch")
            if st.button("📍 I've arrived — reveal!", type="primary", width="stretch"):
                ss.revealed = True
                st.rerun()
    else:
        with st.container(key="reveal"):
            st.html(
                f'<p class="bt-label">You found it · stop {i + 1} of {n}</p>'
                f'<h2 class="bt-display-md">{ui.text(stop.poi["name_en"])}</h2>'
                f'<p class="bt-ko">{ui.text(stop.poi["name_ko"])}</p>'
                f'<p class="bt-caption">Show this to locals if you need directions</p>'
                f'<p class="bt-body" style="margin-top:20px">{ui.text(text_for(stop, "reveal"))}</p>'
                f'<div class="bt-frag" style="background:var(--canvas)">💡 {ui.text(text_for(stop, "tip"))}</div>')
            label = "Next secret stop →" if i + 1 < n else "Finish trip 🎉"
            if st.button(label, type="primary", width="stretch"):
                ss.step += 1
                ss.revealed = False
                st.rerun()

    found = i + (1 if ss.revealed else 0)
    if found:
        with st.expander(f"🗺️ Your journey so far ({found} found)"):
            route_map(points[:found + 1], ["Start"] + [s.poi["name_en"] for s in plan.stops[:found]])


# ---------- judge mode ----------

if judge:
    with st.container(key="judge"):
        meta = ss.meta
        st.html('<p class="bt-label">Judge mode · spoilers</p><h2 class="bt-display-sm">Under the hood</h2>')
        st.markdown(f"- **Mood:** {meta['mood']}\n- **Place scoring:** {meta['source']}\n"
                    f"- **Route solver:** {plan.backend} · {plan.solve_ms:.0f} ms over "
                    f"{len(plan.candidates)} candidates\n- **Clues:** "
                    f"{'Nemotron · ' + meta['lang'] if ss.texts else 'curated English'}")
        if plan.note:
            st.warning(plan.note)
        st.dataframe(pd.DataFrame([
            {"stop": k, "place": s.poi["name_en"], "type": badge(s), "score": s.score, "mode": s.mode,
             "travel": s.travel_min, "arrive": min_to_hhmm(s.arrive), "leave": min_to_hhmm(s.depart)}
            for k, s in enumerate(plan.stops, 1)
        ]), hide_index=True, width="stretch")
        chosen = {s.poi["id"] for s in plan.stops}
        st.caption("Candidates considered (theme score ≥ 4 or requested add-on, open, reachable)")
        st.dataframe(pd.DataFrame([
            {"place": c.poi["name_en"], "group": c.group or "", "score": c.score,
             "picked": "✅" if c.poi["id"] in chosen else ""}
            for c in plan.candidates
        ]), hide_index=True, width="stretch")

st.html(ui.footer())
