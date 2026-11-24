# 🤝 Yojana Mitra (ಯೋಜನಾ ಮಿತ್ರ)

## Problem
Karnataka has many welfare schemes, but the people who need them most (elderly, rural and low-literacy citizens) often don't know which ones they qualify for. The rules are scattered across websites, mostly in English, and full of jargon. Many eligible people never apply.

## Solution
A Kannada-first assistant. The person describes their situation by voice, text or a photo of their ration card. Yojana Mitra checks them against each scheme's rules, explains every result, asks only the questions it still needs, and prepares a draft application with a documents checklist.

## Features
- 🎙️ Kannada voice input, typed text, or a ration card photo
- ✅ / ❌ / ❓ eligibility result for each scheme, with a reason for every rule
- 1–3 smart follow-up questions when information is missing
- Readiness score, a filled draft PDF form (Kannada + English) and a documents checklist
- 🔊 Spoken summary in Kannada or English
- 👵 Ajji mode for elderly users: big text, simple Kannada, every screen read aloud
- Works offline for typed text if the AI is unavailable

## Tech stack
- **Gemini** (`google-genai`): understands voice, text and images
- **Streamlit**: the UI and hosting
- **gTTS**: Kannada and English speech
- **fpdf2** + **uharfbuzz** + Noto Sans Kannada: Kannada PDF forms
- Python rules engine + `schemes.json` for eligibility

**Built with Gemini, Streamlit, gTTS, fpdf2, Claude Code.**

## About
Yojana Mitra helps people in Karnataka find out which government schemes they can get. It works in Kannada and English.

A person can **speak in Kannada**, **type**, or **upload a photo of their ration card**. The app then:

1. **Understands** their details. It uses Gemini AI, with an offline reader for typed text as backup.
2. **Checks eligibility** for each scheme. The answer is ✅ ELIGIBLE, ❌ NOT ELIGIBLE or ❓ NEEDS MORE INFO, with the reason for every condition.
3. **Asks 1–3 follow-up questions** when information is missing, then checks again.
4. **Prepares the application.** It shows a readiness score, a filled draft PDF form (Kannada + English) and a documents checklist, with official links.
5. **Speaks** a summary in Kannada or English.

**👵 Ajji mode** is for elderly users. It has big text and big buttons, uses simple Kannada and reads every screen aloud. It shows one thing at a time.

> ⚠️ **Scheme data:** the rules in `schemes.json` come from news and information websites (links in each scheme's `research_links`). They have **not yet been checked against official government orders**, so every scheme shows "Last verified: not yet verified". Rules the sources disagree on are marked `"needs_official_check": true`. The app never says NOT ELIGIBLE because of such a rule; it shows "needs official verification" instead. Before a real launch, check each scheme on its official website and fill in `last_verified` with the date.

---

## Run it on your computer (Windows)

You need **Python 3.10 or newer** (we use 3.14) and a free **Gemini API key** from https://aistudio.google.com/apikey.

```powershell
# 1. Go to the project folder
cd "C:\Users\<you>\OneDrive\Desktop\yojana-mitra"

# 2. Create and turn on a virtual environment (first time only)
python -m venv .venv
.venv\Scripts\activate

# 3. Install the libraries (first time only)
pip install -r requirements.txt

# 4. Add your Gemini API key (first time only)
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
notepad .streamlit\secrets.toml      # paste your key, save, close

# 5. Start the app
streamlit run app.py
```

The app opens at **http://localhost:8501**. Next time, run only `.venv\Scripts\activate` and `streamlit run app.py`.

> On Mac or Linux: `source .venv/bin/activate` and `cp` instead of `copy`.

**No API key?** The app still works for **typed** text, using the offline reader. Voice and photo need the key.

---

## Put it online (Streamlit Community Cloud, free)

### 1. Put the code on GitHub
Your API key stays out of GitHub, because `.streamlit/secrets.toml` is listed in `.gitignore`.

1. Create a **new empty repository** on https://github.com/new (for example `yojana-mitra`). Don't add a README there.
2. In the project folder, run:
   ```powershell
   git remote add origin https://github.com/<your-username>/yojana-mitra.git
   git push -u origin main
   ```
3. On GitHub, check that `.streamlit/secrets.toml` is **not** in the list of files.

### 2. Create the app
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app**, then **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `<your-username>/yojana-mitra`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** pick a name, e.g. `yojana-mitra`
4. Open **Advanced settings**:
   - **Python version:** choose **3.12**.
   - **Secrets:** paste this (with your real key):
     ```toml
     GEMINI_API_KEY = "paste-your-key-here"
     ```
5. Click **Deploy**. The first start takes a few minutes while it installs the libraries.

### 3. After deploying
- **Mic:** the microphone works on the `https://….streamlit.app` link. The first time, the browser asks for permission; tap **Allow**.
- **Sleeping apps:** free apps go to sleep after a few days without visitors. **Open the link a few minutes before your demo** and click "Yes, get this app back up" if you see it.
- **Changing the key:** in the app's **Settings → Secrets** on share.streamlit.io.
- **Updating the app:** run `git push`. The app updates automatically.

---

## Files

```
app.py                  the screen (Streamlit): normal mode + Ajji mode
engine.py               eligibility rules engine, follow-up questions, readiness score
ai.py                   Gemini (retries, backup model, timeouts) + offline text reader + recording check
pdf_form.py             filled draft application PDF (Kannada + English)
texts.py                all screen text in English and Kannada + the 6 demo people
schemes.json            7 Karnataka schemes: rules, documents, how to apply, links
fonts/                  Noto Sans Kannada + Noto Sans (SIL Open Font License)
tests/                  automatic tests
.streamlit/config.toml  colours (saffron / green)
.streamlit/secrets.toml your API key (NOT on GitHub)
```

## How the eligibility engine works

Each scheme in `schemes.json` has a list of `rules`. Each rule has a `field` (for example `age`), an `op` (`equals`, `in`, `min`, `max`, `is_true`, `is_false`) and a `value`.

| What we know | Result for that rule |
|---|---|
| The person meets it | ✅ met |
| The person clearly does not meet it | ❌ not met, so the scheme is NOT ELIGIBLE |
| We don't have this information yet | ❓ missing, so NEEDS MORE INFO (and we ask a question) |
| Doesn't match, but the rule is marked `needs_official_check` | 🔎 needs official verification, so NEEDS MORE INFO |

A scheme is **ELIGIBLE only when every rule is met.** Conditions we know about but can't check (listed in `other_conditions`) are shown as "needs official verification".

The ration card field has these values: `BPL`, `APL`, `AAY`, `card_type_unknown` (they have a card but didn't say which), `pending`, `none`, or empty when it isn't mentioned.

**To add a scheme:** copy one block in `schemes.json` and edit it. Only use rules you have a source for, and put the source in `research_links`.

## Reliability

- **Gemini busy (503/429):** the app retries 3 times, waiting 2, 4 and 8 seconds, then switches to a backup model. Model names are set at the top of `ai.py`.
- **Slow AI:** each request stops after 30 seconds, and step 1 stops after 60 seconds in total. If a request times out, the app switches to the backup model straight away.
- **Voice reply:** gTTS stops after 15 seconds.
- **AI down:** typed text is read by the offline reader in `ai.py`.
- **Bad voice notes:** too-short or silent recordings are caught immediately with a friendly message.
- **Errors:** users only see friendly messages. The real errors are printed in the terminal (`[Yojana Mitra] ...`).

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -v                     # 29 offline tests, a few seconds
$env:RUN_GEMINI="1"; python -m pytest tests -v # + 7 tests that call the real Gemini API
```

The tests cover the 6 demo people, the engine's rules, ration card states, Yuva Nidhi checks, the scheme data file, the readiness score, recording checks and the retry/backup logic.

## Not built (on purpose)

There's no scheme comparison, no document inconsistency checking, no login and no database. Nothing about the user is stored; everything stays in the browser session.
