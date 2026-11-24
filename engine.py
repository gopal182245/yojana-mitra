"""
engine.py - the ELIGIBILITY ENGINE (plain Python, no AI, no Streamlit).

It compares a person's details with the rules in schemes.json and gives each scheme
one of three outcomes:

    ELIGIBLE         - every rule is met
    NOT_ELIGIBLE     - at least one rule is clearly not met
    NEEDS_MORE_INFO  - nothing fails, but some information is missing,
                       or a rule needs official verification

Important promises:
  * We NEVER say ELIGIBLE when a rule's information is missing.
  * We only use rules written in schemes.json. Anything else is shown as
    "needs official verification" - we never invent rules.
"""

import json
from pathlib import Path

SCHEMES_FILE = Path(__file__).parent / "schemes.json"

ELIGIBLE = "ELIGIBLE"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
NEEDS_MORE_INFO = "NEEDS_MORE_INFO"

# ---------------------------------------------------------------------------
# Every piece of information we may need about a person.
#   type     : "text", "number", "choice" or "yesno"
#   en / kn  : label shown on screen
#   q_en/q_kn: the follow-up question we ask when it is missing
#   options  : for "choice" fields -> {stored value: (English, Kannada)}
#   ai_hint  : extra instructions for Gemini
# ---------------------------------------------------------------------------
YES_NO = {True: ("Yes", "ಹೌದು"), False: ("No", "ಇಲ್ಲ")}

FIELDS = {
    "name": {"type": "text", "en": "Name", "kn": "ಹೆಸರು"},
    "age": {"type": "number", "en": "Age", "kn": "ವಯಸ್ಸು",
            "q_en": "How old are you?", "q_kn": "ನಿಮ್ಮ ವಯಸ್ಸು ಎಷ್ಟು?"},
    "gender": {"type": "choice", "en": "Gender", "kn": "ಲಿಂಗ",
               "q_en": "Are you a woman or a man?", "q_kn": "ನೀವು ಮಹಿಳೆಯೇ ಅಥವಾ ಪುರುಷರೇ?",
               "options": {"female": ("Woman", "ಮಹಿಳೆ"), "male": ("Man", "ಪುರುಷ"), "other": ("Other", "ಇತರೆ")}},
    "marital_status": {"type": "choice", "en": "Marital status", "kn": "ವೈವಾಹಿಕ ಸ್ಥಿತಿ",
                       "q_en": "Are you married, widowed or single?", "q_kn": "ನೀವು ವಿವಾಹಿತರೇ, ವಿಧವೆಯೇ ಅಥವಾ ಅವಿವಾಹಿತರೇ?",
                       "options": {"married": ("Married", "ವಿವಾಹಿತ"), "widow": ("Widowed", "ವಿಧವೆ / ವಿಧುರ"),
                                   "single": ("Single", "ಅವಿವಾಹಿತ"), "separated": ("Separated / divorced", "ಬೇರ್ಪಟ್ಟ / ವಿಚ್ಛೇದಿತ")}},
    "annual_income": {"type": "number", "en": "Family income per year (Rs.)", "kn": "ಕುಟುಂಬದ ವಾರ್ಷಿಕ ಆದಾಯ (ರೂ.)",
                      "q_en": "What is your family's total income in a year (Rs.)?",
                      "q_kn": "ನಿಮ್ಮ ಕುಟುಂಬದ ಒಟ್ಟು ವಾರ್ಷಿಕ ಆದಾಯ ಎಷ್ಟು (ರೂ.)?",
                      "ai_hint": "yearly FAMILY income in rupees; monthly x 12; '1 lakh' = 100000"},
    "occupation": {"type": "choice", "en": "Occupation", "kn": "ಉದ್ಯೋಗ",
                   "q_en": "What work do you do?", "q_kn": "ನೀವು ಯಾವ ಕೆಲಸ ಮಾಡುತ್ತೀರಿ?",
                   "options": {"farmer": ("Farmer", "ರೈತ"), "daily wage worker": ("Daily wage worker", "ದಿನಗೂಲಿ ಕಾರ್ಮಿಕ"),
                               "homemaker": ("Homemaker", "ಗೃಹಿಣಿ"), "salaried": ("Salaried job", "ಸಂಬಳದ ಉದ್ಯೋಗ"),
                               "self-employed": ("Self-employed / business", "ಸ್ವಂತ ಉದ್ಯೋಗ / ವ್ಯಾಪಾರ"),
                               "student": ("Student", "ವಿದ್ಯಾರ್ಥಿ"), "unemployed": ("No job", "ಉದ್ಯೋಗವಿಲ್ಲ"),
                               "retired": ("Retired", "ನಿವೃತ್ತ"), "other": ("Other", "ಇತರೆ")}},
    "district": {"type": "text", "en": "District", "kn": "ಜಿಲ್ಲೆ",
                 "ai_hint": "Karnataka district name in English, e.g. Mysuru"},
    "ration_card": {"type": "choice", "en": "Ration card", "kn": "ರೇಷನ್ ಕಾರ್ಡ್",
                    "q_en": "Which ration card do you have?", "q_kn": "ನಿಮ್ಮ ಬಳಿ ಯಾವ ರೇಷನ್ ಕಾರ್ಡ್ ಇದೆ?",
                    "options": {"BPL": ("BPL card", "ಬಿಪಿಎಲ್ ಕಾರ್ಡ್"), "AAY": ("Antyodaya (AAY) card", "ಅಂತ್ಯೋದಯ ಕಾರ್ಡ್"),
                                "APL": ("APL card", "ಎಪಿಎಲ್ ಕಾರ್ಡ್"), "pending": ("Applied, still pending", "ಅರ್ಜಿ ಹಾಕಿದ್ದೇನೆ, ಇನ್ನೂ ಬಂದಿಲ್ಲ"),
                                "none": ("No ration card", "ರೇಷನ್ ಕಾರ್ಡ್ ಇಲ್ಲ")},
                    # "card_type_unknown" is also allowed: they have a card but didn't say which
                    "ai_hint": "BPL / AAY / APL if they have that card; 'card_type_unknown' if they have a card "
                               "but did not say which; 'pending' if they applied and are waiting; 'none' if they "
                               "clearly have no card; null if ration card is not mentioned at all. "
                               "Kannada: ಬಿಪಿಎಲ್/ಆದ್ಯತಾ=BPL, ಅಂತ್ಯೋದಯ=AAY, ಎಪಿಎಲ್=APL"},
    "is_family_head": {"type": "yesno", "en": "Head of family on ration card", "kn": "ರೇಷನ್ ಕಾರ್ಡ್‌ನಲ್ಲಿ ಕುಟುಂಬದ ಯಜಮಾನ/ಯಜಮಾನಿ",
                       "q_en": "Are you shown as the head of the family on the ration card?",
                       "q_kn": "ರೇಷನ್ ಕಾರ್ಡ್‌ನಲ್ಲಿ ನೀವು ಕುಟುಂಬದ ಯಜಮಾನ/ಯಜಮಾನಿ ಎಂದು ಇದೆಯೇ?", "options": YES_NO},
    "pays_income_tax_or_gst": {"type": "yesno", "en": "Self/spouse pays income tax or GST", "kn": "ತಾವು/ಪತಿ-ಪತ್ನಿ ಆದಾಯ ತೆರಿಗೆ / ಜಿಎಸ್‌ಟಿ ಪಾವತಿ",
                               "q_en": "Do you or your husband/wife pay income tax or GST?",
                               "q_kn": "ನೀವು ಅಥವಾ ನಿಮ್ಮ ಪತಿ/ಪತ್ನಿ ಆದಾಯ ತೆರಿಗೆ ಅಥವಾ ಜಿಎಸ್‌ಟಿ ಪಾವತಿಸುತ್ತೀರಾ?", "options": YES_NO},
    "has_home_electricity": {"type": "yesno", "en": "Home electricity connection", "kn": "ಮನೆಗೆ ವಿದ್ಯುತ್ ಸಂಪರ್ಕ",
                             "q_en": "Does your home have its own electricity connection (meter)?",
                             "q_kn": "ನಿಮ್ಮ ಮನೆಗೆ ಸ್ವಂತ ವಿದ್ಯುತ್ ಸಂಪರ್ಕ (ಮೀಟರ್) ಇದೆಯೇ?", "options": YES_NO},
    "qualification": {"type": "choice", "en": "Highest education", "kn": "ಅತ್ಯುನ್ನತ ವಿದ್ಯಾರ್ಹತೆ",
                      "q_en": "What is your highest education?", "q_kn": "ನಿಮ್ಮ ಅತ್ಯುನ್ನತ ವಿದ್ಯಾರ್ಹತೆ ಯಾವುದು?",
                      "options": {"degree": ("Degree (BA, BSc, BCom, BE, MA...)", "ಪದವಿ (ಬಿಎ, ಬಿಎಸ್ಸಿ, ಬಿಕಾಂ, ಬಿಇ, ಎಂಎ...)"),
                                  "diploma": ("Diploma", "ಡಿಪ್ಲೊಮಾ"), "puc": ("PUC / 12th", "ಪಿಯುಸಿ / 12ನೇ"),
                                  "sslc": ("SSLC / 10th", "ಎಸ್ಸೆಸ್ಸೆಲ್ಸಿ / 10ನೇ"), "below_sslc": ("Below 10th", "10ನೇ ಕೆಳಗೆ")},
                      "ai_hint": "'degree' for any university degree (bachelor's or master's)"},
    "year_of_passing": {"type": "number", "en": "Year of passing", "kn": "ಉತ್ತೀರ್ಣರಾದ ವರ್ಷ",
                        "q_en": "In which year did you pass your degree/diploma?", "q_kn": "ನಿಮ್ಮ ಪದವಿ/ಡಿಪ್ಲೊಮಾ ಯಾವ ವರ್ಷದಲ್ಲಿ ಉತ್ತೀರ್ಣರಾದಿರಿ?"},
    "months_unemployed": {"type": "number", "en": "Months without a job since passing", "kn": "ಉತ್ತೀರ್ಣರಾದ ನಂತರ ಉದ್ಯೋಗವಿಲ್ಲದ ತಿಂಗಳುಗಳು",
                          "q_en": "Since passing, for how many months have you been without a job?",
                          "q_kn": "ಉತ್ತೀರ್ಣರಾದ ನಂತರ ಎಷ್ಟು ತಿಂಗಳಿಂದ ಉದ್ಯೋಗವಿಲ್ಲ?",
                          "ai_hint": "number of months; '1 year' = 12"},
    "employment_status": {"type": "choice", "en": "Work status now", "kn": "ಈಗಿನ ಉದ್ಯೋಗ ಸ್ಥಿತಿ",
                          "q_en": "Right now, are you working, studying, or without a job?",
                          "q_kn": "ಈಗ ನೀವು ಕೆಲಸ ಮಾಡುತ್ತಿದ್ದೀರಾ, ಓದುತ್ತಿದ್ದೀರಾ ಅಥವಾ ಉದ್ಯೋಗವಿಲ್ಲವೇ?",
                          "options": {"unemployed": ("No job", "ಉದ್ಯೋಗವಿಲ್ಲ"), "employed": ("Working (job)", "ಉದ್ಯೋಗದಲ್ಲಿದ್ದೇನೆ"),
                                      "self_employed": ("Self-employed / business", "ಸ್ವಂತ ಉದ್ಯೋಗ"),
                                      "higher_studies": ("Studying further", "ಮುಂದಿನ ವ್ಯಾಸಂಗ")}},
}


def load_schemes():
    with open(SCHEMES_FILE, encoding="utf-8") as f:
        return json.load(f)


def tr(item, key, lang):
    """Pick the Kannada or English version: tr(scheme, "name", "kn") -> scheme["name_kn"]."""
    if lang == "kn" and item.get(key + "_kn"):
        return item[key + "_kn"]
    return item[key]


def show_value(field, value, lang):
    """Turn a stored value into words for the screen, e.g. ("gender", "female") -> "ಮಹಿಳೆ"."""
    if value is None or value == "":
        return "-"
    info = FIELDS.get(field, {})
    if field == "ration_card" and value == "card_type_unknown":
        return "ಕಾರ್ಡ್ ಇದೆ, ಪ್ರಕಾರ ತಿಳಿದಿಲ್ಲ" if lang == "kn" else "Has a card, type not known"
    if "options" in info and value in info["options"]:
        en, kn = info["options"][value]
        return kn if lang == "kn" else en
    if field == "annual_income":
        return f"{value:,}"
    return str(value)


# ---------------------------------------------------------------------------
# Checking rules
# ---------------------------------------------------------------------------
def check_rule(rule, person):
    """
    Check one rule. Returns one of:
      "met"        - the person meets it
      "not_met"    - the person clearly does not meet it
      "missing"    - we don't have the information yet
      "unverified" - doesn't match our data, BUT our rule itself needs official verification,
                     so we must not say "not eligible" because of it
    """
    value = person.get(rule["field"])
    if rule["field"] == "ration_card" and value == "card_type_unknown":
        value = None  # has a card, but we need the type -> still missing
    if value is None or value == "":
        return "missing"

    op, target = rule["op"], rule.get("value")
    if op == "equals":
        ok = value == target
    elif op == "in":
        ok = value in target
    elif op == "min":
        ok = value >= target
    elif op == "max":
        ok = value <= target
    elif op == "is_true":
        ok = value is True
    elif op == "is_false":
        ok = value is False
    else:
        raise ValueError(f"Unknown rule op: {op}")  # a typo in schemes.json

    if ok:
        return "met"
    return "unverified" if rule.get("needs_official_check") else "not_met"


def evaluate_scheme(scheme, person):
    """Check all rules of one scheme. Returns a dict describing the result."""
    result = {"scheme": scheme, "met": [], "not_met": [], "missing": [], "unverified": [],
              "missing_fields": []}
    for rule in scheme["rules"]:
        outcome = check_rule(rule, person)
        result[outcome].append(rule)
        if outcome == "missing" and rule["field"] not in result["missing_fields"]:
            result["missing_fields"].append(rule["field"])

    if result["not_met"]:
        result["status"] = NOT_ELIGIBLE
    elif result["missing"] or result["unverified"]:
        result["status"] = NEEDS_MORE_INFO  # never ELIGIBLE with missing info
    else:
        result["status"] = ELIGIBLE
    return result


def check_all(person, schemes=None):
    """Check every scheme. Order: ELIGIBLE, then NEEDS_MORE_INFO, then NOT_ELIGIBLE;
    inside each group, schemes with more conditions met (and fewer missing) come first."""
    schemes = schemes if schemes is not None else load_schemes()
    results = [evaluate_scheme(s, person) for s in schemes]
    order = {ELIGIBLE: 0, NEEDS_MORE_INFO: 1, NOT_ELIGIBLE: 2}
    results.sort(key=lambda r: (order[r["status"]], -len(r["met"]), len(r["missing_fields"])))
    return results


def pick_questions(results, skipped=(), max_questions=3):
    """
    Choose the 1-3 most useful follow-up questions.

    A missing field gets points from every NEEDS_MORE_INFO scheme that needs it:
      * more points if that scheme is close to done (few other missing fields), and
      * more points if the person already meets some of its conditions.
    Fields the person chose to skip ("I don't know") are never asked again.
    """
    scores = {}
    for result in results:
        if result["status"] != NEEDS_MORE_INFO:
            continue
        missing = result["missing_fields"]
        for field in missing:
            if field in skipped or "q_en" not in FIELDS[field]:
                continue
            points = (1 + 2 * len(result["met"])) / len(missing)
            scores[field] = scores.get(field, 0) + points
    best = sorted(scores, key=lambda f: -scores[f])
    return best[:max_questions]


def readiness(result, person, docs_ticked, form_done, lang):
    """
    How ready is the person to apply for this scheme?
      docs_ticked: list of True/False, one per document ("I have it")
      form_done  : True if they downloaded the filled draft form
    Returns {"percent": 0-100, "done": [text...], "remaining": [text...]}.
    This is only a helper checklist - NOT official approval.
    """
    kn = lang == "kn"
    scheme = result["scheme"]
    done, remaining = [], []

    for rule in result["met"]:
        done.append(rule_reason(rule, person, lang))
    for rule in result["missing"]:
        question = FIELDS[rule["field"]]["q_kn" if kn else "q_en"]
        remaining.append(("ಉತ್ತರಿಸಿ: " if kn else "Answer: ") + question)
    for rule in result["unverified"] + result["not_met"]:
        remaining.append(("ಕಚೇರಿಯಲ್ಲಿ ಖಚಿತಪಡಿಸಿ: " if kn else "Confirm at the office: ") + rule_reason(rule, person, lang))

    documents = scheme["documents_kn"] if kn else scheme["documents"]
    for doc, have_it in zip(documents, docs_ticked):
        if have_it:
            done.append(("ದಾಖಲೆ ಸಿದ್ಧ: " if kn else "Document ready: ") + doc)
        else:
            remaining.append(("ದಾಖಲೆ ತಯಾರಿಸಿ: " if kn else "Get document: ") + doc)

    form_text = "ಭರ್ತಿ ಮಾಡಿದ ಅರ್ಜಿ ಕರಡು ಡೌನ್‌ಲೋಡ್" if kn else "Download the filled draft form"
    (done if form_done else remaining).append(form_text)

    total = len(done) + len(remaining)
    percent = round(100 * len(done) / total) if total else 0
    return {"percent": percent, "done": done, "remaining": remaining}


def rule_reason(rule, person, lang):
    """A short line like 'Age 65 or above (you: 62)'."""
    text = rule["kn"] if lang == "kn" else rule["en"]
    value = person.get(rule["field"])
    if value is not None:
        you = "ನೀವು" if lang == "kn" else "you"
        text += f" ({you}: {show_value(rule['field'], value, lang)})"
    if rule["field"] == "ration_card" and value == "pending":
        text += (" - ಕಾರ್ಡ್ ಬಂದ ನಂತರ ಅರ್ಜಿ ಸಲ್ಲಿಸಿ" if lang == "kn"
                 else " - you can apply once your card is issued")
    return text


def normalize_person(person):
    """Fill in obvious links between fields (only when the field is still empty)."""
    p = dict(person)
    job_to_status = {"unemployed": "unemployed", "salaried": "employed",
                     "self-employed": "self_employed", "student": "higher_studies"}
    if p.get("employment_status") is None and p.get("occupation") in job_to_status:
        p["employment_status"] = job_to_status[p["occupation"]]
    return p
