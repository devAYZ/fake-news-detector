# PIVAS — Political Information Verification Assisted System

> *Verify first, share responsibly.*

**PIVAS** is the tangible artifact of an MIT 799 postgraduate project at Lagos State University titled *"Deepfakes and the Spread of Political Misinformation: Developing a Framework for Information Verification among Nigerian Social Media Users."*

It operationalises the **Nigerian Information Verification Framework (NIVF)** proposed in Chapter 3 and Chapter 4 of the thesis. Any Nigerian social-media user can paste a suspicious political claim, headline, or link into PIVAS and instantly receive a lightweight, colour-coded verdict grounded in coverage by Nigerian fact-checkers and credible mainstream media.

---

## Features

- **Text or URL input** — paste a headline, a claim, or a full link.
- **Optional platform filter** — restrict the search to WhatsApp, Facebook, X (formerly Twitter), Instagram, TikTok, YouTube, or Telegram. Leave every box unticked for an open web search.
- **Keyless search backend** — powered by DuckDuckGo (`duckduckgo-search`), so PIVAS runs on Streamlit Community Cloud without any API secret.
- **Nigeria-first trusted-source list** — Dubawa, Africa Check, CDD West Africa, CJID, Premium Times, The Punch, Vanguard, Guardian NG, Channels TV, Arise TV, Sahara Reporters, Daily Trust, TheCable, plus international corroborators (BBC, Reuters, AP, CNN, Al Jazeera, Guardian, AfricaNews).
- **Explainable verdicts** — every verdict comes with a plain-English note telling the user what to do next, in the spirit of NIVF Module 4 (Contextual Reasoning) and Module 5 (Platform Action).
- **Aesthetic UI** — custom Streamlit styling with a Nigerian-flag-inspired hero gradient, card layout, and metric summaries.

## Verdict scheme

| Icon | Verdict | Meaning |
|---|---|---|
| ✅ | LIKELY AUTHENTIC | Multiple trusted sources (including at least one Nigerian) are reporting on this. |
| 🟢 | PROBABLY AUTHENTIC — verify locally | ≥2 international trusted sources but no Nigerian coverage yet. Check Dubawa or Africa Check. |
| ⚠️ | INCONCLUSIVE — verify further | Only one credible source found. Do not share until you have a second independent confirmation. |
| 🚫 | SUSPECT — likely misleading or fabricated | No trusted coverage. Check a Nigerian fact-checker before you share. |

## How it works

1. The user pastes a claim or a URL.
2. PIVAS composes a DuckDuckGo query, optionally restricted with `site:` filters to the chosen platforms.
3. DuckDuckGo returns up to ten results in the `ng-en` region.
4. Each result is classified by domain against a Nigerian trusted list and an international trusted list.
5. A verdict, an explanatory note, and category-level metrics (Nigerian hits / international hits / other) are rendered, followed by the annotated result cards.

## Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.10+ | Application language |
| UI | Streamlit ≥ 1.32 | Web front end + hosting |
| HTTP client | Requests ≥ 2.31 | Reserved for future direct-fetch of platform APIs |
| Search backend | duckduckgo-search ≥ 6.1 | Keyless open web search |
| Hosting | Streamlit Community Cloud | Free public hosting |
| Version control | Git / GitHub | Source control on branch `feature/pivas` |

## Setup

```bash
git clone https://github.com/<your-username>/fake-news-detector.git
cd fake-news-detector
git checkout feature/pivas
pip install -r requirements.txt
streamlit run fakenews_detector.py
```

No API keys are required. The application will launch on `http://localhost:8501`.

## Deployment on Streamlit Community Cloud

1. Push the branch to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), connect the repo and select `fakenews_detector.py` as the main file.
3. Streamlit auto-installs from `requirements.txt`. No secrets required.

## Project structure

```
fake-news-detector/
├── fakenews_detector.py    # PIVAS Streamlit application
├── requirements.txt        # Python dependencies
├── README.md               # This file
└── LICENSE
```

## Notes on platform coverage

- **WhatsApp** is end-to-end encrypted; public search cannot index private chats. Ticking the WhatsApp box will only reach public-facing whatsapp.com pages (business profiles, channels).
- **Telegram** and **YouTube** are the most search-indexable of the seven platforms; results from those tend to be richest.
- **X / Twitter** results depend on the current openness of the platform's search index and may be sparse for very recent tweets.

## Related project artefacts

- Thesis chapters: `_Chapter 1.docx` through `_Chapter 5.docx`, and `_Reference.docx`.
- Survey: `create_google_form.gs` and `SURVEY_QUESTIONS.md`.
- Reference-list maintenance: `REFERENCES_MAINTENANCE.md`.

## Author and acknowledgements

**Ayokunle Fatokimi**, MIT 799 candidate, Lagos State University.
The base of this application was forked from a fake-news detector by Saptarshi Bandyopadhyay (@saptarshi-ux); it has been substantially rewritten to serve as the NIVF verification artifact for the Nigerian context.

## Licence

See `LICENSE` file.
