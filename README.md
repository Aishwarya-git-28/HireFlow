# HireFlow

Evidence-first candidate screening and interview intelligence. HireFlow reads resumes against a job description,
checks the claims that can be checked, and shows the exact words behind every rating. People make the decision.

## What it does

| Step | What happens | Where the evidence shows |
|---|---|---|
| Set up | Upload a job description and resumes (PDF or text). The job is split into testable requirements. | Setup |
| Screen | Four specialist agents extract a profile, verify claims on the web, rate every requirement, and write an interview kit. | Overview, Candidates |
| Group | Candidates are grouped by shared experience, ordered by a score computed in code. | Overview |
| Interview | Log an answer to get follow-ups. Paste notes to get an evidence map against the requirements and the areas never asked. | Interviews |
| Ask | Ask the pool questions in plain language. Every match shows its quote. | Ask the pool |
| Audit | Every insight, the source text it used, the agent and model behind it, and each web call. | Audit trail |

## Run it

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env      # then add your keys
streamlit run app.py
```

No keys? Click **Explore demo data**. The demo runs entirely on saved results.

## How it stays trustworthy

- **The model proposes, code decides.** Fit scores, dates, gaps, IDs and total experience are computed in Python.
- **Quotes must exist.** An evidence quote that cannot be found in the source document is removed. A rating that loses all its
  quotes falls back to "unclear".
- **Resumes cannot give orders.** Text aimed at the AI screener is detected, ignored, flagged, and forces manual review.
- **Failures degrade, they do not crash.** Each stage is isolated, retried, and can fall back to another model. Finished stages are
  cached, and the last session is restored after a browser refresh.
- **Humans stay in charge.** No screen recommends hiring or rejecting anyone.

## Layout

```
app.py                 dashboard entry point
ui/                    theme (CSS), components (HTML builders), views (pages)
services/              session lifecycle, demo data, scoring, audit, report export
crew/                  agents, task prompts, guards, pipelines, interview intelligence
tools/                 PDF loader and web verification tools
models.py              every data contract (Pydantic)
data/samples/          synthetic job description, resumes and interview notes
```

## Deploy on Streamlit Community Cloud

1. Push the repository to GitHub (`.env` is git-ignored).
2. Create the app with `app.py` as the entry point and Python 3.12.
3. Under Settings, Secrets, add `GROQ_API_KEY` and `GEMINI_API_KEY`.
4. Commit `data/demo_workspace.json` so **Explore demo data** loads your real saved run.

## Troubleshooting

- **"AI backend unavailable" in the top bar:** the message under the sidebar buttons names the import error.
- **Screening stalls with "rate-limited; waiting":** a free-tier limit was hit. The run pauses and continues by itself.
- **Fonts look plain:** the theme loads its fonts from Google Fonts, so it needs a connection. The layout works without it.
- Only synthetic resumes belong in free-tier AI services. Free tiers may use prompts to improve their products.
