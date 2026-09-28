"""Run on a GPU machine to verify cuOpt and compare it with the CPU DP.

    pip install --extra-index-url=https://pypi.nvidia.com 'cuopt-cu12==26.2.*'   # CUDA 12
    pip install --extra-index-url=https://pypi.nvidia.com cuopt-cu13              # CUDA 13
    pip install -r requirements.txt
    python cuopt_check.py
"""

import traceback

from planner import THEMES, cuopt_available, load_pois, min_to_hhmm, plan_race, plan_trip, tag_scores

pois = load_pois()
print("cuOpt importable:", cuopt_available())
if cuopt_available():
    import cuopt
    print("cuOpt version:", getattr(cuopt, "__version__", "?"))

results = []


def show(p):
    total = sum(s.score for s in p.stops)
    moving = sum(s.travel_min + s.wait for s in p.stops)
    print(f"   [{p.backend}] {p.solve_ms:.0f} ms, {len(p.candidates)} candidates, "
          f"score {total}, moving {moving} min, back {min_to_hhmm(p.end_min)}")
    if p.note:
        print("   note:", p.note)
    for s in p.stops:
        print(f"      {min_to_hhmm(s.arrive)} {s.poi['name_en']} [{s.score}] {s.group or ''}")


cases = [
    ("calm", "Myeongdong", 10 * 60, 6, ()),
    ("calm", "Myeongdong", 10 * 60, 6, ("food", "activity")),
    ("landmark", "Hongdae (Hongik Univ. Stn)", 10 * 60, 7, ("food",)),
    ("night", "Gangnam Station", 18 * 60, 4, ("activity",)),
    ("food", "Seoul Station", 11 * 60, 6, ()),
]
for theme, start, t0, hours, addons in cases:
    name = f"{THEMES[theme][0]} from {start}, {hours}h, add-ons={addons}"
    print(f"\n=== {name} ===")
    for backend in ("cpu", "cuopt"):
        try:
            p = plan_trip(pois, tag_scores(pois, theme), start, t0, hours, weekday=2, max_stops=5,
                          backend=backend, addons=addons, foodie=(theme == "food"))
            show(p)
            if backend == "cuopt":
                ok = p.backend.startswith("NVIDIA cuOpt")
                results.append((name, ok, p.note or ""))
        except Exception:
            traceback.print_exc()
            if backend == "cuopt":
                results.append((name, False, "exception"))

print("\n=== 🏁 Two-team race (2-vehicle VRP) ===")
for backend in ("cpu", "cuopt"):
    try:
        r = plan_race(pois, tag_scores(pois, "landmark"), "Myeongdong", 10 * 60, 6, 2, 3, backend=backend)
        print(f" meeting point: {r.meet['name_en']} | {r.backend} {r.solve_ms:.0f} ms {r.note}")
        for team, p in r.teams.items():
            print(f"   Team {team}: " + " → ".join(f"{s.poi['name_en']}@{min_to_hhmm(s.arrive)}" for s in p.stops))
        if backend == "cuopt":
            results.append(("race", r.backend.startswith("NVIDIA cuOpt"), r.note))
    except Exception:
        traceback.print_exc()
        if backend == "cuopt":
            results.append(("race", False, "exception"))

print("\n=== SUMMARY: did cuOpt actually solve it? ===")
for name, ok, note in results:
    print(("✅ " if ok else "❌ ") + name + (f"  ({note})" if note and not ok else ""))
