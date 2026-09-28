"""Seoul Blind Trip — pick a mood, we hide the destinations, you follow the map.

Run:  streamlit run app.py        (from this folder, so .streamlit/config.toml applies)
Env:  NVIDIA_API_KEY (build.nvidia.com) enables Nemotron scoring + multilingual hints.
"""

import datetime as dt
import math
import os
import urllib.parse

import pandas as pd
import pydeck as pdk
import streamlit as st

from pathlib import Path

# Load NVIDIA_API_KEY from a local .env (git-ignored) so the key is typed only once.
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

import llm  # noqa: E402  (reads NVIDIA_API_KEY)
import ui  # noqa: E402
import weather  # noqa: E402
from planner import (START_POINTS, THEMES, cuopt_available, haversine_km, load_pois,
                     min_to_hhmm, plan_race, plan_trip, tag_scores)

LANGS = ["English", "日本語", "简体中文", "Español", "Français", "한국어"]
MODE_ICON = {"walk": "🚶", "subway": "🚇"}
KIND_BADGE = {"restaurant": "🍽️ Meal stop", "cafe": "☕ Café break", "activity": "🎟️ Activity"}
TEAMS = {"A": "🔴 Team A", "B": "🔵 Team B"}
TEAM_STATE = ("plan", "step", "revealed", "peek", "mission", "photos", "replan_msg", "stage")
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
WALKABLE_KM = 0.8   # closer than this, skip "get to the area" and go straight to the walking clue

st.set_page_config(page_title="Seoul Blind Trip", page_icon="🙈", layout="wide")
st.html(ui.CSS)

ss = st.session_state
pois = load_pois()


# ---------- helpers ----------

def gmaps_link(b):
    """Google Maps directions from the phone's current location (no origin), by transit.

    Coordinates only, so the place name isn't spelled out; Korea supports transit directions.
    """
    q = {"api": 1, "destination": f"{b[0]},{b[1]}", "travelmode": "transit"}
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(q)


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
    if stop.group == "meet":
        return "🏁 Meeting point"
    kind = stop.poi.get("kind")
    if kind in KIND_BADGE:
        return KIND_BADGE[kind]
    return "🍽️ Food stop" if stop.group == "food" else ""


def easy_clue(stop, from_pt):
    kind, tags = stop.poi.get("kind"), stop.poi["tags"]
    cat = {"restaurant": "a place to eat", "cafe": "a café", "market": "a market",
           "activity": "an activity"}.get(kind)
    if not cat:
        for tag, label in (("traditional", "a historic spot"), ("nature", "an outdoor green space"),
                           ("shopping", "a shopping area"), ("night", "a night-view spot"),
                           ("landmark", "a famous landmark")):
            if tag in tags:
                cat = label
                break
    km = haversine_km(from_pt, (stop.poi["lat"], stop.poi["lng"]))
    inside = ", mostly indoors" if "indoor" in tags else ""
    drama = " You may have seen it in a K-drama." if stop.poi.get("dramas") else ""
    return f"Extra clue: it's {cat or 'a local favorite'}, about {km:.1f} km away{inside}.{drama}"


def compass_clue(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    k = int(((math.degrees(math.atan2(x, y)) + 360) % 360 + 22.5) // 45) % 8
    metres = max(50, round(haversine_km(a, b) * 1000 / 50) * 50)
    return f"{ARROWS[k]} Walk about {metres} m {COMPASS[k]}."


def approach(stop, from_pt):
    """Where Google Maps drops the traveler first: a nearby station (with a hand-written
    walking clue) or a spot ~200 m short of the place. None when it's walkable already."""
    here = (stop.poi["lat"], stop.poi["lng"])
    d = haversine_km(from_pt, here)
    if d < WALKABLE_KM:
        return None
    ap = stop.poi.get("approach")
    if ap:
        return {"pt": (ap["lat"], ap["lng"]), "label": ap["station"], "clue": ap["clue"]}
    f = 0.2 / d
    drop = (here[0] + (from_pt[0] - here[0]) * f, here[1] + (from_pt[1] - here[1]) * f)
    return {"pt": drop, "label": "a spot about 200 m away", "clue": None}


def mission_for(poi):
    """Spoiler-free photo mission: category level only, never the place itself."""
    kind, tags = poi.get("kind"), poi["tags"]
    by_kind = {"restaurant": "Snap your dish before you dig in.",
               "cafe": "Snap your drink or pastry.",
               "market": "Snap a food stall or something sizzling.",
               "activity": "Snap the activity in action: your ride, your view or your outfit."}
    if kind in by_kind:
        return by_kind[kind]
    for tag, text in (("traditional", "Snap something traditional: a tiled roof, a gate or a lantern."),
                      ("nature", "Snap something green or blue: trees, grass or water."),
                      ("night", "Snap the lights around you."),
                      ("shopping", "Snap a shop sign or a window display."),
                      ("landmark", "Snap the landmark you think you've found.")):
        if tag in tags:
            return text
    return "Snap something that proves you made it."


def replan(i, delay):
    """Re-optimize the remaining stops from the last place the traveler left."""
    plan, meta = ss.plan, ss.meta
    done = plan.stops[:i]
    from_pt = plan.start_point if i == 0 else (done[-1].poi["lat"], done[-1].poi["lng"])
    now = (plan.start_min if i == 0 else done[-1].depart) + delay
    left = plan.start_min + meta["hours"] * 60 - now
    before = {s.poi["id"] for s in plan.stops[i:]}
    addons = [a for a in meta["addons"] if not any(s.group == a for s in done)]
    new = plan_trip(pois, meta["scores"], plan.start_name, now, max(left, 0) / 60, meta["weekday"],
                    max(meta["max_stops"] - i, 1), meta["backend"], addons, meta["foodie"],
                    start_pt=from_pt, exclude=[s.poi["id"] for s in done]) if left > 30 else None
    new_stops = new.stops if new else []
    plan.stops = done + new_stops
    plan.end_min = new.end_min if new_stops else now
    if new:
        plan.backend, plan.solve_ms = new.backend, new.solve_ms
    after = {s.poi["id"] for s in new_stops}
    if new_stops and llm.available():
        try:
            texts, _ = llm.write_hints(new_stops, meta["lang"], meta["mood"], meta["difficulty"])
            ss.texts.update(texts or {})
        except Exception:
            pass
    ss.peek = set()
    ss.replan_msg = (f"⏰ Re-planned from {min_to_hhmm(now)}"
                     + (f" in {new.solve_ms:.0f} ms" if new else "")
                     + f": {len(before & after)} kept, {len(before - after)} dropped, "
                       f"{len(after - before)} new. Destinations stay secret.")


@st.cache_data(ttl=900, show_spinner=False)
def cached_outlook(day, start_min, hours):
    return weather.outlook(day, start_min, hours)


def switch_team(new):
    """Race mode keeps one trip state per team; swap the active one in and out."""
    ss.teams[ss.active] = {k: ss.get(k) for k in TEAM_STATE}
    for k, v in ss.teams[new].items():
        ss[k] = v
    ss.active = new


def team_progress(team):
    state = ss if team == ss.active else ss.teams[team]
    return state["step"], len(state["plan"].stops)


def reset():
    for k in ("plan", "texts", "teaser", "step", "revealed", "meta", "peek", "replan_msg",
              "mission", "photos", "teams", "active", "arrivals", "team_pick", "stage"):
        ss.pop(k, None)


# ---------- sidebar ----------

with st.sidebar:
    st.html('<p class="bt-label">Engine</p>')
    st.markdown(f"**Nemotron (build.nvidia.com):** {'🟢 connected' if llm.available() else '⚪ no API key'}")
    st.markdown(f"**cuOpt (GPU):** {'🟢 available' if cuopt_available() else '⚪ not installed — CPU exact DP'}")
    backend = st.radio("Route solver", ["auto", "cuopt", "cpu"], horizontal=True,
                       help="auto = cuOpt if installed, otherwise CPU exact DP")
    judge = st.toggle("🔍 Judge mode (shows spoilers)")
    demo_rain = st.toggle("🌧️ Simulate rain (demo)", help="Pretend rain is forecast to show weather-aware routing.")
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
        default_t = {"night": dt.time(18, 0), "romantic": dt.time(17, 0)}.get(theme, dt.time(10, 0))
        t0 = c4.time_input("Start time", default_t, step=dt.timedelta(minutes=30))
        hours = c5.slider("Hours", 3, 10, 6)
        start_min = t0.hour * 60 + t0.minute
        forecast = cached_outlook(day, start_min, hours)
        if demo_rain:
            forecast = {**(forecast or {"tmin": None, "tmax": None, "mm": 0}), "prob": 80, "rainy": True}
        w1, w2 = st.columns([3, 2], vertical_alignment="center")
        w1.caption(weather.describe(forecast) + (" (simulated)" if demo_rain else ""))
        adapt_weather = w2.toggle("🌦️ Adapt route to weather", value=True,
                                  help="If rain is likely, indoor places get priority.")
        c6, c7 = st.columns(2)
        max_stops = c6.slider("Max secret stops", 3, 7, 5)
        difficulty = c7.segmented_control("Clue difficulty", ["Easy", "Medium", "Hard"],
                                          default="Medium") or "Medium"
        race = st.toggle("🏁 Two-team race: separate secret routes that meet at one secret place",
                         help="cuOpt solves this as a 2-vehicle routing problem. Add-ons and re-planning "
                              "are off in race mode.")
        missions = st.toggle("📷 Photo missions: snap a photo to unlock each reveal",
                             help="A vision model on build.nvidia.com checks your photo. Without an "
                                  "API key, any photo unlocks the reveal.")

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

                if adapt_weather and forecast and forecast["rainy"] and theme != "rainy":
                    scores = weather.adapt(scores, pois)
                    st.write(f"🌧️ {forecast['prob']}% chance of rain: indoor places get priority.")
                race_plan = None
                if race:
                    st.write("🏁 Splitting the city into two secret routes that meet at one place…")
                    race_plan = plan_race(pois, scores, start, start_min, hours, day.weekday(),
                                          min(4, max_stops - 1), backend, foodie=foodie)
                    plan = race_plan.teams["A"] if race_plan else None
                else:
                    st.write("🧮 Solving orienteering with time windows (opening hours, stay time, budget)…")
                    plan = plan_trip(pois, scores, start, start_min, hours, day.weekday(), max_stops,
                                     backend, addons=addons, foodie=foodie)
                if not plan or not plan.stops:
                    status.update(label="No route fits", state="error")
                    st.error("Nothing fits this time window. Try a longer trip or a different start time.")
                    st.stop()

                texts, teaser = {}, None
                if llm.available():
                    st.write(f"✍️ Writing spoiler-free clues in {lang}…")
                    try:
                        all_stops = (plan.stops + race_plan.teams["B"].stops[:-1]) if race_plan else plan.stops
                        texts, teaser = llm.write_hints(all_stops, lang, mood, difficulty)
                        texts = texts or {}
                    except Exception as e:
                        st.write(f"⚠️ Using curated English clues ({e})")
                status.update(label="Your secret route is ready!", state="complete")

            if race_plan:
                fresh = {"step": 0, "revealed": False, "peek": set(), "mission": False, "photos": {},
                         "replan_msg": None, "stage": {}}
                ss.update(teams={t: {"plan": race_plan.teams[t], **fresh} for t in "AB"},
                          active="A", arrivals={}, team_pick="A")
            ss.update(plan=plan, texts=texts, teaser=teaser, step=0, revealed=False, peek=set(),
                      mission=False, photos={}, replan_msg=None, stage={},
                      meta={"mood": mood, "source": source, "lang": lang, "scores": scores,
                            "hours": hours, "weekday": day.weekday(), "max_stops": max_stops,
                            "addons": addons, "foodie": foodie, "backend": backend,
                            "difficulty": difficulty, "date": day.strftime("%a %d %b %Y"),
                            "missions": missions, "race": bool(race_plan),
                            "weather": weather.describe(forecast) + (" (simulated)" if demo_rain else ""),
                            "rain_adapted": bool(adapt_weather and forecast and forecast["rainy"]
                                                 and theme != "rainy")})
            st.rerun()

    st.html(ui.how_it_works())
    st.html(ui.footer())
    st.stop()


# ---------- trip ----------

st.html(ui.width_css(760))
racing = bool(ss.get("teams"))
if racing:
    pick = st.segmented_control("Team", list(TEAMS), format_func=TEAMS.get, key="team_pick",
                                label_visibility="collapsed") or ss.active
    if pick != ss.active:
        switch_team(pick)
        st.rerun()
plan, i = ss.plan, ss.step
n = len(plan.stops)
points = [plan.start_point] + [(s.poi["lat"], s.poi["lng"]) for s in plan.stops]

st.html(f'<p class="bt-label">Seoul · Blind Trip · from {ui.text(plan.start_name)}</p>'
        f'<h1 class="bt-display-md">{TEAMS[ss.active] + "’s secret route" if racing else "Your secret route"}</h1>'
        f'<div class="bt-band" style="margin-top:24px"><p class="bt-title-md">✨ '
        f'{ui.text(ss.teaser or f"{n} secret stops are waiting for you. Trust the map.")}</p>'
        f'<p class="bt-caption" style="margin-top:8px">{ui.text(ss.meta.get("weather", ""))}'
        f'{" · route adapted for rain" if ss.meta.get("rain_adapted") else ""}</p></div>')
st.html(ui.stats([("Secret stops", n), ("Trip length", f"{(plan.end_min - plan.start_min) / 60:.1f} h"),
                  ("Back by", min_to_hhmm(plan.end_min))]))
if plan.note:
    st.caption(f"ℹ️ {plan.note}")
if ss.get("replan_msg"):
    st.success(ss.replan_msg)
if racing:
    status = []
    for t in "AB":
        step, total = team_progress(t)
        arrived = ss.arrivals.get(t)
        status.append(f"{TEAMS[t]}: " + (f"🏁 arrived {arrived}" if arrived else f"stop {min(step + 1, total)} of {total}"))
    if len(ss.arrivals) == 2:
        winner = min(ss.arrivals, key=ss.arrivals.get)
        status.append(f"🏆 {TEAMS[winner]} reached the meeting point first!")
    elif len(ss.arrivals) == 1:
        status.append(f"🏆 {TEAMS[next(iter(ss.arrivals))]} got there first!")
    st.html('<div class="bt-band" style="padding:20px 24px"><p class="bt-label" style="margin-bottom:8px">🏁 Race</p>'
            + ui.pills(status) + '</div>')

if i >= n:
    st.balloons()
    km = sum(haversine_km(points[k], points[k + 1]) for k in range(len(points) - 1))
    st.html(ui.passport(plan.stops, ss.meta.get("date", ""), ss.meta["mood"], km,
                        (plan.end_min - plan.start_min) / 60, min_to_hhmm))
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
        difficulty = ss.meta.get("difficulty", "Medium")
        peeked = i in ss.get("peek", set())
        with st.container(key=f"stop-{color}"):
            st.html(
                f'<p class="bt-label" style="color:inherit;opacity:.75">Secret stop {i + 1} of {n}</p>'
                + ui.pills([badge(stop) if difficulty != "Hard" else "",
                            f"{MODE_ICON[stop.mode]} ~{stop.travel_min} min by {stop.mode}",
                            f"arrive ≈ {min_to_hhmm(stop.arrive)}{wait}",
                            f"stay ≈ {stop.poi['stay']} min"], tone)
                + f'<p class="bt-hint">🔒 “{ui.text(text_for(stop, "hint"))}”</p>'
                + (f'<p class="bt-body" style="color:inherit;opacity:.9">💡 {ui.text(easy_clue(stop, points[i]))}</p>'
                   if difficulty == "Easy" else "")
                + (f'<p class="bt-body" style="color:inherit;margin-top:12px">🆘 Peeked: <b>{ui.text(stop.poi["name_en"])}</b> · '
                   f'<span style="font-family:\'Noto Sans KR\',sans-serif">{ui.text(stop.poi["name_ko"])}</span></p>'
                   if peeked else ""))
            # Help ladder for this leg only: area (station) -> walking clue -> exact spot.
            appr = approach(stop, points[i])
            walking = appr is None or ss.stage.get(stop.poi["id"]) == "walk"
            if walking:
                translated = ss.texts.get(stop.poi["id"], {}).get("walk")
                if appr and appr["clue"]:
                    clue = translated or appr["clue"]
                    extra = compass_clue(appr["pt"], here) if difficulty == "Easy" else ""
                else:
                    clue, extra = compass_clue(appr["pt"] if appr else points[i], here), ""
                st.html(f'<div class="bt-frag"><b>🚶 Walking clue</b><br>{ui.text(clue)}'
                        + (f'<br>{ui.text(extra)}' if extra else "") + '</div>')
            speech_text = clue if walking else text_for(stop, "hint")
            speech_lang = ss.meta["lang"] if stop.poi["id"] in ss.texts else "English"
            st.iframe(ui.speak_button(speech_text, speech_lang, color in ui.DARK_CARDS), height=44)
            if not walking:
                st.link_button(f"🧭 Get to the area: {appr['label']}", gmaps_link(appr["pt"]), width="stretch")
                if st.button("🚶 I'm in the area — show the walking clue", type="primary", width="stretch"):
                    ss.stage[stop.poi["id"]] = "walk"
                    st.rerun()
            if walking and not ss.get("mission") and st.button(
                    "📍 I've arrived — " + ("take the photo mission" if ss.meta.get("missions") else "reveal!"),
                    type="primary", width="stretch"):
                ss.replan_msg = None
                if stop.group == "meet":
                    ss.arrivals.setdefault(ss.active, dt.datetime.now().strftime("%H:%M:%S"))
                if ss.meta.get("missions"):
                    ss.mission = True
                else:
                    ss.revealed = True
                st.rerun()
            if walking and not ss.get("mission"):
                st.link_button("😵 Can't find it? Open the exact spot in Google Maps", gmaps_link(here),
                               width="stretch")
            if ss.get("mission"):
                st.html(f'<p class="bt-label" style="color:inherit;opacity:.75;margin-top:16px">📷 Photo mission</p>'
                        f'<p class="bt-title-md">{ui.text(mission_for(stop.poi))}</p>')
                upload = st.file_uploader("Upload a photo", type=["jpg", "jpeg", "png", "webp"])
                shot = None
                if st.toggle("📸 Use my camera instead"):
                    shot = st.camera_input("Take a photo", label_visibility="collapsed")
                photo = shot or upload
                m1_, m2_ = st.columns(2)
                if photo and m1_.button("✅ Check my photo", type="primary", width="stretch"):
                    data = photo.getvalue()
                    passed, comment = True, "Photo saved! (No API key, so no AI check.)"
                    if llm.available():
                        with st.spinner("A vision model is looking at your photo…"):
                            try:
                                passed, comment = llm.check_photo(data, mission_for(stop.poi))
                            except Exception as e:
                                comment = f"Couldn't check the photo ({e}), so it counts!"
                    if passed:
                        ss.photos[i] = data
                        ss.mission, ss.revealed = False, True
                        st.toast(f"📷 {comment}")
                        st.rerun()
                    st.warning(f"Not quite: {comment} Try another shot, or skip.")
                if m2_.button("Skip mission", width="stretch"):
                    ss.mission, ss.revealed = False, True
                    st.rerun()
            if racing:  # re-planning would break the shared meeting point
                c4 = st.container()
            else:
                c3, c4 = st.columns(2)
                with c3.popover("⏰ Running late?", width="stretch"):
                    delay = st.select_slider("How late are you?", [15, 30, 45, 60, 90], value=30,
                                             format_func=lambda m: f"{m} min")
                    st.caption("We'll re-optimize the remaining stops from where you are. They stay secret.")
                    if st.button("Re-plan my route", type="primary", width="stretch"):
                        replan(i, delay)
                        st.rerun()
            with c4.popover("🆘 Lost? Peek", width="stretch"):
                st.warning("This reveals where you're heading. Use it if you're lost or need to ask someone.")
                if st.button("Show me the destination", width="stretch"):
                    ss.peek = ss.get("peek", set()) | {i}
                    st.rerun()
    else:
        with st.container(key="reveal"):
            st.html(
                f'<p class="bt-label">You found it · stop {i + 1} of {n}</p>'
                f'<h2 class="bt-display-md">{ui.text(stop.poi["name_en"])}</h2>'
                f'<p class="bt-ko">{ui.text(stop.poi["name_ko"])}</p>'
                f'<p class="bt-caption">Show this to locals if you need directions</p>'
                + (f'<p style="margin:14px 0 0">{ui.pills(["🎬 Seen in: " + ", ".join(stop.poi["dramas"])])}</p>'
                   if stop.poi.get("dramas") else "")
                + f'<p class="bt-body" style="margin-top:20px">{ui.text(text_for(stop, "reveal"))}</p>'
                f'<div class="bt-frag" style="background:var(--canvas)">💡 {ui.text(text_for(stop, "tip"))}</div>')
            if i in ss.get("photos", {}):
                st.image(ss.photos[i], caption="Your mission photo", width=320)
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
