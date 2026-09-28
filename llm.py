"""Nemotron (build.nvidia.com) calls: mood -> place scores, and spoiler-free hints.

Every function degrades gracefully: with no NVIDIA_API_KEY, or on any API error,
callers get None and fall back to the tag-based scores / hand-written hints.
"""

import json
import os
import re

import requests

BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELS = [
    m for m in [
        os.getenv("NEMOTRON_MODEL"),
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-nano-3-30b-a3b",
    ] if m
]

# Words too generic to count as a spoiler on their own.
GENERIC = {
    "palace", "village", "park", "market", "street", "tower", "temple", "lake",
    "square", "museum", "hanok", "seoul", "korea", "garden", "stream", "station",
    "the", "and", "of", "line", "forest", "bridge", "library", "design", "plaza",
}

last_model_used = None


def available():
    return bool(os.getenv("NVIDIA_API_KEY"))


def _chat(system, user, max_tokens=2500, temperature=0.4):
    global last_model_used
    headers = {"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}"}
    err = None
    for model in MODELS:
        try:
            r = requests.post(BASE_URL, headers=headers, timeout=60, json={
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            if r.status_code in (401, 403):
                raise RuntimeError(f"NVIDIA API key rejected ({r.status_code})")
            r.raise_for_status()
            last_model_used = model
            return r.json()["choices"][0]["message"].get("content") or ""
        except RuntimeError:
            raise
        except Exception as e:  # try the next model
            err = e
    raise RuntimeError(f"All Nemotron models failed: {err}")


def _json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    return json.loads(m.group(0)) if m else None


def score_places(mood, pois):
    """Ask Nemotron how well each place fits a free-text mood. Returns {id: 0-10}."""
    catalog = "\n".join(
        f'- {p["id"]}: {p["name_en"]} — {p["reveal"]} (tags: {", ".join(p["tags"])})'
        for p in pois
    )
    system = ("You are a Seoul travel curator for foreign tourists. "
              "Score how well each place matches the traveler's mood. Reply with JSON only.")
    user = (f'Traveler mood: "{mood}"\n\nPlaces:\n{catalog}\n\n'
            'Return {"scores": {"<id>": <integer 0-10>, ...}} covering every id. '
            "10 = perfect match, 0 = wrong vibe.")
    data = _json(_chat(system, user, temperature=0.2))
    scores = (data or {}).get("scores", {})
    ids = {p["id"] for p in pois}
    return {k: max(0, min(10, int(v))) for k, v in scores.items() if k in ids} or None


def leaks(text, poi):
    """True if the text gives away the place's name."""
    low = text.lower()
    if poi["name_ko"].split()[0] in text:
        return True
    words = re.findall(r"[a-z0-9\-]{4,}", poi["name_en"].lower())
    return any(w in low for w in words if w not in GENERIC)


def write_hints(stops, lang, mood):
    """Spoiler-free hints + reveal text in the traveler's language.

    Returns {id: {"hint", "reveal", "tip"}} and a one-line teaser, or (None, None).
    """
    lines = "\n".join(
        f'{i + 1}. id={s.poi["id"]} | {s.poi["name_en"]} | facts: {s.poi["reveal"]} '
        f'Tip: {s.poi["tip"]}'
        for i, s in enumerate(stops)
    )
    system = ("You write playful riddle-style clues for a 'blind trip' in Seoul, where the "
              "traveler must NOT know the destination until arrival. Reply with JSON only.")
    user = (
        f"Traveler mood: {mood}\nWrite in: {lang}\n\nStops in order:\n{lines}\n\n"
        "For each stop write:\n"
        '- "hint": 1-2 intriguing sentences about what the traveler will experience. '
        "NEVER include the place name, neighborhood, district, station, or any proper noun "
        "that identifies it.\n"
        '- "reveal": 2 sentences introducing the place by name, shown after arrival.\n'
        '- "tip": 1 practical sentence.\n'
        'Also write "teaser": one sentence hyping the whole mystery trip without naming places.\n'
        'Format: {"teaser": "...", "stops": [{"id": "...", "hint": "...", "reveal": "...", "tip": "..."}]}'
    )
    data = _json(_chat(system, user, temperature=0.7))
    if not data:
        return None, None
    by_id = {s.poi["id"]: s.poi for s in stops}
    out = {}
    for item in data.get("stops", []):
        poi = by_id.get(item.get("id"))
        if not poi or not item.get("hint"):
            continue
        if leaks(item["hint"], poi):  # spoiler guard: keep the curated hint
            item["hint"] = None
        out[poi["id"]] = item
    return out, data.get("teaser")
