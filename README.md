# Sterling Sales lead finder

A Streamlit app that helps John at Sterling Sales Training & Consulting find,
research, and qualify leads, and drafts outreach for a person to send by hand.
Nothing is ever sent automatically.

Current state (step 2): password sign-in, and a Settings screen that saves
John's targeting and messaging settings to Supabase.

## 1. Install (once)

You need Python 3.12 (`brew install python@3.12`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 2. Set up Supabase (once)

1. Create a project at https://supabase.com.
2. In the dashboard, open **SQL Editor**, paste all of `supabase/schema.sql`,
   and click **Run**.
3. Find your keys:
   - **Project URL**: the **Connect** button at the top, or Project Settings > Data API (looks like
     `https://abcd1234.supabase.co`).
   - **Secret key**: Project Settings > API Keys, the one starting with
     `sb_secret_`. Not the publishable key.

## 3. Add your secrets (once)

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
open -e .streamlit/secrets.toml
```

Fill in `APP_PASSWORD`, `SUPABASE_URL` and `SUPABASE_SECRET_KEY`, then save.
This file is ignored by git, so it never gets committed. Don't paste these
values into chat, screenshots or code.

Without `APP_PASSWORD` the app stays locked. Without the Supabase values the
app still opens, but the Settings screen says it isn't connected and the Save
button is turned off.

## 4. Run it

```bash
source .venv/bin/activate
streamlit run app.py
```

It opens at http://localhost:8501. Stop it with Ctrl-C.

## Tests

```bash
source .venv/bin/activate
python -m pytest
```

These use a fake in-memory database, not Supabase.

## Deploying

On Streamlit Community Cloud, point the app at `app.py` in this repo and paste
the same three lines from your `secrets.toml` into the app's Secrets settings.
