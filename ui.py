"""Visual layer: warm cream design system (tokens, CSS, illustration, HTML blocks)."""

import base64
from html import escape

TOKENS = {
    "canvas": "#fffaf0", "surface-soft": "#faf5e8", "surface-card": "#f5f0e0",
    "surface-strong": "#ebe6d6", "hairline": "#e5e5e5",
    "ink": "#0a0a0a", "body-strong": "#1a1a1a", "body": "#3a3a3a",
    "muted": "#6a6a6a", "muted-soft": "#9a9a9a", "on-dark": "#ffffff",
    # soft pastel card fills: calm on a phone screen, ink text on all of them
    "pink": "#ffdbe6", "teal": "#d6eae3", "lavender": "#e6defa",
    "peach": "#ffe4d2", "ochre": "#f7e8b8", "mint": "#a4d4c5", "coral": "#ff6b5a",
}

# Saturated card rotation; never the same color twice in a row.
CARD_COLORS = ["pink", "teal", "lavender", "peach", "ochre", "cream"]
DARK_CARDS = set()  # all pastel cards take ink text

_vars = "\n".join(f"  --{k}: {v};" for k, v in TOKENS.items())

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700&display=swap');
:root {{
{_vars}
  --r-xs: 6px; --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-xl: 24px; --r-pill: 9999px;
}}
.stApp {{ background: var(--canvas); color: var(--body); }}
[data-testid="stHeader"] {{ background: var(--canvas); }}
[data-testid="stSidebar"] {{ background: var(--surface-soft); border-right: 1px solid var(--hairline); }}
[data-testid="stMainBlockContainer"] {{ padding-top: 96px; padding-bottom: 48px; }}

/* ---------- type ---------- */
.bt-label {{ font-size: 12px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase;
            color: var(--muted); margin: 0 0 12px; }}
.bt-display-xl {{ font-size: 72px; font-weight: 500; line-height: 1.0; letter-spacing: -2.5px;
                 color: var(--ink); margin: 0; }}
.bt-display-md {{ font-size: 40px; font-weight: 500; line-height: 1.1; letter-spacing: -1px;
                 color: var(--ink); margin: 0; }}
.bt-display-sm {{ font-size: 32px; font-weight: 500; line-height: 1.15; letter-spacing: -0.5px;
                 color: var(--ink); margin: 0; }}
.bt-title-md {{ font-size: 18px; font-weight: 600; line-height: 1.4; margin: 0; }}
.bt-lead {{ font-size: 18px; line-height: 1.55; color: var(--body-strong); margin: 20px 0 0; max-width: 34em; }}
.bt-body {{ font-size: 16px; line-height: 1.55; color: var(--body); margin: 0; }}
.bt-caption {{ font-size: 13px; font-weight: 500; color: var(--muted); margin: 4px 0 0; }}
.bt-ko {{ font-family: 'Noto Sans KR', Inter, sans-serif; font-size: 30px; font-weight: 700;
         letter-spacing: -0.5px; color: var(--ink); margin: 8px 0 0; }}

/* ---------- hero ---------- */
.bt-hero {{ display: grid; grid-template-columns: 7fr 5fr; gap: 48px; align-items: center; margin-bottom: 48px; }}
.bt-illus {{ background: var(--surface-soft); border-radius: var(--r-xl); overflow: hidden; line-height: 0; }}
.bt-illus img {{ width: 100%; height: auto; display: block; }}

/* ---------- feature cards ---------- */
.bt-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 48px 0 0; }}
.bt-card {{ border-radius: var(--r-xl); padding: 32px; color: var(--ink); }}
.bt-card .bt-body {{ color: inherit; opacity: .85; margin-top: 8px; }}
.bt-card.pink {{ background: var(--pink); }}
.bt-card.teal {{ background: var(--teal); }}
.bt-card.lavender {{ background: var(--lavender); }}
.bt-card.peach {{ background: var(--peach); }}
.bt-card.ochre {{ background: var(--ochre); }}
.bt-card.cream {{ background: var(--surface-card); }}
.bt-frag {{ margin-top: 24px; background: rgba(255,255,255,.92); color: var(--ink); border-radius: var(--r-lg);
           padding: 16px; font-size: 14px; line-height: 1.5; }}
.bt-frag b {{ font-weight: 600; }}
.bt-pill {{ display: inline-block; font-size: 13px; font-weight: 500; line-height: 1.4; padding: 4px 12px;
           border-radius: var(--r-pill); background: var(--surface-card); color: var(--ink); margin: 0 6px 6px 0; }}
.bt-pill.on-dark {{ background: rgba(255,255,255,.18); color: var(--on-dark); }}
.bt-pill.on-light {{ background: rgba(10,10,10,.08); color: var(--ink); }}

/* ---------- stats row (stays 3-up on phones) ---------- */
.bt-statrow {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0 0 16px; }}
.bt-stat {{ background: var(--surface-card); border-radius: var(--r-lg); padding: 16px 20px; }}
.bt-stat .k {{ font-size: 13px; font-weight: 500; color: var(--muted); }}
.bt-stat .v {{ font-size: 28px; font-weight: 500; letter-spacing: -1px; color: var(--ink); margin-top: 4px; }}

/* ---------- bands ---------- */
.bt-band {{ background: var(--surface-soft); border-radius: var(--r-xl); padding: 32px; margin: 0 0 24px; }}
.bt-footer {{ background: var(--surface-soft); border-radius: var(--r-xl); padding: 48px 32px; margin-top: 96px;
             display: flex; justify-content: space-between; gap: 24px; flex-wrap: wrap; }}
.bt-footer p {{ font-size: 14px; color: var(--muted); margin: 0; }}
.bt-footer .bt-title-md {{ color: var(--ink); }}

/* ---------- passport ---------- */
.bt-passport {{ background: var(--teal); color: var(--ink); border-radius: var(--r-xl); padding: 32px; }}
.bt-stats {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0 24px; font-size: 14px; opacity: .85; }}
.bt-stamps {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 16px; }}
.bt-stamp {{ border: 2px dashed currentColor; border-radius: var(--r-lg); padding: 14px; text-align: center;
            background: var(--canvas); }}
.bt-stamp .n {{ font-size: 12px; font-weight: 600; letter-spacing: 1.5px; }}
.bt-stamp .en {{ font-size: 14px; font-weight: 600; line-height: 1.3; margin: 6px 0 2px; color: var(--ink); }}
.bt-stamp .ko {{ font-family: 'Noto Sans KR', sans-serif; font-weight: 700; font-size: 16px; color: var(--ink); }}
.bt-stamp .t {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}

/* ---------- keyed Streamlit containers ---------- */
.st-key-planner {{ background: var(--surface-card); border-radius: var(--r-lg); padding: 32px; }}
.st-key-resume {{ background: var(--mint); border-radius: var(--r-lg); padding: 20px 24px; margin-bottom: 24px; }}
.st-key-judge {{ background: var(--surface-card); border-radius: var(--r-lg); padding: 32px; margin-top: 48px; }}
.st-key-reveal {{ background: var(--surface-card); border-radius: var(--r-xl); padding: 32px; }}
{"".join(f'''.st-key-stop-{c} {{ background: var(--{"surface-card" if c == "cream" else c}); border-radius: var(--r-xl); padding: 32px; }}
''' for c in CARD_COLORS)}
/* cream widgets inside dark cards keep ink text */
.st-key-stop-pink [data-testid="stExpander"] [data-testid="stMarkdownContainer"] *,
.st-key-stop-teal [data-testid="stExpander"] [data-testid="stMarkdownContainer"] *,
.st-key-stop-pink [data-testid="stExpander"] summary *, .st-key-stop-teal [data-testid="stExpander"] summary *,
.st-key-stop-pink [data-testid="stCameraInput"] *, .st-key-stop-teal [data-testid="stCameraInput"] *,
.st-key-stop-pink [data-testid="stFileUploaderDropzone"] *, .st-key-stop-teal [data-testid="stFileUploaderDropzone"] * {{
  color: var(--ink) !important; }}
.bt-hint {{ font-size: 26px; font-weight: 500; line-height: 1.3; letter-spacing: -0.4px; margin: 16px 0 8px; }}

/* ---------- widgets ---------- */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"],
[data-testid="stBaseLinkButton-secondary"], [data-testid="stBaseLinkButton-primary"] {{
  min-height: 44px; border-radius: var(--r-md); font-weight: 600; font-size: 14px; }}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primary"]:focus:not(:active) {{
  background: var(--ink); border-color: var(--ink); color: var(--on-dark); }}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"] {{
  background: var(--canvas); border: 1px solid var(--hairline); color: var(--ink); }}
/* on saturated cards: filled white primary, outlined secondary */
[class*="st-key-stop-"] [data-testid="stBaseButton-primary"],
[class*="st-key-stop-"] [data-testid="stBaseButton-primary"]:hover {{
  background: #fff; border-color: #fff; color: var(--ink); }}
[class*="st-key-stop-"] [data-testid="stBaseButton-primary"] * {{ color: var(--ink) !important; }}
[class*="st-key-stop-"] [data-testid="stBaseLinkButton-secondary"],
[class*="st-key-stop-"] [data-testid="stBaseButton-secondary"],
[class*="st-key-stop-"] [data-testid="stPopover"] button {{
  background: transparent; border: 1px solid currentColor; color: inherit; min-height: 40px; border-radius: var(--r-md); }}

[data-testid="stButtonGroup"] button {{ border-radius: var(--r-pill); padding: 8px 16px; min-height: 40px;
  background: transparent; border: 1px solid var(--hairline); color: var(--muted); }}
[data-testid="stBaseButton-pillsActive"] {{ background: var(--canvas) !important; border-color: var(--ink) !important;
  color: var(--ink) !important; }}
[data-testid="stBaseButton-pillsActive"] * {{ color: var(--ink) !important; }}

[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="input"] input {{
  background: var(--canvas) !important; }}
[data-baseweb="input"], [data-baseweb="select"] > div {{ border-radius: var(--r-md) !important; min-height: 44px; }}
[data-testid="stWidgetLabel"] p {{ font-weight: 500; color: var(--body-strong); }}

[data-testid="stMetric"] {{ background: var(--surface-card); border-radius: var(--r-lg); padding: 16px 24px; }}
[data-testid="stMetricValue"] {{ font-weight: 500; letter-spacing: -1px; }}
[data-testid="stExpander"] details {{ border-radius: var(--r-lg); border: 1px solid var(--hairline); background: var(--canvas); }}

@media (max-width: 1024px) {{ .bt-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 768px) {{
  .bt-hero {{ grid-template-columns: 1fr; gap: 32px; }}
  .bt-display-xl {{ font-size: 40px; letter-spacing: -1.2px; }}
  .bt-display-md {{ font-size: 30px; }}
  .bt-grid {{ grid-template-columns: 1fr; }}
  .bt-hint {{ font-size: 21px; }}
  [data-testid="stMainBlockContainer"] {{ padding: 72px 12px 32px; }}
  .bt-band {{ padding: 20px; }}
  .bt-stat {{ padding: 12px; }}
  .bt-stat .v {{ font-size: 20px; }}
  .bt-footer {{ margin-top: 48px; padding: 32px 20px; }}
  .bt-card, .st-key-planner, .st-key-reveal, [class*="st-key-stop-"] {{ padding: 24px; }}
}}
</style>
"""


def width_css(px):
    return f'<style>[data-testid="stMainBlockContainer"] {{ max-width: {px}px; }}</style>'


# Soft, clay-like Seoul scene: shaded hills, a tower on the peak, and a curious map-pin mascot.
ILLUSTRATION = """
<svg viewBox="0 0 480 380" width="480" height="380" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Clay-style Seoul hills with a tower and a map-pin mascot">
 <defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#efe7ff"/><stop offset="1" stop-color="#faf5e8"/></linearGradient>
  <radialGradient id="sun" cx=".35" cy=".3" r=".75"><stop offset="0" stop-color="#ffe3a0"/><stop offset=".6" stop-color="#e8b94a"/><stop offset="1" stop-color="#c9952c"/></radialGradient>
  <linearGradient id="lav" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#d6caf7"/><stop offset="1" stop-color="#9884d6"/></linearGradient>
  <linearGradient id="pch" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffcfae"/><stop offset="1" stop-color="#f08f5e"/></linearGradient>
  <linearGradient id="mnt" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c3e6da"/><stop offset="1" stop-color="#7fb8a6"/></linearGradient>
  <radialGradient id="pin" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#ff8db4"/><stop offset=".55" stop-color="#ff4d8b"/><stop offset="1" stop-color="#d42f6b"/></radialGradient>
  <filter id="soft" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="#5a3a2a" flood-opacity=".18"/></filter>
 </defs>
 <rect width="480" height="380" fill="url(#sky)"/>
 <circle cx="372" cy="92" r="42" fill="url(#sun)" filter="url(#soft)"/>
 <path d="M-20 300 C 60 170, 130 150, 210 250 C 260 190, 330 150, 500 280 L 500 380 L -20 380 Z" fill="url(#lav)"/>
 <path d="M60 330 C 140 200, 200 150, 262 150 C 320 150, 380 230, 470 330 L 470 380 L 60 380 Z" fill="url(#pch)"/>
 <g filter="url(#soft)">
  <rect x="256" y="96" width="12" height="58" rx="5" fill="#fffaf0"/>
  <rect x="246" y="100" width="32" height="14" rx="7" fill="#1a3a3a"/>
  <rect x="259" y="66" width="6" height="34" rx="3" fill="#fffaf0"/>
  <circle cx="262" cy="64" r="4" fill="#ff6b5a"/>
 </g>
 <path d="M-20 350 C 80 290, 170 300, 240 330 C 320 300, 410 290, 500 340 L 500 380 L -20 380 Z" fill="url(#mnt)"/>
 <ellipse cx="128" cy="330" rx="34" ry="8" fill="#5a3a2a" opacity=".15"/>
 <g filter="url(#soft)">
  <path d="M128 322 C 108 294, 92 276, 92 252 C 92 230, 108 214, 128 214 C 148 214, 164 230, 164 252 C 164 276, 148 294, 128 322 Z" fill="url(#pin)"/>
  <ellipse cx="114" cy="232" rx="10" ry="6" fill="#fff" opacity=".45" transform="rotate(-30 114 232)"/>
  <circle cx="117" cy="252" r="5" fill="#0a0a0a"/><circle cx="139" cy="252" r="5" fill="#0a0a0a"/>
  <circle cx="118.5" cy="250.5" r="1.6" fill="#fff"/><circle cx="140.5" cy="250.5" r="1.6" fill="#fff"/>
  <path d="M121 266 Q 128 272 135 266" stroke="#0a0a0a" stroke-width="3" fill="none" stroke-linecap="round"/>
 </g>
 <g filter="url(#soft)">
  <circle cx="186" cy="196" r="20" fill="#fffaf0"/>
  <text x="186" y="204" text-anchor="middle" font-family="Inter, sans-serif" font-size="24" font-weight="600" fill="#1a3a3a">?</text>
 </g>
</svg>
"""


ILLUSTRATION_SRC = "data:image/svg+xml;base64," + base64.b64encode(ILLUSTRATION.strip().encode()).decode()


def hero():
    return f"""
<div class="bt-hero">
  <div>
    <p class="bt-label">📦 Unboxing Seoul</p>
    <h1 class="bt-display-xl">Pick a mood.<br>We hide the destinations.</h1>
    <p class="bt-lead">Follow the map one secret stop at a time. Each place stays a mystery until you arrive.</p>
  </div>
  <div class="bt-illus"><img src="{ILLUSTRATION_SRC}" alt="Clay-style Seoul hills with a tower and a map-pin mascot"></div>
</div>
"""


def how_it_works():
    return """
<div class="bt-grid">
  <div class="bt-card pink">
    <p class="bt-title-md">1 · Choose a mood</p>
    <p class="bt-body">Healing, landmarks, food, night views, or describe it in your own words.</p>
    <div class="bt-frag"><span class="bt-pill">🌿 Healing</span><span class="bt-pill">🍽️ Meal stop</span><span class="bt-pill">🎟️ Activity</span></div>
  </div>
  <div class="bt-card teal">
    <p class="bt-title-md">2 · Follow secret stops</p>
    <p class="bt-body">Nemotron writes the riddles, the optimizer times every stop around opening hours.</p>
    <div class="bt-frag"><b>🔒 Secret Stop 2</b><br>🚇 ~18 min by subway · arrive ≈ 11:30<br>“Kings once ruled from here…”</div>
  </div>
  <div class="bt-card lavender">
    <p class="bt-title-md">3 · Reveal on arrival</p>
    <p class="bt-body">Tap “I've arrived” and the place reveals itself, with its Korean name to show locals.</p>
    <div class="bt-frag"><b>🎉 Gyeongbokgung Palace</b><br><span style="font-family:'Noto Sans KR',sans-serif;font-weight:700;font-size:18px">경복궁</span></div>
  </div>
</div>
"""


def footer():
    return """
<div class="bt-footer">
  <div><p class="bt-title-md">📦 Unboxing Seoul</p><p>Pick a mood. Unbox Seoul one secret stop at a time.</p></div>
  <div><p>Built with NVIDIA Nemotron · cuOpt routing</p><p>Places, hours and travel times are approximate.</p></div>
</div>
"""


STAMP_INK = {"pink": "#ff4d8b", "teal": "#1a3a3a", "lavender": "#7a62c9", "peach": "#e0703c",
             "ochre": "#b8871a", "cream": "#6a6a6a"}


def passport(stops, date_label, mood, km, hours, fmt_time):
    stamps = "".join(
        f'<div class="bt-stamp" style="color:{STAMP_INK[CARD_COLORS[k % len(CARD_COLORS)]]};'
        f'transform:rotate({(-3, 2, -1, 3, -2, 1)[k % 6]}deg)">'
        f'<div class="n">STOP {k + 1}</div><div class="en">{escape(s.poi["name_en"])}</div>'
        f'<div class="ko">{escape(s.poi["name_ko"])}</div><div class="t">{fmt_time(s.arrive)}</div></div>'
        for k, s in enumerate(stops))
    return f"""
<div class="bt-passport">
  <p class="bt-label">Unboxing Seoul · Passport</p>
  <h2 class="bt-display-sm">Trip complete 🎉</h2>
  <div class="bt-stats"><span>📅 {escape(date_label)}</span><span>✨ {escape(mood)}</span>
    <span>📍 {len(stops)} secret stops</span><span>🚶 {km:.1f} km</span><span>⏱️ {hours:.1f} h</span></div>
  <div class="bt-stamps">{stamps}</div>
</div>
"""


SPEECH_LANG = {"English": "en-US", "日本語": "ja-JP", "简体中文": "zh-CN", "Español": "es-ES",
               "Français": "fr-FR", "한국어": "ko-KR"}


def _js_string(value):
    """JSON-encode for inline <script>; escape <, >, & so text can't close the tag."""
    import json
    return (json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def speak_button(text, lang, dark):
    """Small in-browser text-to-speech button (Web Speech API).

    `text` may come from the LLM, so it only ever enters the page via _js_string.
    """
    color = "#ffffff" if dark else "#0a0a0a"
    return f"""
<button id="say" style="font:600 14px Inter,sans-serif;color:{color};background:transparent;
  border:1px solid {color};border-radius:12px;padding:8px 16px;cursor:pointer;width:100%;min-height:40px">
  🔊 Read the clue aloud</button>
<script>
document.getElementById('say').onclick = () => {{
  const u = new SpeechSynthesisUtterance({_js_string(text)});
  u.lang = {_js_string(SPEECH_LANG.get(lang, "en-US"))}; u.rate = 0.95;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}};
</script>
<style>body{{margin:0;background:transparent}}</style>
"""


def stats(items):
    return '<div class="bt-statrow">' + "".join(
        f'<div class="bt-stat"><div class="k">{escape(str(k))}</div><div class="v">{escape(str(v))}</div></div>'
        for k, v in items) + "</div>"


def pills(items, tone=""):
    return "".join(f'<span class="bt-pill {tone}">{escape(t)}</span>' for t in items if t)


def text(s):
    return escape(s or "")
