# Sterling Sales lead finder

## Goal
A web app for John at Sterling Sales Training & Consulting. It finds companies
that fit his ideal client profile, researches each company and its owner,
qualifies them against his rules, and drafts a cold email and a LinkedIn note
for him to review and send by hand.

**Nothing is ever sent automatically.** The app only drafts; John sends.

## Stack
- Python 3.12
- Streamlit for the app (`app.py`)
- Supabase (Postgres) for the database (from step 2)
- OpenAI API with web search for research (from step 3)
- Hosted on Streamlit Community Cloud from this GitHub repo

## Step plan
1. Skeleton and deploy
2. Settings screen saved to Supabase
3. Research one company
4. Qualification rules with tests
5. Drafts with editor, copy, and status
6. Batch "Find leads"
7. Spreadsheet export, error handling, polish

Build one step at a time. Don't start features from a later step early.

## Rules
- Keep code simple and readable. Oliver is learning as he goes, so prefer
  plain, obvious code over clever code, and add short comments where it helps.
- After finishing a step, explain each file in plain English, give the exact
  commands to run it locally, and say what to test.
- Don't commit or push. Oliver does that himself.
- Secrets (APP_PASSWORD and later API keys) live in `.streamlit/secrets.toml`
  locally or the Streamlit Cloud Secrets box. Never commit them.
