"""Route planning for Seoul Blind Trip.

The planning problem is a prize-collecting TSP with time windows (orienteering):
pick the subset of places that maximizes theme score within the time budget,
respecting opening hours and stay durations, and order them.

Backends:
  - cuOpt (GPU): routing.DataModel with order prizes + time windows.
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
    "calm": ("🌿 Calm & Slow", {"calm": 4, "nature": 3, "traditional": 1}),
    "landmark": ("🏙️ Iconic Landmarks", {"landmark": 5, "night": 1}),
    "traditional": ("🏯 Traditional Korea", {"traditional": 5, "calm": 1}),
    "kculture": ("🎤 K-Culture & Trendy", {"kculture": 4, "trendy": 3}),
    "food": ("🍜 Foodie Adventure", {"food": 5, "traditional": 1}),
    "night": ("🌃 Night Views", {"night": 5, "landmark": 1}),
}

MIN_SCORE = 4        # places scoring below this (0-10) are never candidates
PRIZE_WEIGHT = 10    # 1 theme point is worth 10 minutes of travel
MAX_CANDIDATES = 12  # CPU DP is exact over 2^K subsets; cuOpt gets every candidate
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


@dataclass
class Stop:
    poi: dict
    score: int
    travel_min: int
    mode: str
    arrive: int   # minutes of day
    depart: int
    wait: int


@dataclass
class Plan:
    stops: list
    start_name: str
    start_point: tuple
    start_min: int
    end_min: int
    backend: str
    solve_ms: float
    candidates: list = field(default_factory=list)  # (poi, score) considered
    note: str = ""


def _candidates(pois, scores, start_pt, start_min, budget, weekday):
    out = []
    for p in pois:
        s = scores.get(p["id"], 0)
        if s < MIN_SCORE or weekday in p.get("closed_days", []):
            continue
        if haversine_km(start_pt, (p["lat"], p["lng"])) < NEAR_START_KM:
            continue
        early = max(0, hhmm_to_min(p["open"]) - start_min)
        late = min(budget - p["stay"], hhmm_to_min(p["close"]) - p["stay"] - start_min)
        if late < early:
            continue
        out.append((p, s, early, late))
    out.sort(key=lambda c: -c[1])
    return out


def _matrix(points):
    n = len(points)
    T = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                T[i][j] = leg(points[i], points[j])[0]
    return T


def solve_dp(T, stay, early, late, prize, max_stops):
    """Exact orienteering with time windows. Index 0 is the start point."""
    n = len(stay)  # number of candidate places (matrix has n + 1 rows)
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
                arr = max(t + T[last + 1][nxt + 1], early[nxt])
                if arr > late[nxt]:
                    continue
                key = (mask | (1 << nxt), nxt)
                fin = arr + stay[nxt]
                if fin < best.get(key, (INF,))[0]:
                    best[key] = (fin, last)
    if not best:
        return []
    def value(kv):
        (mask, _), (finish, _) = kv
        members = [i for i in range(n) if mask >> i & 1]
        moving = finish - sum(stay[i] for i in members)  # travel + waiting
        return PRIZE_WEIGHT * sum(prize[i] for i in members) - moving

    (mask, last), _ = max(best.items(), key=value)
    order = []
    while last != -1:
        order.append(last)
        prev = best[(mask, last)][1]
        mask &= ~(1 << last)
        last = prev
    return order[::-1]


def solve_cuopt(T, stay, early, late, prize, max_stops, budget):
    import cudf
    from cuopt import routing

    n = len(stay)
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
    return [int(loc) - 1 for loc in route["location"] if int(loc) != 0]


def cuopt_available():
    try:
        import cuopt  # noqa: F401
        return True
    except Exception:
        return False


def plan_trip(pois, scores, start_name, start_min, hours, weekday, max_stops, backend="auto"):
    start_pt = START_POINTS[start_name]
    budget = int(hours * 60)
    all_cands = _candidates(pois, scores, start_pt, start_min, budget, weekday)

    def problem(cands):
        T = _matrix([start_pt] + [(c[0]["lat"], c[0]["lng"]) for c in cands])
        return (T, [c[0]["stay"] for c in cands], [c[2] for c in cands],
                [c[3] for c in cands], [c[1] for c in cands])

    note = ""
    t0 = time.perf_counter()
    order = None
    if backend in ("auto", "cuopt") and all_cands:
        if cuopt_available():
            try:
                cands = all_cands
                order = solve_cuopt(*problem(cands), max_stops, budget)
                used = "NVIDIA cuOpt (GPU)"
            except Exception as e:  # keep the demo alive
                note = f"cuOpt failed, fell back to CPU: {e}"
        elif backend == "cuopt":
            note = "cuOpt not installed on this machine; used CPU exact DP."
    if order is None:
        cands = all_cands[:MAX_CANDIDATES]
        order = solve_dp(*problem(cands), max_stops) if cands else []
        used = "CPU exact DP"
    solve_ms = (time.perf_counter() - t0) * 1000

    stops = []
    t = start_min
    prev = start_pt
    for i in order:
        p, s = cands[i][0], cands[i][1]
        here = (p["lat"], p["lng"])
        mins, mode = leg(prev, here)
        arr = t + mins
        open_at = hhmm_to_min(p["open"])
        wait = max(0, open_at - arr)
        arr += wait
        dep = arr + p["stay"]
        stops.append(Stop(p, s, mins, mode, arr, dep, wait))
        t, prev = dep, here

    return Plan(
        stops=stops, start_name=start_name, start_point=start_pt,
        start_min=start_min, end_min=t, backend=used, solve_ms=solve_ms,
        candidates=[(c[0], c[1]) for c in cands], note=note,
    )
