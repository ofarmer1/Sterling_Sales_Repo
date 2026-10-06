# Sterling Sales lead finder

A Streamlit app that helps John at Sterling Sales Training & Consulting find,
research, and qualify leads, and drafts outreach for him to send by hand.

Right now (step 1) it's a password-protected skeleton with three empty tabs.

## Run it locally

You need Python 3.12.

```bash
# 1. Create and turn on a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install the packages
pip install -r requirements.txt

# 3. (Optional) set a password
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and change the password

# 4. Start the app
streamlit run app.py
```

The app opens at http://localhost:8501.

If you skip step 3, there's no password and the app lets you straight in.
You can also set the password with an environment variable instead:
`APP_PASSWORD=secret streamlit run app.py`.

## Deploying

On Streamlit Community Cloud, point the app at `app.py` in this repo and add
`APP_PASSWORD = "..."` in the app's Secrets settings.
