# Step 2 review report: Settings saved to Supabase

## 1. Branch and commit
- Branch: `step-2-settings`, created from `main` at `df53254` (Step 1).
- **Not committed yet.** All changes are in the working tree of
  ~/Desktop/Sterling Sales Project, waiting for Oliver's OK to commit/push.
- ~/Documents/GitHub/Sterling_Sales_Repo is an empty clone made before Step 1
  was pushed. It was not touched; run `git pull` there to sync.

## 2. What changed, in plain English
- The Settings tab is now a real form: geography, preferred industries,
  "allow strong non-tech fits", revenue min/max, salespeople min/max, person
  to contact, messaging style, main value, call to action, and sender name,
  title, company, signature and optional booking link.
- It starts with John's confirmed settings (South Carolina; Tech, Software;
  non-tech allowed; $1M to $30M; 2 to 20 salespeople; Owner). Sender fields
  start blank.
- Clicking **Save settings** checks the values first (no negatives, minimum
  not above maximum, required fields filled, booking link must be http(s)).
  If anything is wrong it lists the problems and saves nothing.
- Saving writes one row to the Supabase table `app_settings`. "Settings saved"
  only appears if the database returns the saved row. Network or database
  errors show an error and "Nothing was saved."
- On every visit the form loads the saved row, with a "Last saved" time.
- Without Supabase keys, the form shows the defaults, a "Not connected"
  warning, and the Save button is disabled. Nothing is kept in temporary
  session memory pretending to be saved.
- **Security change:** the app now stays locked when APP_PASSWORD isn't set,
  instead of letting everyone in. This closes the gap where a deployed app with
  no password would be open.
- Leads and Find leads tabs are unchanged placeholders.

## 3. Files
| File | Purpose |
|---|---|
| `app.py` | Password gate (now locked if no password), database connection, Settings form |
| `settings_store.py` | Defaults, validation, load and save. No Streamlit code, so it's easy to test |
| `supabase/schema.sql` | Creates the `app_settings` table (single row, range checks, RLS on with no policies) |
| `.streamlit/secrets.toml.example` | Template now includes `SUPABASE_URL` and `SUPABASE_SECRET_KEY` |
| `requirements.txt` | Adds `supabase` |
| `requirements-dev.txt` | Adds `pytest` for tests |
| `tests/fake_database.py` | In-memory stand-in for the Supabase client, for tests only |
| `tests/test_settings_store.py` | 13 tests for validation and save/load logic |
| `tests/test_app.py` | 9 tests that click through the real app screens with Streamlit's AppTest |
| `.gitignore` | Also ignores `.pytest_cache/` |
| `CLAUDE.md` | Full project requirements and decisions from Oliver's brief |
| `README.md` | Setup for Supabase and secrets, run and test commands |

## 4. Run it locally
```bash
cd ~/Desktop/"Sterling Sales Project"
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
open -e .streamlit/secrets.toml     # fill in the three values, save
streamlit run app.py
```
Database setup: Supabase dashboard > SQL Editor > paste `supabase/schema.sql` > Run.

**Which key:** the **secret key** (`sb_secret_...`) from Project Settings >
API Keys, plus the Project URL. The app runs only on the server, so the secret
key never reaches the browser. The table has Row Level Security on with no
policies, so the publishable key can't read or write it. The legacy
`service_role` key would also work but Supabase plans to retire legacy keys.

## 5. Tests and actual results
`python -m pytest`: **22 passed** (Python 3.12.15, Streamlit 1.65.0, supabase 2.32.0).

All 22 use a **fake in-memory database**. None ran against real Supabase,
because no project exists yet. Covered:
- No password configured keeps the app locked; wrong password rejected; right password shows tabs.
- Password and secret key never appear in the page text.
- John's defaults are valid; sender fields start blank.
- Range boundaries: min = max allowed; min > max, negatives and blank required fields rejected.
- Booking link must be http(s) (rejects `javascript:` and bare domains).
- Save then load in a brand-new session shows the saved values and "Last saved".
- Invalid ranges in the UI show errors and never call the database.
- Database outage on save or load shows an error, never a success.
- A write the database doesn't confirm is treated as a failure.
- Leads and Find leads tabs still render.

Manual check: started the app with a temporary password and no Supabase keys,
signed in, and confirmed the Settings form, defaults and "Not connected"
warning display correctly.

**Real Supabase tests** (project "Sterling Sales Project", us-east-1, set up
through the Supabase CLI with Oliver's login; keys written straight into the
git-ignored secrets file, never displayed):
- `supabase/schema.sql` ran successfully; all 18 columns exist.
- Load before any save returned "nothing saved yet".
- Saved John's defaults with the secret key; a fresh connection read back
  identical values and a timestamp. **This row is now the live settings.**
- A direct write with revenue_min > revenue_max was rejected by the database
  check constraint (APIError), even bypassing app validation.
- The publishable key was refused for both read and write (Postgres 42501).
- In the browser, signing in and opening Settings shows the saved values and
  "Last saved: Oct 06, 2026 at 03:33 UTC".

## 6. What Oliver should click and test
Supabase and secrets are already set up.
1. Sign in. Open Settings. You should see "Last saved" and John's settings.
2. Click Save settings. You should see "Settings saved to the database."
   In Supabase, Table Editor > app_settings should show one row.
3. Change Salespeople maximum to 15, save, close the browser tab, open
   http://localhost:8501 in a new tab, sign in. It should still say 15.
4. Set Revenue minimum above the maximum and save. You should see an error
   and the database row should be unchanged.
5. Type `calendly.com/x` as the booking link and save. You should get an error.
6. Temporarily break `SUPABASE_SECRET_KEY` in secrets.toml, restart, open
   Settings. You should see a clear error, not a crash. Put it back.
7. Remove `APP_PASSWORD`, restart. The app should say it's locked.

## 7. Missing setup, limitations, next step
- Setup is done locally. For Streamlit Cloud, the three secrets still need
  to go in the app's Secrets box (use a new password there).
- Tests now run from an empty temp folder so they never read the real
  secrets file or touch the real database.
- "Last saved" is now shown in a readable format.
- Revenue fields show raw numbers (1000000) without commas.
- One settings row for everyone; there's no history of past settings.
- `updated_at` is set by the app's clock when saving.
- Elapsed agent time for Step 2: about 5 minutes by this Mac's clock, from
  receiving the brief to this report. Oliver's own time isn't counted.
  No paid API calls were made.
- Next: Step 3, research one company (needs an OpenAI API key with credits).
