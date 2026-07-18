"""
PIVAS — Political Information Verification Assisted System
============================================================
The tangible artifact of the MIT 799 postgraduate project at Lagos State
University titled: "Deepfakes and the Spread of Political Misinformation:
Developing a Framework for Information Verification among Nigerian Social
Media Users."

PIVAS operationalises the Nigerian Information Verification Framework (NIVF)
described in Chapter 3 and Chapter 4 of the thesis. It lets ordinary
Nigerian social-media users paste a suspicious political claim, headline or
URL and receive a lightweight verification verdict grounded in coverage by
Nigerian fact-checking organisations and credible mainstream media.

Design notes:
- Uses DuckDuckGo (via the `duckduckgo-search` library) for keyless search,
  so the app can be hosted on Streamlit Community Cloud without needing any
  API secret.
- Optional per-platform filters restrict the query to a specific social
  media domain via a `site:` filter. WhatsApp is included in the UI but is
  end-to-end encrypted, so its filter falls back to whatsapp.com public
  channels only.
- The verdict logic prioritises Nigerian trusted sources first, then
  regional and international outlets, in line with the localisation
  argument in Chapter 5 §5.4.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
import streamlit as st

# duckduckgo-search may not be installed at first run; degrade gracefully.
try:
    from duckduckgo_search import DDGS
except Exception:  # pragma: no cover - handled at runtime
    DDGS = None


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

APP_TITLE = "Political Information Verification Assisted System"
APP_TAGLINE = "Verify first, share responsibly"
APP_ACRONYM = "PIVAS"

# Platforms mirror those documented in Chapters 1, 3 and 4 of the thesis.
PLATFORMS = {
    "WhatsApp":   "whatsapp.com",
    "Facebook":   "facebook.com",
    "X (Twitter)": "x.com OR twitter.com",
    "Instagram":  "instagram.com",
    "TikTok":     "tiktok.com",
    "YouTube":    "youtube.com",
    "Telegram":   "t.me OR telegram.me",
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
    "africanews.com", "aa.com.tr", "france24.com",
]
TRUSTED_ALL = TRUSTED_NG + TRUSTED_INTL


# ----------------------------------------------------------------------
# Search helpers (keyless)
# ----------------------------------------------------------------------

def is_url(text: str) -> bool:
    """Detect if the input looks like a URL."""
    text = text.strip()
    if not text:
        return False
    try:
        p = urlparse(text if "://" in text else "https://" + text)
        return bool(p.netloc) and "." in p.netloc
    except Exception:
        return False


def build_query(user_input: str, selected_platforms: list[str]) -> str:
    """Compose a DuckDuckGo query string.

    If the input is a URL the query is the URL itself. If platforms are
    selected, a boolean `site:` filter is appended so DDG only returns
    results from those domains.
    """
    text = user_input.strip()
    if not text:
        return ""

    if selected_platforms:
        sites = " OR ".join(f"site:{PLATFORMS[p]}" for p in selected_platforms)
        return f'{text} ({sites})'
    return text


def ddg_search(query: str, max_results: int = 8) -> list[dict]:
    """Run a keyless DuckDuckGo search. Returns a list of {title,href,body}."""
    if DDGS is None:
        st.error(
            "The `duckduckgo-search` library is not installed. "
            "Run `pip install duckduckgo-search`."
        )
        return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results, region="ng-en"))
    except Exception as exc:  # pragma: no cover
        st.error(f"Search backend error: {exc}")
        return []


# ----------------------------------------------------------------------
# Verdict logic — mirrors the NIVF Module 1 (Source Triangulation) +
# Module 2 (Lateral Reading) principles from Chapter 3 §3.5.
# ----------------------------------------------------------------------

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def score_results(results: list[dict]) -> dict:
    """Count trusted-source coverage and return a verdict payload."""
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
        verdict = "LIKELY AUTHENTIC"
        colour = "#2E7D32"
        icon = "✅"
        note = ("Multiple credible Nigerian and/or international sources are "
                "reporting on this. Cross-check the specific claim before sharing.")
    elif total_trusted >= 2:
        verdict = "PROBABLY AUTHENTIC — verify locally"
        colour = "#558B2F"
        icon = "🟢"
        note = ("International coverage exists but no Nigerian outlet has picked "
                "it up yet. Search Dubawa or Africa Check for a local check.")
    elif total_trusted == 1:
        verdict = "INCONCLUSIVE — verify further"
        colour = "#EF6C00"
        icon = "⚠️"
        note = ("Only one credible source found. Do not share until you have "
                "confirmed the claim with a second independent source.")
    else:
        verdict = "SUSPECT — likely misleading or fabricated"
        colour = "#C62828"
        icon = "🚫"
        note = ("No trusted Nigerian or international coverage found. Treat this "
                "as suspect and check a Nigerian fact-checking organisation "
                "(Dubawa, Africa Check, CDD, CJID) before you share.")

    return {
        "verdict": verdict, "colour": colour, "icon": icon, "note": note,
        "ng_hits": ng_hits, "intl_hits": intl_hits, "other_hits": other_hits,
    }


# ----------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_ACRONYM} — {APP_TITLE}",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Custom CSS for a cleaner look ---
st.markdown("""
<style>
  .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1000px; }
  .pivas-hero {
    background: linear-gradient(135deg, #0B3D91 0%, #1F6FEB 60%, #2E9E60 100%);
    color: white; padding: 2rem 2.4rem; border-radius: 18px; margin-bottom: 1.5rem;
    box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  }
  .pivas-hero h1 { color: white; font-size: 2rem; font-weight: 700; margin: 0 0 .35rem 0; }
  .pivas-hero p  { color: rgba(255,255,255,0.92); margin: 0; font-size: 1.05rem; }
  .pivas-hero .badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    background: rgba(255,255,255,0.18); font-size: .78rem; margin-bottom: .6rem;
  }
  .pivas-card {
    background: white; border: 1px solid #e6e8ec; border-radius: 14px;
    padding: 1.25rem 1.5rem; margin-bottom: 1rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
  }
  .pivas-verdict {
    padding: 1.1rem 1.4rem; border-radius: 14px; color: white;
    font-size: 1.15rem; font-weight: 600; margin: 1rem 0;
  }
  .pivas-verdict small { display:block; font-weight:400; margin-top:.3rem; opacity:.95; }
  .pivas-plat-label { font-weight:600; color:#0B3D91; margin: 0 0 .35rem 0; }
  a { text-decoration: none; }
  .stButton>button {
    background: #0B3D91; color: white; border: none; border-radius: 10px;
    padding: .55rem 1.4rem; font-weight: 600;
  }
  .stButton>button:hover { background: #1F6FEB; color:white; }
  .pivas-footer { color:#6b7280; font-size:.85rem; margin-top:2rem; text-align:center; }
</style>
""", unsafe_allow_html=True)

# --- Hero ---
st.markdown(f"""
<div class="pivas-hero">
  <span class="badge">🛡️ {APP_ACRONYM}</span>
  <h1>{APP_TITLE}</h1>
  <p><em>{APP_TAGLINE}</em></p>
</div>
""", unsafe_allow_html=True)

# --- Input card ---
st.markdown('<div class="pivas-card">', unsafe_allow_html=True)

query_input = st.text_input(
    "Paste a link or type a headline / claim to verify",
    placeholder="e.g. https://example.com/story  —  or —  'President cancels 2027 elections'",
    key="pivas_query",
)

st.markdown('<p class="pivas-plat-label">Restrict search to social media platforms (optional):</p>',
            unsafe_allow_html=True)

# 4 columns × 2 rows of platform checkboxes
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
st.markdown('</div>', unsafe_allow_html=True)


# --- Search + verdict ---
if verify_clicked:
    if not query_input.strip():
        st.warning("Please paste a link or type a claim to verify.")
    else:
        input_mode = "URL" if is_url(query_input) else "text claim"
        st.info(f"Interpreted as **{input_mode}** — running verification...")

        with st.spinner("Consulting trusted Nigerian and international sources..."):
            query = build_query(query_input, selected)
            results = ddg_search(query, max_results=10)

        if not results:
            st.error(
                "No results returned. If you selected a specific platform, "
                "try without it or with a shorter query. WhatsApp content is "
                "end-to-end encrypted and cannot be indexed by public search."
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

            # Coverage summary
            colA, colB, colC = st.columns(3)
            colA.metric("Nigerian trusted sources", len(scored["ng_hits"]))
            colB.metric("International trusted sources", len(scored["intl_hits"]))
            colC.metric("Other results", len(scored["other_hits"]))

            # Detailed results
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

# --- Footer ---
st.markdown(
    f'<div class="pivas-footer">'
    f'{APP_ACRONYM} · Built for the MIT 799 project at Lagos State University · '
    f'Verify first, share responsibly.'
    f'</div>',
    unsafe_allow_html=True,
)
