"""
PIVAS — Political Information Verification Assisted System
============================================================
Tangible artifact of the MIT 799 postgraduate project at Lagos State
University titled: "Deepfakes and the Spread of Political Misinformation:
Developing a Framework for Information Verification among Nigerian Social
Media Users."

PIVAS operationalises the Nigerian Information Verification Framework (NIVF)
described in Chapter 3 and Chapter 4 of the thesis. Users paste a suspicious
political claim, headline, or URL and receive a lightweight, colour-coded
verdict grounded in coverage by Nigerian fact-checkers and credible
mainstream media.

Search backends (both keyless, no API secret required):
1. Primary — ddgs (the new name of the duckduckgo-search library).
2. Fallback — Wikipedia OpenSearch API, always reachable, always keyless.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
import streamlit as st

# `ddgs` is the current package name; the previous `duckduckgo-search`
# releases now emit runtime errors on some networks. Import both and prefer
# ddgs if it is installed.
DDGS = None
try:
    from ddgs import DDGS  # noqa: F401
except Exception:
    try:
        from duckduckgo_search import DDGS  # noqa: F401
    except Exception:
        DDGS = None


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

APP_TITLE = "Political Information Verification Assisted System"
APP_TAGLINE = "Verify first, share responsibly"
APP_ACRONYM = "PIVAS"

# Platforms mirror those documented in Chapters 1, 3 and 4 of the thesis.
PLATFORMS = {
    "WhatsApp":    "whatsapp.com",
    "Facebook":    "facebook.com",
    "X (Twitter)": "x.com OR twitter.com",
    "Instagram":   "instagram.com",
    "TikTok":      "tiktok.com",
    "YouTube":     "youtube.com",
    "Telegram":    "t.me OR telegram.me",
}

# Trusted-source lists — Nigerian first (Chapter 5 §5.4 localisation).
TRUSTED_NG = [
    "dubawa.org", "africacheck.org", "cddwestafrica.org", "cjid.org",
    "premiumtimesng.com", "punchng.com", "vanguardngr.com",
    "thisdaylive.com", "guardian.ng", "channelstv.com", "arise.tv",
    "saharareporters.com", "dailytrust.com", "thecable.ng",
    "businessday.ng", "nairametrics.com", "leadership.ng",
]
TRUSTED_INTL = [
    "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com",
    "cnn.com", "aljazeera.com", "theguardian.com", "nytimes.com",
    "africanews.com", "aa.com.tr", "france24.com", "wikipedia.org",
]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def is_url(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    try:
        p = urlparse(text if "://" in text else "https://" + text)
        return bool(p.netloc) and "." in p.netloc
    except Exception:
        return False


def build_query(user_input: str, selected_platforms: list[str]) -> str:
    text = user_input.strip()
    if not text:
        return ""
    if selected_platforms:
        sites = " OR ".join(f"site:{PLATFORMS[p]}" for p in selected_platforms)
        return f"{text} ({sites})"
    return text


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


# ----------------------------------------------------------------------
# Search backends
# ----------------------------------------------------------------------

def ddg_search(query: str, max_results: int = 10) -> list[dict]:
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results, region="ng-en"))
    except Exception:
        try:  # Retry once without region — some DDG mirrors reject ng-en
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
        except Exception:
            return []
    # Normalise result shape (`ddgs` uses `href`, some versions use `link`).
    normalised = []
    for r in raw:
        normalised.append({
            "title": r.get("title") or r.get("name") or "(no title)",
            "href":  r.get("href")  or r.get("url")  or r.get("link") or "",
            "body":  r.get("body")  or r.get("snippet") or r.get("description") or "",
        })
    return [r for r in normalised if r["href"]]


def wikipedia_search(query: str, max_results: int = 8) -> list[dict]:
    """Keyless Wikipedia OpenSearch API fallback — always reachable."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": query,
                "format": "json", "srlimit": max_results, "utf8": 1,
            }, timeout=8,
        )
        if not r.ok:
            return []
        results = []
        for hit in r.json().get("query", {}).get("search", []):
            title = hit["title"]
            slug = title.replace(" ", "_")
            snippet = re.sub("<.*?>", "", hit.get("snippet", "")).strip()
            results.append({
                "title": title,
                "href":  f"https://en.wikipedia.org/wiki/{slug}",
                "body":  snippet + "…" if snippet else "",
            })
        return results
    except Exception:
        return []


def run_search(query: str, max_results: int = 10) -> tuple[list[dict], str]:
    """Try DDG first, then fall back to Wikipedia. Return (results, backend)."""
    results = ddg_search(query, max_results=max_results)
    if results:
        return results, "DuckDuckGo (ddgs)"
    fallback = wikipedia_search(query, max_results=max_results)
    if fallback:
        return fallback, "Wikipedia (fallback)"
    return [], "none"


# ----------------------------------------------------------------------
# Verdict logic
# ----------------------------------------------------------------------

def score_results(results: list[dict]) -> dict:
    ng_hits, intl_hits, other_hits = [], [], []
    for r in results:
        dom = domain_of(r.get("href", ""))
        if any(dom.endswith(t) for t in TRUSTED_NG):
            ng_hits.append(r)
        elif any(dom.endswith(t) for t in TRUSTED_INTL):
            intl_hits.append(r)
        else:
            other_hits.append(r)

    total_trusted = len(ng_hits) + len(intl_hits)

    if total_trusted >= 2 and ng_hits:
        verdict, colour, icon = "LIKELY AUTHENTIC", "#2E7D32", "✅"
        note = ("Multiple credible Nigerian and/or international sources are "
                "reporting on this. Cross-check the specific claim before sharing.")
    elif total_trusted >= 2:
        verdict, colour, icon = "PROBABLY AUTHENTIC — verify locally", "#558B2F", "🟢"
        note = ("International coverage exists but no Nigerian outlet has picked "
                "it up yet. Search Dubawa or Africa Check for a local check.")
    elif total_trusted == 1:
        verdict, colour, icon = "INCONCLUSIVE — verify further", "#EF6C00", "⚠️"
        note = ("Only one credible source found. Do not share until you have "
                "confirmed the claim with a second independent source.")
    else:
        verdict, colour, icon = "SUSPECT — likely misleading or fabricated", "#C62828", "🚫"
        note = ("No trusted Nigerian or international coverage found. Treat this "
                "as suspect and check a Nigerian fact-checking organisation "
                "(Dubawa, Africa Check, CDD, CJID) before you share.")

    return {"verdict": verdict, "colour": colour, "icon": icon, "note": note,
            "ng_hits": ng_hits, "intl_hits": intl_hits, "other_hits": other_hits}


# ----------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_ACRONYM} — {APP_TITLE}",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Global styling ---------------------------------------------------
# Cyan page background for readable contrast; larger hero title;
# single continuous card so no white separator appears between the
# header and the search area.
st.markdown("""
<style>
  html, body, [data-testid="stAppViewContainer"] {
    background: rgba(0, 0, 0, 0.88) !important;   /* black with light opacity */
    color: #F5F5F5;
  }
  [data-testid="stHeader"] { background: transparent; }
  /* Make Streamlit's own text elements readable on the dark surface */
  .stMarkdown, .stCaption, label, .stCheckbox label,
  [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
    color: #F5F5F5 !important;
  }
  /* Input field on the dark background */
  .stTextInput > div > div > input {
    background: rgba(255, 255, 255, 0.08);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.22);
  }
  .stTextInput > div > div > input::placeholder { color: rgba(255, 255, 255, 0.55); }
  /* Streamlit warning / info / error banners keep their intended colours */
  .block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 2rem;
    max-width: 1000px;
  }
  /* Combined hero + input surface — no gap between them */
  .pivas-shell {
    border-radius: 20px;
    box-shadow: 0 10px 32px rgba(0, 60, 90, 0.14);
    overflow: hidden;
    margin-bottom: 1.4rem;
  }
  .pivas-hero {
    background: linear-gradient(135deg, #0B3D91 0%, #1F6FEB 55%, #00B58A 100%);
    color: white;
    padding: 2.4rem 2.4rem 2rem 2.4rem;
    text-align: center;
  }
  .pivas-hero .badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 999px;
    background: rgba(255,255,255,0.22);
    font-size: 0.85rem;
    letter-spacing: 0.15em;
    margin-bottom: 0.6rem;
  }
  .pivas-hero h1 {
    color: white;
    font-size: 3.1rem;     /* enlarged logo/title */
    font-weight: 800;
    margin: 0.15rem 0 0.35rem 0;
    line-height: 1.1;
    letter-spacing: -0.5px;
  }
  .pivas-hero .shield {
    font-size: 3.2rem;     /* larger shield icon */
    display: block;
    line-height: 1;
    margin-bottom: 0.35rem;
  }
  .pivas-hero p {
    color: rgba(255,255,255,0.95);
    margin: 0;
    font-size: 1.15rem;
    font-style: italic;
  }
  /* The input section shares the same shell as the hero — no separator */
  .pivas-input {
    background: #FFFFFF;
    padding: 1.4rem 1.8rem 0.4rem 1.8rem;
  }
  /* Slim divider between hero and input, if any spacing shows in Streamlit */
  .pivas-input-top {
    height: 4px;
    background: linear-gradient(90deg, #0B3D91, #00B58A);
  }
  .pivas-plat-label {
    font-weight: 600;
    color: #7CC9FF;             /* light blue reads well on dark */
    margin: 0.9rem 0 0.35rem 0;
  }
  .pivas-verdict {
    padding: 1.15rem 1.4rem;
    border-radius: 14px;
    color: white;
    font-size: 1.2rem;
    font-weight: 700;
    margin: 1rem 0;
    box-shadow: 0 4px 14px rgba(0,0,0,0.10);
  }
  .pivas-verdict small {
    display: block; font-weight: 400; margin-top: 0.35rem;
    opacity: 0.96; font-size: 0.95rem;
  }
  .stButton>button {
    background: #0B3D91;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.55rem 1.5rem;
    font-weight: 600;
  }
  .stButton>button:hover { background: #1F6FEB; color: white; }
  a { text-decoration: none; }
  .pivas-card-out {
    background: rgba(255,255,255,0.06);       /* subtle glassy card on dark */
    border-radius: 14px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1rem;
    border: 1px solid rgba(255,255,255,0.10);
  }
  .pivas-footer {
    color: rgba(255,255,255,0.75);
    font-size: 0.85rem;
    margin-top: 2rem;
    text-align: center;
  }
</style>
""", unsafe_allow_html=True)

# --- Combined hero + input, no separator gap --------------------------
st.markdown(f"""
<div class="pivas-shell">
  <div class="pivas-hero">
    <span class="shield">🛡️</span>
    <span class="badge">{APP_ACRONYM}</span>
    <h1>{APP_TITLE}</h1>
    <p>{APP_TAGLINE}</p>
  </div>
  <div class="pivas-input-top"></div>
</div>
""", unsafe_allow_html=True)

# --- Input controls (native Streamlit widgets, no wrapping div) -------
query_input = st.text_input(
    "Paste a link or type a headline / claim to verify",
    placeholder="e.g. https://example.com/story  —  or —  'President cancels 2027 elections'",
    key="pivas_query",
)

st.markdown('<p class="pivas-plat-label">Restrict search to social media platforms (optional):</p>',
            unsafe_allow_html=True)

plat_cols = st.columns(4)
selected: list[str] = []
platforms_list = list(PLATFORMS.keys())
for idx, name in enumerate(platforms_list):
    with plat_cols[idx % 4]:
        if st.checkbox(name, key=f"plat_{name}"):
            selected.append(name)

st.caption(
    "Leave every box unticked to run an open web search across trusted Nigerian and "
    "international fact-checking / news sources."
)

verify_clicked = st.button("🔍  Verify")

# --- Search + verdict -------------------------------------------------
if verify_clicked:
    if not query_input.strip():
        st.warning("Please paste a link or type a claim to verify.")
    else:
        input_mode = "URL" if is_url(query_input) else "text claim"
        st.info(f"Interpreted as **{input_mode}** — running verification...")

        with st.spinner("Consulting trusted Nigerian and international sources..."):
            query = build_query(query_input, selected)
            results, backend = run_search(query, max_results=10)

        st.caption(f"Search backend used: **{backend}**")

        if not results:
            st.error(
                "No results were returned by any keyless backend. This is often "
                "temporary (DuckDuckGo rate-limits from time to time). Try again "
                "in a few seconds, use a shorter query, or untick any selected "
                "social-media filter. WhatsApp content is end-to-end encrypted "
                "and cannot be indexed by public search."
            )
        else:
            scored = score_results(results)

            # Verdict banner
            st.markdown(
                f'<div class="pivas-verdict" style="background:{scored["colour"]}">'
                f'{scored["icon"]}&nbsp; {scored["verdict"]}'
                f'<small>{scored["note"]}</small></div>',
                unsafe_allow_html=True,
            )

            colA, colB, colC = st.columns(3)
            colA.metric("🇳🇬 Nigerian trusted", len(scored["ng_hits"]))
            colB.metric("🌍 International trusted", len(scored["intl_hits"]))
            colC.metric("Other results", len(scored["other_hits"]))

            def render_hits(title: str, hits: list[dict]):
                if not hits:
                    return
                st.markdown(f"### {title}")
                for r in hits:
                    st.markdown(f"**[{r.get('title', '(no title)')}]({r.get('href', '#')})**")
                    body = re.sub(r"\s+", " ", r.get("body", "") or "").strip()
                    if body:
                        st.caption(body[:280] + ("..." if len(body) > 280 else ""))
                    dom = domain_of(r.get("href", ""))
                    if dom:
                        st.caption(f"↪ {dom}")

            render_hits("🇳🇬  Nigerian trusted coverage", scored["ng_hits"])
            render_hits("🌍  International trusted coverage", scored["intl_hits"])
            with st.expander("Other search results"):
                render_hits("Other results", scored["other_hits"])

# --- Footer -----------------------------------------------------------
st.markdown(
    f'<div class="pivas-footer">'
    f'{APP_ACRONYM} · Built for the MIT 799 project at Lagos State University · '
    f'Verify first, share responsibly.'
    f'</div>',
    unsafe_allow_html=True,
)
