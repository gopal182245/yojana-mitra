"""
ai.py - STEP 1: understand the person (voice note / typed text / photo).

  * extract_details()    - asks Gemini, with retries, a backup model and time limits
  * parse_text_offline() - backup plan for TYPED text when AI is not available (no internet/AI needed)

Nothing in this file uses Streamlit, so it can be tested on its own.
"""

import io
import json
import re
import time
import wave
from array import array

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from engine import FIELDS

# Gemini model names. If Google retires one, just change the name here.
# (Nov 2026: gemini-3.8-flash was overloaded and took 30+ seconds, so the fast
#  flash-lite model goes first. Swap these back when 3.8-flash is healthy again.)
GEMINI_MODEL = "gemini-3.5-flash-lite"     # main model (fast, handles Kannada voice well)
BACKUP_MODEL = "gemini-3.8-flash"          # backup, used if the main model keeps failing

# Reliability settings
RETRY_WAITS = [2, 4, 8]          # seconds to wait before retry 1, 2 and 3
REQUEST_TIMEOUT_SECONDS = 30     # give up on a single Gemini request after this long
TOTAL_TIME_LIMIT_SECONDS = 60    # never spend more than this on Step 1 in total


# ---------------------------------------------------------------------------
# The instructions for Gemini, built from the FIELDS list in engine.py
# ---------------------------------------------------------------------------
def build_prompt():
    lines = []
    for key, info in FIELDS.items():
        if info["type"] == "number":
            kind = "integer"
        elif info["type"] == "yesno":
            kind = "true or false"
        elif info["type"] == "choice":
            values = list(info["options"])
            if key == "ration_card":
                values.append("card_type_unknown")
            kind = "one of " + ", ".join(f'"{v}"' for v in values)
        else:
            kind = "string"
        hint = f" ({info['ai_hint']})" if info.get("ai_hint") else ""
        lines.append(f'  "{key}": {kind}{hint} - {info["en"]}')
    return (
        "You are helping a person in Karnataka, India check government schemes.\n"
        "The input may be a Kannada voice note, typed text (Kannada or English), or a photo of a\n"
        "ration card / ID card. Return ONLY a JSON object with exactly these keys:\n"
        + "\n".join(lines) + "\n\n"
        "VERY IMPORTANT: never guess. Use null for anything the person did not clearly say or show.\n"
        "Do not work out occupation or work status from age, gender or being a widow.\n"
        "Keep the name in the script it was given (Kannada stays Kannada)."
    )


EXTRACT_PROMPT = build_prompt()


def to_int(value):
    """Turn '42', 42.0 or '1,00,000' into an int. Returns None if it can't."""
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def clean_details(data):
    """Keep only known fields, and only values that make sense for each field."""
    details = {}
    for key, info in FIELDS.items():
        value = data.get(key)
        if value in (None, "", "null"):
            details[key] = None
        elif info["type"] == "number":
            details[key] = to_int(value)
        elif info["type"] == "yesno":
            text = str(value).strip().lower()
            details[key] = True if text in ("true", "yes") else False if text in ("false", "no") else None
        elif info["type"] == "choice":
            allowed = list(info["options"]) + (["card_type_unknown"] if key == "ration_card" else [])
            match = [a for a in allowed if str(a).lower() == str(value).strip().lower()]
            details[key] = match[0] if match else None
        else:
            details[key] = str(value).strip()
    return details


# ---------------------------------------------------------------------------
# Gemini with retries + backup model + time limits
# ---------------------------------------------------------------------------
def is_timeout(error):
    """True if the request was too slow (our timeout, or Google's 408/504 'deadline exceeded')."""
    if isinstance(error, genai_errors.APIError):
        return error.code in (408, 504)
    return "timeout" in type(error).__name__.lower()


def is_worth_retrying(error):
    """
    True for quick 'busy' errors where waiting a few seconds and trying again often works
    (503 overloaded, 429 too many requests, 500/502 server hiccup, internet glitch, broken JSON).
    False for timeouts (the model is very slow - better to switch to the backup at once)
    and for errors that will never fix themselves (wrong API key, unknown model name).
    """
    if is_timeout(error):
        return False
    if isinstance(error, genai_errors.APIError):
        return error.code in (429, 500, 502, 503)
    return True


def ask_gemini(api_key, contents, notify):
    """
    Send `contents` to Gemini and return its JSON reply as a Python dict.

    - Tries the main model up to 4 times (1 try + 3 retries, waiting 2, 4, 8 seconds).
    - If that still fails (or a request times out), does the same with the backup model.
    - Each request is cut off after REQUEST_TIMEOUT_SECONDS, and the whole thing
      after TOTAL_TIME_LIMIT_SECONDS, so the app never spins forever.
    - notify(message_key, **values) lets the screen show friendly progress messages.
    If everything fails, the last error is raised.
    """
    start = time.time()
    tries_per_model = len(RETRY_WAITS) + 1
    last_error = None

    for model_number, model in enumerate([GEMINI_MODEL, BACKUP_MODEL]):
        if model_number == 1:
            notify("ai_backup")

        for attempt in range(tries_per_model):
            time_left = TOTAL_TIME_LIMIT_SECONDS - (time.time() - start)
            if time_left < 1:
                raise TimeoutError(f"Gave up after {TOTAL_TIME_LIMIT_SECONDS} seconds") from last_error

            # New client each try, so the timeout never goes past our total time limit
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=int(min(REQUEST_TIMEOUT_SECONDS, time_left) * 1000),  # in milliseconds
                    retry_options=types.HttpRetryOptions(attempts=1),  # we do our own retries
                ),
            )
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",  # ask Gemini to reply with pure JSON
                        temperature=0,  # 0 = no creativity, just facts
                    ),
                )
                return json.loads(response.text)
            except Exception as error:
                last_error = error
                # The real error goes to the terminal (for you), not to the user's screen
                print(f"[Yojana Mitra] {model} try {attempt + 1} failed: {error!r}")

                is_last_try = attempt == tries_per_model - 1
                if is_last_try or not is_worth_retrying(error):
                    break  # stop retrying this model -> go to the backup model

                wait = RETRY_WAITS[attempt]
                if time.time() - start + wait >= TOTAL_TIME_LIMIT_SECONDS:
                    break  # no time left to wait -> go to the backup model (or give up)
                notify("ai_busy", wait=wait, n=attempt + 2, total=tries_per_model)
                time.sleep(wait)

    raise last_error


MIN_RECORDING_SECONDS = 1.0   # shorter than this = probably pressed the mic by mistake
SILENCE_LEVEL = 300           # loudest sound below this (out of 32767) = nothing was said


def check_recording(audio_bytes):
    """
    Quick local check of a voice note BEFORE we spend time on the AI.
    Returns "ok", "too_short" or "silent".
    st.audio_input gives 16-bit WAV. If the file is not a WAV we can read, we say "ok"
    and let Gemini try (it understands many audio formats).
    """
    try:
        with wave.open(io.BytesIO(audio_bytes)) as recording:
            seconds = recording.getnframes() / recording.getframerate()
            if seconds < MIN_RECORDING_SECONDS:
                return "too_short"
            if recording.getsampwidth() != 2:
                return "ok"  # not 16-bit - skip the loudness check
            samples = array("h", recording.readframes(recording.getnframes()))
    except (wave.Error, EOFError, ZeroDivisionError):
        return "too_short" if len(audio_bytes) < 1000 else "ok"
    loudest = max((abs(s) for s in samples), default=0)
    return "silent" if loudest < SILENCE_LEVEL else "ok"


def extract_details(api_key, typed_text, audio_bytes, audio_mime, image_bytes, image_mime, notify):
    """Use Gemini to read the voice note / text / photo and return the person's details."""
    if not api_key:
        raise RuntimeError("No Gemini API key")

    # "contents" is a list: our instructions + whatever the user gave us
    contents = [EXTRACT_PROMPT]
    if typed_text:
        contents.append("Typed text from the user:\n" + typed_text)
    if audio_bytes:
        contents.append(types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime or "audio/wav"))
    if image_bytes:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))

    return clean_details(ask_gemini(api_key, contents, notify))


# ---------------------------------------------------------------------------
# BACKUP PLAN: read TYPED text without AI, using simple patterns.
# Not as smart as Gemini, but eligibility still works when AI is down.
# ---------------------------------------------------------------------------

# Karnataka districts: official name -> words people may type (English + Kannada).
# Kannada words are written without the last vowel so "ಮೈಸೂರು" and "ಮೈಸೂರಿನ" both match.
DISTRICTS = {
    "Bengaluru Rural": ["bengaluru rural", "bangalore rural", "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ"],
    "Bengaluru Urban": ["bengaluru", "bangalore", "ಬೆಂಗಳೂರ"],
    "Bagalkot": ["bagalkot", "ಬಾಗಲಕೋಟ"],
    "Ballari": ["ballari", "bellary", "ಬಳ್ಳಾರಿ"],
    "Belagavi": ["belagavi", "belgaum", "ಬೆಳಗಾವಿ"],
    "Bidar": ["bidar", "ಬೀದರ"],
    "Chamarajanagar": ["chamarajanagar", "ಚಾಮರಾಜನಗರ"],
    "Chikkaballapur": ["chikkaballapur", "ಚಿಕ್ಕಬಳ್ಳಾಪುರ"],
    "Chikkamagaluru": ["chikkamagaluru", "chikmagalur", "ಚಿಕ್ಕಮಗಳೂರ"],
    "Chitradurga": ["chitradurga", "ಚಿತ್ರದುರ್ಗ"],
    "Dakshina Kannada": ["dakshina kannada", "mangaluru", "mangalore", "ದಕ್ಷಿಣ ಕನ್ನಡ", "ಮಂಗಳೂರ"],
    "Davanagere": ["davanagere", "davangere", "ದಾವಣಗೆರ"],
    "Dharwad": ["dharwad", "hubli", "hubballi", "ಧಾರವಾಡ", "ಹುಬ್ಬಳ್ಳಿ"],
    "Gadag": ["gadag", "ಗದಗ"],
    "Hassan": ["hassan", "ಹಾಸನ"],
    "Haveri": ["haveri", "ಹಾವೇರಿ"],
    "Kalaburagi": ["kalaburagi", "gulbarga", "ಕಲಬುರಗಿ"],
    "Kodagu": ["kodagu", "coorg", "madikeri", "ಕೊಡಗ"],
    "Kolar": ["kolar", "ಕೋಲಾರ"],
    "Koppal": ["koppal", "ಕೊಪ್ಪಳ"],
    "Mandya": ["mandya", "ಮಂಡ್ಯ"],
    "Mysuru": ["mysuru", "mysore", "ಮೈಸೂರ"],
    "Raichur": ["raichur", "ರಾಯಚೂರ"],
    "Ramanagara": ["ramanagara", "ರಾಮನಗರ"],
    "Shivamogga": ["shivamogga", "shimoga", "ಶಿವಮೊಗ್ಗ"],
    "Tumakuru": ["tumakuru", "tumkur", "ತುಮಕೂರ"],
    "Udupi": ["udupi", "ಉಡುಪಿ"],
    "Uttara Kannada": ["uttara kannada", "karwar", "ಉತ್ತರ ಕನ್ನಡ"],
    "Vijayapura": ["vijayapura", "bijapur", "ವಿಜಯಪುರ"],
    "Vijayanagara": ["vijayanagara", "hosapete", "hospet", "ವಿಜಯನಗರ"],
    "Yadgir": ["yadgir", "ಯಾದಗಿರಿ"],
}

NO_JOB_WORDS = ["unemployed", "no job", "jobless", "without job", "without a job", "not working",
                "looking for job", "looking for a job", "ನಿರುದ್ಯೋಗ", "ಉದ್ಯೋಗವಿಲ್ಲ", "ಕೆಲಸ ಇಲ್ಲ", "ಕೆಲಸವಿಲ್ಲ"]

# Occupation -> words that hint at it. Checked in this order ("no job" before "job").
OCCUPATION_WORDS = {
    "unemployed": NO_JOB_WORDS,
    "farmer": ["farmer", "farming", "agricultur", "kisan", "raita", "ರೈತ", "ಕೃಷಿ"],
    "student": ["student", "studying", "ವಿದ್ಯಾರ್ಥಿ"],
    "homemaker": ["homemaker", "housewife", "house wife", "ಗೃಹಿಣಿ"],
    "daily wage worker": ["daily wage", "coolie", "labourer", "laborer", "ಕೂಲಿ"],
    "retired": ["retired", "pensioner", "ನಿವೃತ್ತ"],
    "self-employed": ["self-employed", "self employed", "business", "shop", "tailor", "ಟೈಲರ್", "ಅಂಗಡಿ", "ವ್ಯಾಪಾರ"],
    "salaried": ["salaried", "employee", "private job", "government job", "software", "it company",
                 "company", "office job", "working at", "working in", "job at", "ನೌಕರ", "ಕಂಪನಿ"],
}


def has_word(text, words):
    """True if any of `words` appears in `text` (already lowercase).
    English words must start and end at a word boundary ("man" should not match "woman")."""
    for word in words:
        if word.isascii():
            if re.search(r"\b" + re.escape(word) + r"\b", text):
                return True
        elif word in text:  # Kannada: simple "is it inside the text" check
            return True
    return False


def parse_text_offline(text):
    """Pull the person's details out of typed text with simple patterns (no AI)."""
    # Turn Kannada digits (೪೨) into normal digits (42)
    text = text.translate(str.maketrans("೦೧೨೩೪೫೬೭೮೯", "0123456789"))
    low = text.lower()
    d = {key: None for key in FIELDS}

    # --- Name: "my name is Lakshmi" / "ನನ್ನ ಹೆಸರು ಲಕ್ಷ್ಮಿ" ---
    match = re.search(r"(?:my name is|name is|name\s*[:\-]|ನನ್ನ ಹೆಸರು|ಹೆಸರು\s*[:\-])\s*([^\d,.;\n]+)", text, re.I)
    if match:
        name = re.split(r"\s+(?:and|i|i'm|age|from|ನಾನು|ವಯಸ್ಸು)(?!\w)", match.group(1), flags=re.I)[0]
        name = " ".join(name.split()[:4])  # at most 4 words
        if name:
            d["name"] = name
            low = low.replace(name.lower(), " ")  # so a name like "Hassan" isn't read as a district

    # --- Age: "age 42", "42 years old", "42 yrs", "42 ವರ್ಷ", "I am 42" ---
    for pattern in [r"\b(?:age|aged|ವಯಸ್ಸು)\s*(?:is|:|-|=)?\s*(\d{1,3})\b",
                    # "42 years" but not "for 1 year" / "since 2 years" (that's time, not age)
                    r"(?<!for )(?<!since )\b(\d{1,3})\s*(?:years?|yrs?)\b(?!\s*(?:ago|without|of\s+no|of\s+unemploy))",
                    r"\b(\d{1,3})\s*ವರ್ಷ(?!ಕ್ಕೆ|ದಿಂದ|ಗಳಿಂದ|ದ\s*ಹಿಂದೆ)",
                    r"\bi\s*(?:am|'m)\s*(\d{1,3})\b(?!\s*(?:lakh|thousand|k\b|rs|rupees|months?))"]:
        match = re.search(pattern, low)
        if match and 0 < int(match.group(1)) <= 120:
            d["age"] = int(match.group(1))
            break

    # --- Marital status + gender (a widow is a woman, a widower is a man) ---
    if has_word(low, ["widower", "ವಿಧುರ"]):
        d["marital_status"], d["gender"] = "widow", "male"
    elif has_word(low, ["widow", "widowed", "ವಿಧವೆ"]):
        d["marital_status"], d["gender"] = "widow", "female"
    elif has_word(low, ["unmarried", "single", "not married", "ಅವಿವಾಹಿತ"]):
        d["marital_status"] = "single"
    elif has_word(low, ["married", "my husband", "my wife", "ವಿವಾಹಿತ", "ಮದುವೆಯಾಗಿದೆ"]):
        d["marital_status"] = "married"

    if d["gender"] is None:
        if has_word(low, ["female", "woman", "women", "lady", "girl", "mrs", "smt", "housewife",
                          "ಮಹಿಳೆ", "ಹೆಂಗಸು", "ಹೆಣ್ಣು", "ಗೃಹಿಣಿ"]):
            d["gender"] = "female"
        elif has_word(low, ["male", "man", "boy", "mr", "ಪುರುಷ", "ಗಂಡಸು", "ಗಂಡು"]):
            d["gender"] = "male"

    # --- Ration card: none / pending / AAY / BPL / APL / has a card (type unknown) ---
    if (re.search(r"\b(?:no|don'?t have|do not have|without|not have|haven'?t got)\s+(?:a\s+|any\s+)?ration\s*card", low)
            or "ರೇಷನ್ ಕಾರ್ಡ್ ಇಲ್ಲ" in low or "ಪಡಿತರ ಚೀಟಿ ಇಲ್ಲ" in low):
        d["ration_card"] = "none"
    elif (re.search(r"ration\s*card\s*(?:is\s*)?(?:pending|not yet (?:come|received|issued))"
                    r"|applied for (?:a\s+)?(?:new\s+)?ration\s*card", low)
            or "ಕಾರ್ಡ್‌ಗೆ ಅರ್ಜಿ" in low or "ಕಾರ್ಡ್ ಬಾಕಿ" in low):
        d["ration_card"] = "pending"
    elif has_word(low, ["aay", "antyodaya", "ಅಂತ್ಯೋದಯ"]):
        d["ration_card"] = "AAY"
    elif has_word(low, ["bpl", "phh", "priority household", "ಬಿಪಿಎಲ್", "ಆದ್ಯತಾ"]):
        d["ration_card"] = "BPL"
    elif has_word(low, ["apl", "nphh", "ಎಪಿಎಲ್"]):
        d["ration_card"] = "APL"
    elif has_word(low, ["ration card", "ರೇಷನ್ ಕಾರ್ಡ್", "ಪಡಿತರ ಚೀಟಿ"]):
        d["ration_card"] = "card_type_unknown"

    # --- Head of family ---
    if re.search(r"\bnot (?:the )?head of (?:the )?(?:family|household)", low):
        d["is_family_head"] = False
    elif re.search(r"\bhead of (?:the |my )?(?:family|household)", low) or "ಯಜಮಾನ" in low:
        d["is_family_head"] = True

    # --- Income tax / GST ---
    if (re.search(r"\b(?:don'?t|do not|never|not|no)\s+(?:pay\s+|paying\s+|file\s+)?(?:any\s+)?(?:income\s*tax|tax|gst)", low)
            or "ತೆರಿಗೆ ಕಟ್ಟುವುದಿಲ್ಲ" in low or "ತೆರಿಗೆ ಇಲ್ಲ" in low):
        d["pays_income_tax_or_gst"] = False
    elif (re.search(r"\b(?:pay|paying|file|filing)\s+(?:income\s*)?tax|\btaxpayer|\bpay gst|gst registered", low)
            or "ತೆರಿಗೆ ಕಟ್ಟುತ್ತೇ" in low):
        d["pays_income_tax_or_gst"] = True

    # --- Home electricity connection ---
    if re.search(r"\b(?:no|don'?t have|without)\s+(?:an?\s+)?(?:electricity|power|current)\s*(?:connection|meter)", low):
        d["has_home_electricity"] = False
    elif (re.search(r"\b(?:electricity|current|power)\s*(?:connection|meter|bill)", low)
            or "ವಿದ್ಯುತ್ ಸಂಪರ್ಕ" in low or "ಕರೆಂಟ್ ಬಿಲ್" in low):
        d["has_home_electricity"] = True

    # --- Highest education ---
    if has_word(low, ["diploma", "polytechnic", "ಡಿಪ್ಲೊಮಾ"]):
        d["qualification"] = "diploma"
    elif (re.search(r"\b(?:BA|BE|MA)\b", text)  # short degree names: capital letters only
          or re.search(r"\b(?:b\.a|b\.e|m\.a|b\.?sc|b\.?com|b\.?tech|bba|bca|mba|mca|m\.?sc|m\.?com|m\.?tech)\b", low)
          or has_word(low, ["graduate", "graduation", "degree", "post graduate", "postgraduate", "ಪದವಿ", "ಪದವೀಧರ"])):
        d["qualification"] = "degree"
    elif has_word(low, ["puc", "12th", "ಪಿಯುಸಿ"]):
        d["qualification"] = "puc"
    elif has_word(low, ["sslc", "10th", "ಎಸ್ಸೆಸ್ಸೆಲ್ಸಿ"]):
        d["qualification"] = "sslc"

    # --- Year of passing: "passed in 2023", "graduated 2023", "2023 batch", "2023ರಲ್ಲಿ ಉತ್ತೀರ್ಣ" ---
    match = (re.search(r"(?:passed|pass out|passed out|graduated|completed|finished|passing)\D{0,25}?\b((?:19|20)\d{2})\b", low)
             or re.search(r"\b((?:19|20)\d{2})\s*(?:pass|batch|passout|pass-out)", low)
             or re.search(r"((?:19|20)\d{2})[^\d]{0,12}(?:ಉತ್ತೀರ್ಣ|ಪಾಸ್)", low))
    if match:
        d["year_of_passing"] = int(match.group(1))

    # --- Months without a job: "unemployed for 8 months", "8 months without a job", "no job for 1 year" ---
    match = (re.search(r"(?:unemployed|no job|without (?:a )?job|jobless|not working)\D{0,20}?(\d{1,2})\s*(months?|years?)", low)
             or re.search(r"(\d{1,2})\s*(months?|years?)\s*(?:without|of no|of unemploy|with no)", low)
             or re.search(r"(\d{1,2})\s*(ತಿಂಗಳ|ವರ್ಷ)\S*\s*(?:ಇಂದ\s*)?(?:ಉದ್ಯೋಗ|ಕೆಲಸ)", low))
    if match:
        months = int(match.group(1))
        d["months_unemployed"] = months * 12 if match.group(2).startswith(("year", "ವರ್ಷ")) else months

    # --- Occupation ---
    for occupation, words in OCCUPATION_WORDS.items():
        if has_word(low, words):
            d["occupation"] = occupation
            break

    # --- Work status now ---
    if has_word(low, NO_JOB_WORDS):
        d["employment_status"] = "unemployed"
    elif re.search(r"\b(?:studying|pursuing|doing (?:my )?(?:masters|mba|mtech|msc|ma|pg)|higher studies)", low):
        d["employment_status"] = "higher_studies"
    elif d["occupation"] == "self-employed":
        d["employment_status"] = "self_employed"
    elif re.search(r"\b(?:working (?:at|in|as|for)|employed (?:at|in)|job at|got a job|i work|employee|salary)", low):
        d["employment_status"] = "employed"

    # --- Income: "1 lakh", "Rs 8000 per month", "50k", "ತಿಂಗಳಿಗೆ 8000 ರೂ" ---
    amount_pattern = (r"(₹|rs\.?|inr|rupees?|ರೂ\.?)?\s*(\d+(?:[.,]\d+)*)\s*"
                      r"(lakhs?|lacs?|ಲಕ್ಷ|thousand|ಸಾವಿರ|k\b)?\s*(rupees?|rs\b|ರೂ)?")
    for match in re.finditer(amount_pattern, low):
        currency = match.group(1) or match.group(4)
        unit = match.group(3)
        before = low[max(0, match.start() - 20):match.start()]
        after = low[match.end():match.end() + 20]
        income_word_before = any(w in before for w in ["income", "salary", "earn", "ಆದಾಯ", "ಸಂಬಳ", "ಗಳಿಕೆ"])
        if not (currency or unit or income_word_before):
            continue  # just a plain number (like an age or a year), not money
        amount = float(match.group(2).replace(",", ""))
        if unit and unit.startswith(("lakh", "lac", "ಲಕ್ಷ")):
            amount *= 100000
        elif unit:
            amount *= 1000
        month_words = ["month", "p.m", "pm", "ತಿಂಗಳ"]
        if any(w in before[-15:] or w in after for w in month_words):
            amount *= 12  # monthly -> yearly
        d["annual_income"] = int(amount)
        break

    # --- District ---
    for district, words in DISTRICTS.items():
        if has_word(low, words):
            d["district"] = district
            break

    return d
