"""Run on a GPU box (Colab T4, Brev, ...) to verify cuOpt and compare with the CPU DP.

    pip install --extra-index-url=https://pypi.nvidia.com 'cuopt-cu12==26.2.*' requests
    python cuopt_check.py
"""

from planner import THEMES, load_pois, min_to_hhmm, plan_trip, tag_scores

pois = load_pois()
cases = [
    ("calm", "Myeongdong", 10 * 60, 6),
    ("landmark", "Hongdae (Hongik Univ. Stn)", 10 * 60, 7),
    ("night", "Gangnam Station", 18 * 60, 4),
    ("kculture", "Seoul Station", 11 * 60, 6),
]

for theme, start, t0, hours in cases:
    scores = tag_scores(pois, theme)
    print(f"\n=== {THEMES[theme][0]} from {start}, {hours}h ===")
    for backend in ("cpu", "cuopt"):
        p = plan_trip(pois, scores, start, t0, hours, weekday=2, max_stops=5, backend=backend)
        total = sum(s.score for s in p.stops)
        moving = sum(s.travel_min + s.wait for s in p.stops)
        print(f"[{p.backend}] {p.solve_ms:.0f} ms, {len(p.candidates)} candidates, "
              f"score {total}, moving {moving} min, back {min_to_hhmm(p.end_min)}")
        if p.note:
            print("   note:", p.note)
        for s in p.stops:
            print(f"   {min_to_hhmm(s.arrive)} {s.poi['name_en']} [{s.score}]")
