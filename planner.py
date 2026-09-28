"""Route planning for Seoul Blind Trip.

The planning problem is a prize-collecting TSP with time windows (orienteering):
pick the subset of places that maximizes theme score within the time budget,
respecting opening hours and stay durations, and order them.

Optional add-ons ("include a food stop", "include an activity") become group
constraints: exactly one member of the group must be on the route.

Backends:
  - cuOpt (GPU): routing.DataModel with order prizes, time windows and one
    capacity dimension per group.
  - CPU exact DP: bitmask dynamic programming over the top-K candidates.
"""

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).parent / "data" / "seoul_pois.json"

START_POINTS = {
    "Myeongdong": (37.5609, 126.9863),
    "Hongdae (Hongik Univ. Stn)": (37.5572, 126.9245),
    "Gangnam Station": (37.4979, 127.0276),
    "Seoul Station": (37.5547, 126.9707),
    "Itaewon": (37.5345, 126.9946),
    "Jongno / Insadong (Anguk Stn)": (37.5765, 126.9855),
    "Dongdaemun (DDP)": (37.5655, 127.0074),
    "Jamsil (Lotte World)": (37.5133, 127.1001),
}

# theme key -> (label, tag weights)
THEMES = {
    "calm": ("🌿 Healing & Slow", {"calm": 4, "nature": 3, "traditional": 1}),
    "landmark": ("🏙️ Iconic Landmarks", {"landmark": 5, "night": 1}),
    "food": ("🍜 Foodie Trip", {"food": 5, "traditional": 1}),
    "traditional": ("🏯 Traditional Korea", {"traditional": 5, "calm": 1}),
    "kculture": ("🎤 K-Culture & Trendy", {"kculture": 4, "trendy": 3}),
    "night": ("🌃 Night Views", {"night": 5, "landmark": 1}),
    "romantic": ("💑 Date & Romance", {"romantic": 5, "night": 1}),
    "photo": ("📸 Photo Spots", {"photo": 5, "trendy": 1}),
    "shopping": ("🛍️ Shopping", {"shopping": 5, "food": 1}),
    "rainy": ("🌧️ Rainy Day", {"indoor": 5, "calm": 1}),
    "family": ("👨‍👩‍👧 Family & Kids", {"family": 5, "nature": 1}),
    "kdrama": ("🎬 K-Drama Spots", {"kdrama": 5, "romantic": 1}),
}

# Kinds that only show up on request (or, for restaurants/cafés, on the Foodie theme).
ADDON_ONLY = {"restaurant", "cafe", "activity"}
ADDON_PRIZE = 6       # floor score for a requested add-on stop
FOODIE_CAPS = {"restaurant": 2, "cafe": 1}  # keep a food trip from being five lunches
LUNCH = (11 * 60 + 30, 14 * 60)
DINNER = (17 * 60 + 30, 20 * 60 + 30)

MIN_SCORE = 4        # places scoring below this (0-10) are never candidates
PRIZE_WEIGHT = 10    # 1 theme point is worth 10 minutes of travel
MAX_CANDIDATES = 12  # CPU DP is exact over 2^K subsets; cuOpt gets every candidate
ADDON_SLOTS = 3      # per requested add-on group, within MAX_CANDIDATES
NEAR_START_KM = 0.4  # skip places you are already standing in


def load_pois():
    return json.loads(DATA.read_text(encoding="utf-8"))


def haversine_km(a, b):
    lat1, lng1 = a
    lat2, lng2 = b
    p = math.radians
    x = (math.sin(p(lat2 - lat1) / 2) ** 2
         + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lng2 - lng1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(x))


def leg(a, b):
    """Estimated door-to-door minutes and mode between two points in Seoul."""
    d = haversine_km(a, b)
    if d <= 1.2:
        return max(1, round(d * 1.3 / 4.5 * 60)), "walk"
    # subway: ~10 min walking/waiting overhead + ~25 km/h effective speed
    return round(10 + d * 1.35 / 25 * 60), "subway"


def hhmm_to_min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(m):
    m = int(round(m)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def tag_scores(pois, theme_key):
    weights = THEMES[theme_key][1]
    raw = {p["id"]: sum(weights.get(t, 0) for t in p["tags"]) for p in pois}
    top = max(raw.values()) or 1
    return {k: round(10 * v / top) for k, v in raw.items()}


def meal_window(start_min, budget):
    """Lunch or dinner window the trip overlaps by at least an hour, else None."""
    end = start_min + budget
    for lo, hi in (LUNCH, DINNER):
        if min(end, hi) - max(start_min, lo) >= 60:
            return lo, hi
    return None


@dataclass
class Cand:
    poi: dict
    score: int
    early: int    # minutes after trip start
    late: int
    group: str = None


@dataclass
class Stop:
    poi: dict
    score: int
    travel_min: int
    mode: str
    arrive: int   # minutes of day
    depart: int
    wait: int
    group: str = None


@dataclass
class Plan:
    stops: list
    start_name: str
    start_point: tuple
    start_min: int
    end_min: int
    backend: str
    solve_ms: float
    candidates: list = field(default_factory=list)  # Cand considered
    note: str = ""


def _candidates(pois, scores, start_pt, start_min, budget, weekday, addons, foodie):
    meal = meal_window(start_min, budget)
    out = []
    for p in pois:
        kind = p.get("kind", "place")
        s = scores.get(p["id"], 0)
        early = max(0, hhmm_to_min(p["open"]) - start_min)
        late = min(budget - p["stay"], hhmm_to_min(p["close"]) - p["stay"] - start_min)
        group = None

        if foodie and kind in FOODIE_CAPS:
            group = kind                    # regular foodie stop, capped per kind
        elif kind in ADDON_ONLY or (kind == "market" and "food" in addons):
            if kind == "activity" and "activity" in addons:
                group = "activity"
            elif kind != "activity" and "food" in addons and not foodie:
                # Meal-time trips get a restaurant or market at lunch/dinner;
                # otherwise a café break.
                if meal and kind in ("restaurant", "market"):
                    early = max(early, meal[0] - start_min)
                    late = min(late, meal[1] - start_min)
                    group = "food"
                elif not meal and kind == "cafe":
                    group = "food"
            if group is None and kind in ADDON_ONLY:
                continue
            if group:
                s = max(s, ADDON_PRIZE)

        if group is None and s < MIN_SCORE:
            continue
        if weekday in p.get("closed_days", []):
            continue
        if haversine_km(start_pt, (p["lat"], p["lng"])) < NEAR_START_KM:
            continue
        if late < early:
            continue
        out.append(Cand(p, s, early, late, group))
    out.sort(key=lambda c: -c.score)
    return out


def _cpu_subset(cands, required):
    """Top theme places plus the best few members of each required group."""
    regular = [c for c in cands if c.group not in required]
    keep = regular[:MAX_CANDIDATES - ADDON_SLOTS * len(required)]
    if keep:
        clat = sum(c.poi["lat"] for c in keep) / len(keep)
        clng = sum(c.poi["lng"] for c in keep) / len(keep)
    for g in required:
        members = [c for c in cands if c.group == g]
        if keep:  # prefer add-ons close to where the rest of the trip happens
            members.sort(key=lambda c: (-c.score, haversine_km((clat, clng), (c.poi["lat"], c.poi["lng"]))))
        keep += members[:ADDON_SLOTS]
    return keep


def _matrix(points):
    n = len(points)
    T = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                T[i][j] = leg(points[i], points[j])[0]
    return T


def solve_dp(T, stay, early, late, prize, max_stops, group=None, caps=None, required=(), end=None):
    """Exact orienteering with time windows and group caps. Index 0 is the start point.

    `end=(column, latest_arrival)` forces the route to finish at a fixed place
    (the matrix column) by a deadline, counting that last leg as travel.
    Returns (order, missing_groups).
    """
    n = len(stay)  # number of candidate places (matrix has n + 1 rows)
    group = group or [None] * n
    caps = caps or {}
    gmask = {}
    for i, g in enumerate(group):
        if g:
            gmask[g] = gmask.get(g, 0) | (1 << i)

    INF = float("inf")
    best = {}  # (mask, last) -> (finish_time, parent_last)
    for i in range(n):
        arr = max(T[0][i + 1], early[i])
        if arr <= late[i]:
            best[(1 << i, i)] = (arr + stay[i], -1)
    for mask in range(1, 1 << n):
        if bin(mask).count("1") >= max_stops:
            continue
        for last in range(n):
            st = best.get((mask, last))
            if st is None:
                continue
            t = st[0]
            for nxt in range(n):
                if mask & (1 << nxt):
                    continue
                g = group[nxt]
                if g and bin(mask & gmask[g]).count("1") >= caps.get(g, n):
                    continue
                arr = max(t + T[last + 1][nxt + 1], early[nxt])
                if arr > late[nxt]:
                    continue
                key = (mask | (1 << nxt), nxt)
                fin = arr + stay[nxt]
                if fin < best.get(key, (INF,))[0]:
                    best[key] = (fin, last)
    states = list(best.items())
    if end:
        col, end_late = end
        states = [kv for kv in states if kv[1][0] + T[kv[0][1] + 1][col] <= end_late]
    if not states:
        return [], list(required)

    def value(kv):
        (mask, last), (finish, _) = kv
        members = [i for i in range(n) if mask >> i & 1]
        moving = finish - sum(stay[i] for i in members)  # travel + waiting
        if end:
            moving += T[last + 1][end[0]]
        return PRIZE_WEIGHT * sum(prize[i] for i in members) - moving

    ok = [kv for kv in states if all(kv[0][0] & gmask.get(g, 0) for g in required)]
    missing = [] if ok else list(required)
    (mask, last), _ = max(ok or states, key=value)
    order = []
    while last != -1:
        order.append(last)
        prev = best[(mask, last)][1]
        mask &= ~(1 << last)
        last = prev
    return order[::-1], missing


def solve_cuopt(T, stay, early, late, prize, max_stops, budget, group, caps, required):
    import cudf
    from cuopt import routing

    n = len(stay)
    # A large prize makes required add-ons effectively mandatory; the group
    # capacity below keeps it to exactly the allowed count.
    prize = [p + (100 if group[i] in required else 0) for i, p in enumerate(prize)]
    M = cudf.DataFrame(T, dtype="float32")
    dm = routing.DataModel(n_locations=n + 1, n_fleet=1, n_orders=n)
    dm.add_cost_matrix(M)
    dm.add_transit_time_matrix(M)
    dm.set_order_locations(cudf.Series(list(range(1, n + 1)), dtype="int32"))
    dm.set_order_time_windows(cudf.Series(early, dtype="int32"), cudf.Series(late, dtype="int32"))
    dm.set_order_service_times(cudf.Series(stay, dtype="int32"))
    dm.set_order_prizes(cudf.Series(prize, dtype="float32"))
    dm.add_capacity_dimension("stops", cudf.Series([1] * n, dtype="int32"),
                              cudf.Series([max_stops], dtype="int32"))
    for g, cap in caps.items():
        dm.add_capacity_dimension(g, cudf.Series([int(x == g) for x in group], dtype="int32"),
                                  cudf.Series([cap], dtype="int32"))
    dm.set_vehicle_locations(cudf.Series([0], dtype="int32"), cudf.Series([0], dtype="int32"))
    dm.set_drop_return_trips(cudf.Series([True]))
    dm.set_vehicle_time_windows(cudf.Series([0], dtype="int32"), cudf.Series([budget], dtype="int32"))
    # Same trade-off as the DP backend: theme points vs. minutes on the move.
    dm.set_objective_function(
        cudf.Series([routing.Objective.PRIZE, routing.Objective.COST]),
        cudf.Series([PRIZE_WEIGHT, 1], dtype="float32"),
    )
    ss = routing.SolverSettings()
    ss.set_time_limit(2)
    sol = routing.Solve(dm, ss)
    if sol.get_status() != 0:
        raise RuntimeError(f"cuOpt status {sol.get_status()}: {sol.get_error_message()}")
    route = sol.get_route().to_pandas().sort_values("arrival_stamp")
    order = [int(loc) - 1 for loc in route["location"] if int(loc) != 0]
    missing = [g for g in required if not any(group[i] == g for i in order)]
    return order, missing


def cuopt_available():
    try:
        import cuopt  # noqa: F401
        return True
    except Exception:
        return False


ADDON_LABELS = {"food": "a food stop", "activity": "an activity"}


def plan_trip(pois, scores, start_name, start_min, hours, weekday, max_stops,
              backend="auto", addons=(), foodie=False, start_pt=None, exclude=()):
    """Plan a route. `start_pt`/`exclude` let a trip be re-planned mid-way from
    the traveler's current position without revisiting places."""
    start_pt = start_pt or START_POINTS[start_name]
    budget = int(hours * 60)
    addons = set(addons)
    if exclude:
        pois = [p for p in pois if p["id"] not in set(exclude)]
    all_cands = _candidates(pois, scores, start_pt, start_min, budget, weekday, addons, foodie)
    required = {g for g in addons if any(c.group == g for c in all_cands)}
    caps = {g: 1 for g in required}
    if foodie:
        caps.update({g: c for g, c in FOODIE_CAPS.items() if any(x.group == g for x in all_cands)})

    def problem(cands):
        T = _matrix([start_pt] + [(c.poi["lat"], c.poi["lng"]) for c in cands])
        return (T, [c.poi["stay"] for c in cands], [c.early for c in cands],
                [c.late for c in cands], [c.score for c in cands])

    notes = []
    t0 = time.perf_counter()
    order = None
    if backend in ("auto", "cuopt") and all_cands:
        if cuopt_available():
            try:
                cands = all_cands
                order, missing = solve_cuopt(*problem(cands), max_stops, budget,
                                             [c.group for c in cands], caps, required)
                used = "NVIDIA cuOpt (GPU)"
            except Exception as e:  # keep the demo alive
                notes.append(f"cuOpt failed, fell back to CPU: {e}")
        elif backend == "cuopt":
            notes.append("cuOpt not installed on this machine; used CPU exact DP.")
    if order is None:
        cands = _cpu_subset(all_cands, required)
        order, missing = (solve_dp(*problem(cands), max_stops, [c.group for c in cands],
                                   caps, required) if cands else ([], []))
        used = "CPU exact DP"
    solve_ms = (time.perf_counter() - t0) * 1000

    for g in sorted(addons - required) + sorted(missing):
        notes.append(f"Couldn't fit {ADDON_LABELS[g]} into this time window.")

    stops = []
    t = start_min
    prev = start_pt
    for i in order:
        c = cands[i]
        here = (c.poi["lat"], c.poi["lng"])
        mins, mode = leg(prev, here)
        arr = t + mins
        wait = max(0, start_min + c.early - arr)
        arr += wait
        dep = arr + c.poi["stay"]
        stops.append(Stop(c.poi, c.score, mins, mode, arr, dep, wait, c.group))
        t, prev = dep, here

    return Plan(
        stops=stops, start_name=start_name, start_point=start_pt,
        start_min=start_min, end_min=t, backend=used, solve_ms=solve_ms,
        candidates=cands, note=" ".join(notes),
    )


# ---------- two-team race ----------

@dataclass
class RacePlan:
    teams: dict          # "A" / "B" -> Plan (last stop is the shared meeting point)
    meet: dict           # meeting-point poi
    backend: str
    solve_ms: float
    note: str = ""


def _schedule(cands, start_pt, start_min, groups=None):
    stops, t, prev = [], start_min, start_pt
    for k, c in enumerate(cands):
        here = (c.poi["lat"], c.poi["lng"])
        mins, mode = leg(prev, here)
        arr = t + mins
        wait = max(0, start_min + c.early - arr)
        arr += wait
        dep = arr + c.poi["stay"]
        stops.append(Stop(c.poi, c.score, mins, mode, arr, dep, wait,
                          (groups or {}).get(k, c.group)))
        t, prev = dep, here
    return stops, t


def solve_cuopt_race(T, stay, early, late, prize, per_team, meet_col, meet_late):
    import cudf
    from cuopt import routing

    n = len(stay)
    M = cudf.DataFrame(T, dtype="float32")
    dm = routing.DataModel(n_locations=n + 2, n_fleet=2, n_orders=n)
    dm.add_cost_matrix(M)
    dm.add_transit_time_matrix(M)
    dm.set_order_locations(cudf.Series(list(range(1, n + 1)), dtype="int32"))
    dm.set_order_time_windows(cudf.Series(early, dtype="int32"), cudf.Series(late, dtype="int32"))
    dm.set_order_service_times(cudf.Series(stay, dtype="int32"))
    dm.set_order_prizes(cudf.Series(prize, dtype="float32"))
    dm.add_capacity_dimension("stops", cudf.Series([1] * n, dtype="int32"),
                              cudf.Series([per_team, per_team], dtype="int32"))
    # Both teams leave the hotel and must end at the meeting point by its deadline.
    dm.set_vehicle_locations(cudf.Series([0, 0], dtype="int32"),
                             cudf.Series([meet_col, meet_col], dtype="int32"))
    dm.set_vehicle_time_windows(cudf.Series([0, 0], dtype="int32"),
                                cudf.Series([meet_late, meet_late], dtype="int32"))
    dm.set_min_vehicles(2)
    dm.set_objective_function(
        cudf.Series([routing.Objective.PRIZE, routing.Objective.COST]),
        cudf.Series([PRIZE_WEIGHT, 1], dtype="float32"),
    )
    ss = routing.SolverSettings()
    ss.set_time_limit(3)
    sol = routing.Solve(dm, ss)
    if sol.get_status() != 0:
        raise RuntimeError(f"cuOpt status {sol.get_status()}: {sol.get_error_message()}")
    route = sol.get_route().to_pandas().sort_values("arrival_stamp")
    out = []
    for truck in sorted(route["truck_id"].unique()):
        locs = route[route["truck_id"] == truck]["location"]
        out.append([int(loc) - 1 for loc in locs if 0 < int(loc) < meet_col])
    return out + [[]] * (2 - len(out))


def plan_race(pois, scores, start_name, start_min, hours, weekday, per_team, backend="auto", foodie=False):
    """Two disjoint secret routes from the same start that converge on one meeting point."""
    start_pt = START_POINTS[start_name]
    budget = int(hours * 60)
    cands = _candidates(pois, scores, start_pt, start_min, budget, weekday, set(), foodie)
    finale = [c for c in cands if c.late >= budget * 0.6
              and haversine_km(start_pt, (c.poi["lat"], c.poi["lng"])) <= 10]
    if not finale:
        return None
    meet = max(finale, key=lambda c: (c.score, c.late))
    pool = [c for c in cands if c.poi["id"] != meet.poi["id"]]
    meet_pt = (meet.poi["lat"], meet.poi["lng"])

    def problem(sub):
        T = _matrix([start_pt] + [(c.poi["lat"], c.poi["lng"]) for c in sub] + [meet_pt])
        return (T, [c.poi["stay"] for c in sub], [c.early for c in sub],
                [c.late for c in sub], [c.score for c in sub])

    note, orders, used = "", None, "CPU exact DP"
    t0 = time.perf_counter()
    if backend in ("auto", "cuopt") and cuopt_available() and pool:
        try:
            idx = solve_cuopt_race(*problem(pool), per_team, len(pool) + 1, meet.late)
            orders = [[pool[k] for k in r] for r in idx]
            used = "NVIDIA cuOpt (GPU, 2-vehicle VRP)"
        except Exception as e:
            note = f"cuOpt failed, fell back to CPU: {e}"
    elif backend == "cuopt":
        note = "cuOpt not installed on this machine; used CPU exact DP."
    if orders is None:
        def best_route(exclude, k):
            sub = [c for c in pool if c.poi["id"] not in exclude][:MAX_CANDIDATES]
            if not sub or k < 1:
                return []
            order, _ = solve_dp(*problem(sub), k, end=(len(sub) + 1, meet.late))
            return [sub[j] for j in order]

        ids = lambda route: {c.poi["id"] for c in route}
        team_a = best_route(set(), per_team)             # A drafts first,
        team_b = best_route(ids(team_a), per_team)       # B from what's left,
        if len(team_a) > len(team_b):                    # then A re-drafts to match B's size
            team_a = best_route(ids(team_b), len(team_b)) or team_a
        orders = [team_a, team_b]
    solve_ms = (time.perf_counter() - t0) * 1000

    teams = {}
    for name, route in zip("AB", orders):
        stops, end = _schedule(route + [meet], start_pt, start_min, {len(route): "meet"})
        teams[name] = Plan(stops=stops, start_name=start_name, start_point=start_pt,
                           start_min=start_min, end_min=end, backend=used, solve_ms=solve_ms,
                           candidates=cands, note=note)
    return RacePlan(teams=teams, meet=meet.poi, backend=used, solve_ms=solve_ms, note=note)
