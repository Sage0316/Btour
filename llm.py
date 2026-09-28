"""Nemotron (build.nvidia.com) calls: mood -> place scores, and spoiler-free hints.

Every function degrades gracefully: with no NVIDIA_API_KEY, or on any API error,
callers get None and fall back to the tag-based scores / hand-written hints.
"""

import base64
import io
import json
import os
import re

import requests

BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELS = [
    m for m in [
        os.getenv("NEMOTRON_MODEL"),
        "nvidia/nemotron-3-super-120b-a12b",      # fastest in our timing (~3 s per clue)
        "nvidia/nemotron-3.5-lightning-30b-a3b",
    ] if m
]

# Words too generic to count as a spoiler on their own.
GENERIC = {
    "palace", "village", "park", "market", "street", "tower", "temple", "lake",
    "square", "museum", "hanok", "seoul", "korea", "garden", "stream", "station",
    "the", "and", "of", "line", "forest", "bridge", "library", "design", "plaza",
    "city", "tour", "loop", "course", "near", "rental", "ride", "river", "night", "coin",
}

last_model_used = None


def available():
    return bool(os.getenv("NVIDIA_API_KEY"))


VISION_MODELS = [
    m for m in [
        os.getenv("NEMOTRON_VISION_MODEL"),
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "meta/llama-3.2-11b-vision-instruct",
    ] if m
]


def _chat(system, user, max_tokens=2500, temperature=0.4, models=None, timeout=60):
    global last_model_used
    headers = {"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}"}
    err = None
    for model in models or MODELS:
        try:
            body = {
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if model.startswith("nvidia/nemotron"):
                # Nemotron reasons at length by default (70s+); we only need the JSON answer.
                body["chat_template_kwargs"] = {"enable_thinking": False}
            r = requests.post(BASE_URL, headers=headers, timeout=timeout, json=body)
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
    data = _json(_chat(system, user, max_tokens=1500, temperature=0.2, timeout=45))
    scores = (data or {}).get("scores", {})
    ids = {p["id"] for p in pois}
    return {k: max(0, min(10, int(v))) for k, v in scores.items() if k in ids} or None


def leaks(text, poi):
    """True if the text gives away the place's name."""
    low = text.lower()
    if poi["name_ko"].split()[0] in text:
        return True
    full = re.sub(r"\s*\(.*?\)", "", poi["name_en"]).lower()
    if full in low:  # names made only of common words, e.g. "Seoul City Tour Bus"
        return True
    words = re.findall(r"[a-z0-9\-]{4,}", poi["name_en"].lower())
    return any(w in low for w in words if w not in GENERIC)


DIFFICULTY = {
    "Easy": ("Say plainly what kind of place it is and two things the traveler will see there. "
             "No metaphors."),
    "Medium": ("Name two concrete things the traveler will SEE on arrival (buildings, objects, food, "
               "people doing something) so they can recognize it. Plain words, at most one light image."),
    "Hard": "Make it a cryptic riddle built on metaphor; avoid obvious category words.",
}


HINT_SYSTEM = ("You write clues for a 'blind trip' in Seoul: the traveler must NOT know the destination "
               "until arrival, but must be able to recognize it when they get there. Write in plain, "
               "concrete language a tourist can act on, not poetry. Reply with JSON only.")


LANG_NAMES = {"日本語": "Japanese (日本語)", "简体中文": "Simplified Chinese (简体中文)", "Español": "Spanish",
              "Français": "French", "한국어": "Korean (한국어)", "English": "English"}
CJK = {"日本語": (0x3040, 0x30FF), "简体中文": (0x4E00, 0x9FFF), "한국어": (0xAC00, 0xD7A3)}


def _in_language(text, lang):
    """Cheap check that a CJK-language reply is actually written in that script."""
    if lang not in CJK or not text:
        return True
    lo, hi = CJK[lang]
    return sum(lo <= ord(c) <= hi for c in text) >= 3


def _one_stop(stop, lang, mood, difficulty):
    p = stop.poi
    lang_name = LANG_NAMES.get(lang, lang)
    walk = f"\nWalking clue to translate: {p['approach']['clue']}" if p.get("approach") else ""
    user = (
        f"Traveler mood: {mood}\nWrite in: {lang_name}\n"
        f"Place: {p['name_en']} | facts: {p['reveal']} | tip: {p['tip']}{walk}\n\n"
        'Return {"hint": "...", "reveal": "...", "tip": "..."' + (', "walk": "..."' if walk else "") + "}.\n"
        '- "hint": 1-2 short sentences describing what the traveler will find there. NEVER include the '
        f"place name, neighborhood, district, station, or any identifying proper noun. {DIFFICULTY.get(difficulty, '')}\n"
        '- "reveal": 2 sentences introducing the place by name, shown after arrival.\n'
        '- "tip": 1 practical sentence.'
        + ('\n- "walk": translate the walking clue faithfully, keeping directions exact.' if walk else "")
        + "\nDo not use superlatives or facts that single the place out (oldest, biggest, tallest, most famous)."
        + f"\nIMPORTANT: write every field in {lang_name} only."
    )
    item = {}
    for _ in range(2):  # the model occasionally ignores the language; retry once
        item = _json(_chat(HINT_SYSTEM, user, max_tokens=600, temperature=0.7, timeout=40)) or {}
        if _in_language(item.get("hint"), lang):
            break
    if not _in_language(item.get("hint"), lang):
        return {}
    if item.get("hint") and leaks(item["hint"], p):  # spoiler guard: keep the curated hint
        item["hint"] = None
    if item.get("walk") and leaks(item["walk"], p):
        item["walk"] = None
    return item


def _teaser(stops, lang, mood):
    user = (f"Traveler mood: {mood}. In {LANG_NAMES.get(lang, lang)}, write ONE exciting sentence hyping a {len(stops)}-stop "
            'mystery trip in Seoul without naming any place. Return {"teaser": "..."}')
    return (_json(_chat(HINT_SYSTEM, user, max_tokens=150, temperature=0.8, timeout=40)) or {}).get("teaser")


def write_hints(stops, lang, mood, difficulty="Medium", teaser=True):
    """Spoiler-free hints + reveal text in the traveler's language, one request per stop in parallel.

    Returns ({id: {"hint", "reveal", "tip", "walk"}}, teaser).
    """
    from concurrent.futures import ThreadPoolExecutor

    def safe(fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            return e

    with ThreadPoolExecutor(max_workers=min(6, len(stops) + 1)) as pool:
        teaser_job = pool.submit(safe, _teaser, stops, lang, mood) if teaser else None
        jobs = [pool.submit(safe, _one_stop, s, lang, mood, difficulty) for s in stops]
        results = [j.result() for j in jobs]
        teaser = teaser_job.result() if teaser_job else None
    out = {s.poi["id"]: r for s, r in zip(stops, results) if isinstance(r, dict) and r}
    if not out:
        errors = [r for r in results if isinstance(r, Exception)]
        raise RuntimeError(f"no clues generated ({errors[0] if errors else 'empty replies'})")
    return out, teaser if isinstance(teaser, str) else None


def _jpeg_data_url(image_bytes, max_side=768):
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def check_photo(image_bytes, mission):
    """Ask a vision model whether the photo fulfils the mission. Returns (passed, comment)."""
    system = "You judge photo missions in a playful travel game. Be lenient and friendly. Reply with JSON only."
    user = [
        {"type": "text", "text": (
            f"Mission: {mission}\nDoes this photo reasonably fulfil the mission? "
            'Reply {"pass": true|false, "comment": "<one short friendly sentence about the photo>"}. '
            "Do not name or guess the specific place.")},
        {"type": "image_url", "image_url": {"url": _jpeg_data_url(image_bytes)}},
    ]
    data = _json(_chat(system, user, max_tokens=1500, temperature=0.2, models=VISION_MODELS)) or {}
    return bool(data.get("pass", True)), data.get("comment") or "Nice shot!"
