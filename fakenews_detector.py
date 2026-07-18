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

import base64
import os
import re
from urllib.parse import urlparse

import requests
import streamlit as st
import streamlit.components.v1 as components


# Path to an optional bespoke logo image. Drop a file named `logo.jpeg`,
# `logo.png`, or `logo.svg` next to this script and it will be embedded in
# the hero. If no such file exists, PIVAS falls back to the 🛡️ emoji.
LOGO_CANDIDATES = ["logo.jpeg", "logo.jpg", "logo.png", "logo.svg"]


def _find_logo() -> tuple[str, str] | None:
    """Return (base64-data, mime-type) for the first logo file that exists."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in LOGO_CANDIDATES:
        p = os.path.join(here, name)
        if os.path.exists(p):
            ext = os.path.splitext(name)[1].lower()
            mime = {".jpeg": "image/jpeg", ".jpg": "image/jpeg",
                    ".png": "image/png",  ".svg": "image/svg+xml"}.get(ext, "image/jpeg")
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), mime
    return None

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
    """Compose the search query.

    Note: the `selected_platforms` value is NOT applied as a `site:` filter
    on the query itself. Restricting the search to `site:facebook.com` or
    similar would return only social-media posts, which are not fact-checks
    and would hurt verification. The selected platforms are treated as a
    context signal (see PLATFORM_HINTS below) and used only to tailor the
    verdict note that follows the search.
    """
    return user_input.strip()


# Guidance shown alongside the verdict, based on where the user saw the
# content. The messages are deliberately concrete and Nigeria-aware.
PLATFORM_HINTS = {
    "WhatsApp": ("WhatsApp is end-to-end encrypted, so third-party fact-checkers "
                 "cannot see private messages. If it came from a group, screenshot "
                 "and forward the claim to Dubawa's WhatsApp tip line (+234 803 900 1069)."),
    "Facebook": ("Facebook posts spread quickly. If the account looks new or has few "
                 "followers, treat it as unverified until a trusted outlet confirms it."),
    "X (Twitter)": ("X (Twitter) content often lacks context. Check whether the account "
                    "is verified and whether the same claim appears from at least one credible "
                    "Nigerian outlet in the results below."),
    "Instagram": ("Instagram posts can be image- or Reels-based. Perform a reverse-image "
                  "search on any photo (Google Images or TinEye) before you accept the claim."),
    "TikTok": ("TikTok political clips are often edited or dubbed. Confirm with a Nigerian "
               "fact-checker before you share."),
    "YouTube": ("Check the channel — official Nigerian outlets (Channels TV, Arise, TVC, BBC) "
                "have long-standing accounts; new channels claiming breaking political news are a warning sign."),
    "Telegram": ("Telegram channels are less moderated than Facebook or X. Cross-reference "
                 "any claim from a Telegram channel against at least two independent sources."),
}


TIME_WINDOWS = {
    "Any time":         None,
    "Past 24 hours":    "d",
    "Past week":        "w",
    "Past month":       "m",
    "Past year":        "y",
}


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


# ----------------------------------------------------------------------
# Search backends
# ----------------------------------------------------------------------

def ddg_search(query: str, max_results: int = 10,
               timelimit: str | None = None) -> list[dict]:
    """Run a keyless DuckDuckGo search.

    `timelimit` accepts one of: "d" (day), "w" (week), "m" (month), "y" (year)
    or None (any time). DDG does NOT sort by date; it returns results ranked
    by its relevance model. Setting a timelimit narrows the window so the
    freshest coverage floats to the top of a relevance-ranked list.
    """
    if DDGS is None:
        return []
    kwargs = {"max_results": max_results, "region": "ng-en"}
    if timelimit:
        kwargs["timelimit"] = timelimit
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, **kwargs))
    except Exception:
        try:  # Retry once without region — some DDG mirrors reject ng-en
            kwargs.pop("region", None)
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, **kwargs))
        except Exception:
            return []
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


def run_search(query: str, max_results: int = 10,
               timelimit: str | None = None) -> tuple[list[dict], str]:
    """Try DDG first, then fall back to Wikipedia. Return (results, backend)."""
    results = ddg_search(query, max_results=max_results, timelimit=timelimit)
    if results:
        return results, "DuckDuckGo (ddgs)"
    # Wikipedia has no equivalent time filter; ignore the timelimit for it.
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
    padding: 0.95rem 1.4rem 0.85rem 1.4rem;   /* compact header */
    text-align: left;
  }
  .pivas-hero .pivas-brand {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .pivas-hero .logo-img {
    width: 44px;
    height: 44px;
    border-radius: 10px;
    object-fit: cover;
    background: rgba(255,255,255,0.10);
    flex-shrink: 0;
  }
  .pivas-hero .shield {
    font-size: 2.0rem;
    line-height: 1;
    flex-shrink: 0;
  }
  .pivas-hero h1 {
    color: white;
    font-size: 1.55rem;    /* inline with logo — moderate size */
    font-weight: 700;
    margin: 0;
    line-height: 1.15;
    letter-spacing: -0.3px;
    flex: 1;
  }
  .pivas-hero .badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 999px;
    background: rgba(255,255,255,0.22);
    font-size: 1.05rem;          /* enlarged acronym */
    letter-spacing: 0.18em;
    font-weight: 700;
  }
  .pivas-hero p {
    color: rgba(255,255,255,0.95);
    margin: 0.35rem 0 0 0;
    font-size: 0.9rem;
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
  /* Primary action buttons — regular and form submit both hit these */
  .stButton>button,
  [data-testid="stFormSubmitButton"] button {
    background: #16A34A !important;   /* action green */
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.6rem 1.6rem !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 10px rgba(22, 163, 74, 0.30);
    transition: background 0.15s ease, transform 0.05s ease;
  }
  .stButton>button:hover,
  [data-testid="stFormSubmitButton"] button:hover {
    background: #15803D !important;   /* deeper green on hover */
    color: #FFFFFF !important;
  }
  .stButton>button:active,
  [data-testid="stFormSubmitButton"] button:active {
    transform: translateY(1px);
  }
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
# Resolve the logo — prefer a bespoke image dropped into fake-news-detector/,
# otherwise fall back to the 🛡️ emoji.
_logo = _find_logo()
if _logo:
    _b64, _mime = _logo
    logo_html = f'<img class="logo-img" src="data:{_mime};base64,{_b64}" alt="PIVAS logo" />'
else:
    logo_html = '<span class="shield">🛡️</span>'

st.markdown(f"""
<div class="pivas-shell">
  <div class="pivas-hero">
    <div class="pivas-brand">
      {logo_html}
      <h1>{APP_TITLE}</h1>
      <span class="badge">{APP_ACRONYM}</span>
    </div>
    <p>{APP_TAGLINE}</p>
  </div>
  <div class="pivas-input-top"></div>
</div>
""", unsafe_allow_html=True)

# --- Input controls (native Streamlit widgets, no wrapping div) -------
# Wrap input + platform ticks + time window + Verify button in a form so
# pressing Enter inside the search input triggers a submission (Streamlit
# forms auto-submit on Enter). Without the form, Enter would only update
# the input value and the user would have to click Verify separately.
with st.form(key="pivas_form", clear_on_submit=False):
    query_input = st.text_input(
        "Paste a link or type a headline / claim to verify",
        placeholder="e.g. https://example.com/story  —  or —  'President cancels 2027 elections'",
        key="pivas_query",
    )

    st.markdown('<p class="pivas-plat-label">Where did you originally see this content? (optional)</p>',
                unsafe_allow_html=True)

    plat_cols = st.columns(4)
    selected: list[str] = []
    platforms_list = list(PLATFORMS.keys())
    for idx, name in enumerate(platforms_list):
        with plat_cols[idx % 4]:
            if st.checkbox(name, key=f"plat_{name}"):
                selected.append(name)

    st.caption(
        "Selecting a platform does not limit the search. "
        "PIVAS always checks trusted Nigerian and global sources. "
        "It simply adds platform-specific guidance "
        "e.g., WhatsApp forwards require different verification methods)."
    )

    st.markdown('<p class="pivas-plat-label">How recent should the coverage be?</p>',
                unsafe_allow_html=True)
    time_label = st.radio(
        label="How recent should the coverage be?",
        options=list(TIME_WINDOWS.keys()),
        index=3,   # default to "Past month" — best for political content
        horizontal=True,
        label_visibility="collapsed",
    )
    st.caption(
        "The framework returns results ranked by relevance, not by date. "
        "To find fresh results, narrow the time range: "
        "use Past month for political topics and Past 24 hours for breaking news."
    )

    # The submit button IS the Verify button. Pressing Enter in any text
    # input inside a Streamlit form triggers this submit automatically.
    verify_clicked = st.form_submit_button("🔍  Verify (or press Enter)")

# Disable browser autocorrect / autocapitalise / autocomplete / spellcheck
# on the search input. Streamlit does not expose these attributes on
# st.text_input, so we set them via a small JS component that also
# re-applies them on every Streamlit re-render via a MutationObserver.
components.html(
    """
    <script>
      const disableAutocorrect = () => {
        const doc = window.parent.document;
        doc.querySelectorAll('input[type="text"], textarea').forEach(el => {
          el.setAttribute('autocorrect', 'off');
          el.setAttribute('autocapitalize', 'off');
          el.setAttribute('autocomplete', 'off');
          el.setAttribute('spellcheck', 'false');
        });
      };
      disableAutocorrect();
      // Keep applying — Streamlit re-renders inputs on every interaction.
      const observer = new MutationObserver(disableAutocorrect);
      observer.observe(window.parent.document.body, { childList: true, subtree: true });
    </script>
    """,
    height=0,
)

# --- Search + verdict -------------------------------------------------
if verify_clicked:
    if not query_input.strip():
        st.warning("Please paste a link or type a claim to verify.")
    else:
        input_mode = "URL" if is_url(query_input) else "text claim"
        st.info(f"Interpreted as **{input_mode}** — running verification...")

        with st.spinner("Consulting trusted Nigerian and international sources..."):
            query = build_query(query_input, selected)
            timelimit = TIME_WINDOWS.get(time_label)
            results, backend = run_search(query, max_results=10, timelimit=timelimit)

        st.caption(
            f"Search backend: **{backend}** · Time window: **{time_label}** · "
            f"Results are ranked by relevance (no public search engine sorts by date; "
            f"the time window is the reliable way to prioritise recent coverage)."
        )

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

            # Platform-specific tailored guidance (uses the checkboxes)
            if selected:
                st.markdown("#### 📍 Platform-specific guidance")
                for p in selected:
                    hint = PLATFORM_HINTS.get(p)
                    if hint:
                        st.markdown(f"**{p}** — {hint}")

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
    f'{APP_ACRONYM} · Built for the MIT 799 Project at Lagos State University, 2023/24  · '
    f'Verify first, share responsibly.'
    f'</div>',
    unsafe_allow_html=True,
)
