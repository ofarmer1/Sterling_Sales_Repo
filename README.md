# Sterling Sales lead finder

A Streamlit app that helps John at Sterling Sales Training & Consulting find,
research, and qualify leads, and drafts outreach for a person to send by hand.
Nothing is ever sent automatically.

What it does:
- **Find leads**: add companies you know, search the web for new ones, and
  research a batch (up to 15 at a time) with a progress bar.
- **Leads**: see each company's research with sources, whether it meets
  John's criteria (and why), and edit/copy the email and LinkedIn drafts.
  Set a review status. Download everything as a spreadsheet (CSV).
- **Settings**: John's targeting and messaging preferences.

Nothing is ever sent. You copy the drafts and send them yourself.

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

Fill in `APP_PASSWORD`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY` and
`OPENAI_API_KEY`, then save. The OpenAI key needs API credits from
platform.openai.com (a ChatGPT subscription doesn't include them).
This file is ignored by git, so it never gets committed. Don't paste these
values into chat, screenshots or code.

Without `APP_PASSWORD` the app stays locked. Without `OPENAI_API_KEY` you can
still add companies and edit things, but research and drafts are switched off. Without the Supabase values the
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

## Accounts and signing in

- **Oliver** signs in with username `oliver` (or `ADMIN_USERNAME`) and the
  `APP_PASSWORD` from secrets. This always works, so he can't be locked out.
- **Everyone else** gets an account from Oliver in **Settings > Accounts**:
  a username, a password, and either **Full access** or **View only**.
  - View only: Leads tab only. Can open companies, read and copy drafts and
    download the spreadsheet; can't edit, change statuses or Settings, or
    run any search or research (so it can't spend OpenAI credits).
- Passwords are stored only as scrypt hashes.
- "Keep me signed in" remembers the device for 30 days with a cookie. Only a
  hash of its token is stored, and signing out, a new password, a change of
  access or removing the account ends it.
- Five wrong tries in a row lock the sign-in form for a minute.

## Costs

Research uses OpenAI's web search. The app shows a running estimate on the
Leads tab and caps batches at 15 companies and searches at 8 per company.
The estimate is a guide; OpenAI's billing page has the real numbers.

## Deploying

On Streamlit Community Cloud, point the app at `app.py` in this repo and paste
the same lines from your `secrets.toml` into the app's Secrets settings.
