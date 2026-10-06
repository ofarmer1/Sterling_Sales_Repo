# Where the data goes, and how the AI part copes with problems

## Where data is stored
- **Supabase** (project "Sterling Sales Project", AWS us-east-1): settings,
  leads, research, drafts and AI usage.
- Every table has Row Level Security on with no policies. Only the server-side
  secret key (`sb_secret_...`) can read or write. The public (publishable) key
  was tested and is refused for both reading and writing.
- The secret key lives only in `.streamlit/secrets.toml` (git-ignored, checked)
  or, once deployed, in Streamlit Cloud's Secrets box. It never reaches the
  browser, because Streamlit runs the Python code on the server.

## Where data is sent
| Goes to | What | Why |
|---|---|---|
| OpenAI | Company name, website, target region; for drafts, the research facts and John's messaging settings | Research and drafting |
| Supabase | Everything the app saves | Storage |
| Your browser | The pages you look at; the CSV when you click Download | Using the app |
| Streamlit Cloud (only after deploying) | The app runs on their servers, so data passes through them | Hosting |

Nothing else. The code makes no other outside calls, and anonymous Streamlit
usage statistics are switched off (`.streamlit/config.toml`).

About OpenAI: by OpenAI's published policy, API data isn't used to train models
by default, and may be kept for up to 30 days for abuse monitoring. Only
public company information and John's settings are sent, never passwords or
database keys.

Nothing is ever emailed or posted. The app has no sending code at all.

## Still worth doing
- In the OpenAI dashboard, set a monthly spending limit on the project as a
  second safety net (the app's own cap is an estimate).
- Before deploying, use a new, stronger APP_PASSWORD (the current one was
  shared in chat).
- Keep the Supabase account protected with two-factor login.
- Only share the CSV export with people who should see it: it contains
  everything.

## AI reliability
- **Retries:** brief outages, rate limits and server errors are retried 3
  times automatically, waiting longer each time. Each try times out after 3 minutes.
- **Clear errors:** a wrong key, an account with no credits, a busy service, a
  wrong model name or no internet each show a plain message saying what to do.
- **Incomplete or garbled answers** are treated as failures, never saved as results.
- **Nothing finished is lost:** each company is saved as soon as it's done. A
  failure is recorded on that company and the batch carries on. "Retry failed"
  redoes only the failures.
- **Spending cap:** the app stops starting new AI requests once its estimated
  spend reaches `AI_BUDGET_USD` (default $25, the top of the test budget). A
  batch stops cleanly when the cap is hit. Batches are capped at 15 companies,
  discovery at 20 candidates, and web searches at 8 per company.
- **Honest research:** sources the search never visited are removed, and
  unsupported "verified" claims are downgraded (see research.py). This only
  proves the search opened the page, not that the page says what the AI
  claims, so the app labels these facts "cited" and asks a person to open
  the link before relying on it.

Not proven yet: none of this has run against the real OpenAI API, because there
is no key yet. The first real runs will show actual accuracy, speed and cost.
