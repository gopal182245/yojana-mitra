"""
Yojana Mitra (ಯೋಜನಾ ಮಿತ್ರ) - helps people in Karnataka find government schemes.

Files:
  app.py       - this file: the screen (Streamlit)
  engine.py    - eligibility rules engine (ELIGIBLE / NOT ELIGIBLE / NEEDS MORE INFO)
  ai.py        - understanding voice / text / photo with Gemini (+ offline backup for text)
  pdf_form.py  - the filled draft application PDF
  texts.py     - all screen text in English and Kannada (+ demo people)
  schemes.json - the schemes and their rules

The agent's steps, shown in the tracker at the top of the page:
  1 Tell us   -> 2 Check eligibility -> 3 Follow-up questions -> 4 Prepare (form, documents) -> 5 Listen

Run it with:  streamlit run app.py
"""

from io import BytesIO

import streamlit as st
from gtts import gTTS

import ai
import engine
from engine import ELIGIBLE, FIELDS, NEEDS_MORE_INFO, NOT_ELIGIBLE, show_value, tr
from pdf_form import make_pdf
from texts import PERSONAS, T

st.set_page_config(page_title="Yojana Mitra", page_icon="🤝", layout="centered")

# ---------------------------------------------------------------------------
# Look and feel. Plain CSS, added once at the top of the page.
#   Cards are st.container(border=True, key="ymc_...") - Streamlit turns the key into the CSS
#   class "st-key-ymc_...", which is how the styles below find them.
# ---------------------------------------------------------------------------
CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Kannada:wght@400;500;600;700;800&display=swap');

  /* ---- Global: ivory page, Inter + Noto Sans Kannada ---- */
  .stApp { background: #FFFCF4; }
  .stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input, .stApp textarea,
  .stApp div, .stApp span:not([data-testid="stIconMaterial"]) {
      font-family: "Inter", "Noto Sans Kannada", system-ui, sans-serif; }
  .stApp p, .stApp li { color: #1F2933; }
  .stApp button p { color: inherit !important; }   /* keep white text on green buttons */
  .stApp button[kind="primary"] p { font-weight: 700; }
  .block-container { padding-top: 3rem; padding-bottom: 2rem; max-width: 820px; }

  /* ---- Hide Streamlit's Deploy button, menu, toolbar and footer (keep the sidebar button) ---- */
  [data-testid="stToolbar"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
  [data-testid="stStatusWidget"], [data-testid="stDecoration"], footer, #MainMenu { display: none !important; }
  [data-testid="stHeader"] { background: transparent; }

  /* ---- White cards: soft shadow, 16px corners ---- */
  [class*="st-key-ymc_"] {
      background: #FFFFFF; border: 1px solid #EFE8DA !important; border-radius: 16px !important;
      box-shadow: 0 1px 2px rgba(16, 24, 40, .04), 0 6px 18px rgba(16, 24, 40, .06); }
  [class*="st-key-ymc_ok_"]   { border-left: 6px solid #16A34A !important; }
  [class*="st-key-ymc_info_"] { border-left: 6px solid #F59E0B !important; }
  [class*="st-key-ymc_no_"]   { border-left: 6px solid #94A3B8 !important; }
  [data-testid="stExpander"] details { background: #FFFFFF; border-radius: 12px !important; border-color: #EFE8DA !important; }

  /* ---- Header (hero) ---- */
  .ym-hero { background: linear-gradient(135deg, #065F46 0%, #059669 48%, #6EE7B7 100%);
             border-radius: 20px; padding: 22px 22px 18px; margin-bottom: 16px;
             box-shadow: 0 12px 30px rgba(5, 150, 105, .25); }
  .ym-hero-top { display: flex; align-items: center; gap: 14px; }
  .ym-logo { width: 56px; height: 56px; flex-shrink: 0; border-radius: 16px; background: #FFFFFF;
             display: flex; align-items: center; justify-content: center; font-size: 30px;
             box-shadow: 0 4px 12px rgba(0, 0, 0, .15); }
  .ym-title { color: #FFFFFF; font-size: 1.7rem; font-weight: 800; line-height: 1.2; }
  .ym-title span { font-weight: 600; opacity: .92; }
  .ym-tagline { color: #ECFDF5; font-size: 1.05rem; margin: 12px 0 12px; font-weight: 500; }
  .ym-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .ym-chip { background: rgba(255, 255, 255, .18); border: 1px solid rgba(255, 255, 255, .4); color: #FFFFFF;
             border-radius: 999px; padding: 5px 12px; font-size: .82rem; font-weight: 600; white-space: nowrap; }

  /* ---- Step tracker ---- */
  .ym-tracker { display: flex; gap: 6px; margin: 0 0 8px; }
  .ym-step { flex: 1; min-width: 0; text-align: center; padding: 7px 2px; border-radius: 12px; font-size: .76rem;
             background: #F4F1EA; color: #7B8794; line-height: 1.25; overflow-wrap: anywhere; }
  .ym-step b { display: block; font-size: .95rem; }
  .ym-step.done { background: #DCFCE7; color: #166534; }
  .ym-step.current { background: #FEF3C7; color: #92400E; font-weight: 700; box-shadow: inset 0 0 0 2px #F59E0B; }

  /* ---- Section titles ---- */
  .ym-sec { display: flex; align-items: center; gap: 10px; font-size: 1.2rem; font-weight: 800;
            margin: 26px 0 10px; color: #1F2933; }
  .ym-sec .n { background: #059669; color: #FFFFFF; border-radius: 50%; min-width: 30px; height: 30px;
               display: inline-flex; align-items: center; justify-content: center; font-size: .9rem; }

  /* ---- Demo person cards ---- */
  .ym-p-emoji { font-size: 2.1rem; line-height: 1.1; }
  .ym-p-name { font-weight: 700; font-size: 1.02rem; color: #1F2933; margin-top: 4px; }
  .ym-p-desc { color: #52606D; font-size: .84rem; min-height: 2.5em; line-height: 1.3; }

  /* ---- Result tiles: green / amber / grey ---- */
  .ym-tiles { display: flex; gap: 10px; margin: 2px 0 14px; }
  .ym-tile { flex: 1; min-width: 0; border-radius: 16px; padding: 14px 6px; text-align: center;
             font-size: .9rem; font-weight: 700; }
  .ym-tile b { display: block; font-size: 2.3rem; font-weight: 800; line-height: 1.1; }
  .ym-tile.ok, .ym-badge.ok { background: #DCFCE7; color: #166534; }
  .ym-tile.info, .ym-badge.info { background: #FEF3C7; color: #92400E; }
  .ym-tile.no, .ym-badge.no { background: #F1F5F9; color: #475569; }

  /* ---- Scheme cards ---- */
  .ym-card-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  .ym-card-head .name { font-size: 1.15rem; font-weight: 700; color: #1F2933; }
  .ym-badge { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: .76rem;
              font-weight: 800; letter-spacing: .03em; white-space: nowrap; }
  .ym-benefit { font-size: 1.4rem; font-weight: 800; color: #065F46; margin: 6px 0 2px; line-height: 1.25; }
  .ym-benefit-note { color: #52606D; font-size: .9rem; }
  .ym-counts { color: #52606D; font-size: .86rem; margin-top: 6px; }

  /* ---- Readiness ring ---- */
  .ym-ring { display: flex; flex-direction: column; align-items: center; gap: 4px; }
  .ym-ring-label { font-weight: 700; color: #065F46; text-align: center; }

  /* ---- Footer ---- */
  .ym-footer { margin-top: 36px; padding: 16px 12px; text-align: center; color: #52606D; font-size: .82rem;
               border-top: 1px solid #EFE8DA; line-height: 1.6; }

  /* ---- Phones (375px): smaller type, no sideways scrolling ---- */
  @media (max-width: 640px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 2.6rem; }
    .ym-title { font-size: 1.3rem; }
    .ym-tagline { font-size: .95rem; }
    .ym-step { font-size: .62rem; padding: 6px 1px; }
    .ym-tile b { font-size: 1.8rem; }
    .ym-tile { font-size: .78rem; }
  }
</style>
"""

STATUS_STYLE = {ELIGIBLE: ("ok", "✅"), NEEDS_MORE_INFO: ("info", "❓"), NOT_ELIGIBLE: ("no", "❌")}

# Short names for rules that need official confirmation: field -> (English, Kannada)
VERIFY_LABEL = {
    "age": ("Age limit", "ವಯೋಮಿತಿ"),
    "annual_income": ("Income limit", "ಆದಾಯ ಮಿತಿ"),
    "year_of_passing": ("Eligible year of passing", "ಅರ್ಹ ಉತ್ತೀರ್ಣ ವರ್ಷ"),
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def get_api_key():
    """Read the key from .streamlit/secrets.toml. Returns None if it is missing."""
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return None


@st.cache_data
def load_schemes():
    return engine.load_schemes()


@st.cache_data
def cached_pdf(person, scheme):
    return make_pdf(person, scheme)


VOICE_TIMEOUT_SECONDS = 15  # gTTS has no time limit by default - never let it hang


@st.cache_data(show_spinner=False)
def speak(text, lang):
    """Turn text into speech (MP3 bytes). gTTS needs internet."""
    audio = BytesIO()
    gTTS(text=text, lang=lang, timeout=VOICE_TIMEOUT_SECONDS).write_to_fp(audio)
    return audio.getvalue()


def html(code):
    st.markdown(code, unsafe_allow_html=True)


def section(number, title):
    html(f'<div class="ym-sec"><span class="n">{number}</span>{title}</div>')


def card(name):
    """A white rounded card (styled by the CSS rule for "st-key-ymc_...")."""
    return st.container(border=True, key=f"ymc_{name}")


def render_hero():
    chips = "".join(f'<span class="ym-chip">{chip}</span>' for chip in L["chips"])
    html('<div class="ym-hero">'
         '<div class="ym-hero-top"><div class="ym-logo">🤝</div>'
         '<div class="ym-title">Yojana Mitra <span>/ ಯೋಜನಾ ಮಿತ್ರ</span></div></div>'
         f'<div class="ym-tagline">{L["hero_tagline"]}</div>'
         f'<div class="ym-chips">{chips}</div></div>')


def render_footer():
    html(f'<div class="ym-footer">{L["footer"]}</div>')


def ring_svg(percent):
    """A circular progress ring with the % in the middle (plain SVG)."""
    radius = 52
    circumference = 2 * 3.14159 * radius
    gap = circumference * (1 - percent / 100)
    return (f'<svg viewBox="0 0 120 120" width="140" height="140" role="img" aria-label="{percent}%">'
            f'<circle cx="60" cy="60" r="{radius}" fill="none" stroke="#E7E1D4" stroke-width="12"/>'
            f'<circle cx="60" cy="60" r="{radius}" fill="none" stroke="#059669" stroke-width="12" '
            f'stroke-linecap="round" stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{gap:.1f}" '
            f'transform="rotate(-90 60 60)"/>'
            f'<text x="60" y="68" text-anchor="middle" font-size="28" font-weight="800" fill="#065F46" '
            f'font-family="Inter, sans-serif">{percent}%</text></svg>')


def render_tracker(current):
    """The 5-step tracker. Steps before `current` are done (green), `current` is orange."""
    boxes = []
    for i, name in enumerate(L["track"], start=1):
        state = "done" if i < current else "current" if i == current else ""
        mark = "✓" if i < current else str(i)
        boxes.append(f'<div class="ym-step {state}"><b>{mark}</b>{name}</div>')
    html(f'<div class="ym-tracker">{"".join(boxes)}</div>')


# ---------------------------------------------------------------------------
# STEP 1: understand the person
# ---------------------------------------------------------------------------
def understand(typed, voice, photo):
    """Run Gemini (or the offline reader). Saves the details in session_state.
    Returns True if it worked."""
    message_box = st.empty()  # friendly "AI is busy, retrying..." messages appear here

    def notify(key, **values):
        message_box.info(L[key].format(**values))

    # Check the voice note first (empty / silent recordings), without waiting for the AI
    if voice:
        recording = ai.check_recording(voice.getvalue())
        if recording != "ok":
            if not (typed or photo):
                message_box.warning(L["rec_" + recording])
                return False
            voice = None  # we still have text or a photo - just ignore the bad recording

    with st.status(L["agent_working"], expanded=True) as status:
        st.write(L["agent_read"])
        try:
            person = ai.extract_details(
                get_api_key(),
                typed,
                voice.getvalue() if voice else None,
                voice.type if voice else None,
                photo.getvalue() if photo else None,
                photo.type if photo else None,
                notify,
            )
            used_offline = False
        except Exception as error:
            print(f"[Yojana Mitra] AI failed completely: {error!r}")  # for you, in the terminal
            if not typed:
                status.update(label=L["ai_failed"], state="error")
                message_box.error(L["ai_failed"])
                return False
            person = ai.parse_text_offline(typed)  # backup plan: read typed text without AI
            used_offline = True

        # If nothing at all was understood (silent / noisy recording), don't go on
        if not any(value is not None for value in person.values()):
            status.update(label=L["not_understood"], state="error")
            message_box.warning(L["not_understood"])
            return False

        st.write(L["agent_checked"].format(n=len(load_schemes())))
        status.update(label=L["agent_done"], state="complete", expanded=False)

    message_box.empty()
    # Save in session_state so it survives when Streamlit reruns
    st.session_state["person"] = engine.normalize_person(person)
    st.session_state["used_offline"] = used_offline
    st.session_state["skipped"] = []  # new person -> forget old "I don't know" answers
    return True


def render_details(person):
    if st.session_state.get("used_offline"):
        st.info(L["ai_offline"])
    known = [(key, value) for key, value in person.items() if value is not None]
    with card("details"):
        cols = st.columns(2)
        for i, (key, value) in enumerate(known):
            cols[i % 2].markdown(f"**{FIELDS[key][lang]}:** {show_value(key, value, lang)}")


# ---------------------------------------------------------------------------
# STEP 2: eligibility - one card per scheme
# ---------------------------------------------------------------------------
def scheme_details(result, person):
    """Everything about one scheme: conditions, documents, how to apply, sources."""
    scheme = result["scheme"]
    if result["met"]:
        st.markdown(f"**{L['met']}**")
        for rule in result["met"]:
            extra = f" _({L['to_verify']})_" if rule.get("needs_official_check") else ""
            st.markdown(f"- ✅ {engine.rule_reason(rule, person, lang)}{extra}")
    if result["not_met"]:
        st.markdown(f"**{L['not_met']}**")
        for rule in result["not_met"]:
            st.markdown(f"- ❌ {engine.rule_reason(rule, person, lang)}")
    if result["missing"]:
        st.markdown(f"**{L['missing']}**")
        for rule in result["missing"]:
            st.markdown(f"- ❓ {engine.rule_reason(rule, person, lang)}")

    # Things we cannot decide: rules marked "needs_official_check" that didn't match,
    # and conditions we know about but have no rule for in schemes.json
    to_verify = [f"{engine.rule_reason(r, person, lang)} — {L['unverified_rule']}" for r in result["unverified"]]
    to_verify += [c["kn"] if lang == "kn" else c["en"] for c in scheme.get("other_conditions", [])]
    if to_verify:
        st.markdown(f"**{L['to_verify']}**")
        for line in to_verify:
            st.markdown(f"- 🔎 {line}")

    st.markdown(f"**{L['documents']}:** " + ", ".join(tr(scheme, "documents", lang)))
    st.markdown(f"**{L['how_to_apply']}:** {tr(scheme, 'how_to_apply', lang)}")
    st.markdown(f"**{L['official_source']}:** [{scheme['source_link']}]({scheme['source_link']})")
    st.markdown(f"**{L['last_verified']}:** {scheme.get('last_verified') or L['not_verified']}")
    if scheme.get("research_links"):
        links = " · ".join(f"[{i + 1}]({url})" for i, url in enumerate(scheme["research_links"]))
        st.caption(f"{L['research_links']}: {links}")


def render_scheme_card(result, person, with_details_box=True):
    scheme = result["scheme"]
    style, icon = STATUS_STYLE[result["status"]]
    with card(f"{style}_{scheme['id']}"):  # the key decides the coloured left border
        html(f'<div class="ym-card-head"><span class="name">{tr(scheme, "name", lang)}</span>'
             f'<span class="ym-badge {style}">{icon} {L["status_" + result["status"]]}</span></div>'
             f'<div class="ym-benefit">{tr(scheme, "benefit_short", lang)}</div>'
             f'<div class="ym-benefit-note">{tr(scheme, "benefits", lang)}</div>')
        verify = len(result["unverified"]) + len(scheme.get("other_conditions", []))
        html(f'<div class="ym-counts">✅ {len(result["met"])} {L["met_short"]} · '
             f'❓ {len(result["missing"])} {L["missing_short"]} · '
             f'🔎 {verify} {L["verify_short"]}</div>')
        # Nothing is missing, only rules we could not confirm -> say exactly which, in plain words
        if result["status"] == NEEDS_MORE_INFO and not result["missing"] and result["unverified"]:
            names = []
            for rule in result["unverified"]:
                short = VERIFY_LABEL.get(rule["field"], (FIELDS[rule["field"]]["en"], FIELDS[rule["field"]]["kn"]))
                name = short[1] if lang == "kn" else short[0]
                if name not in names:
                    names.append(name)
            joiner = " ಮತ್ತು " if lang == "kn" else " and "
            st.info(L["only_verify"].format(what=joiner.join(names)))
        if with_details_box:
            with st.expander(L["details_btn"]):
                scheme_details(result, person)
        else:
            scheme_details(result, person)  # already inside an expander (Streamlit can't nest them)


def render_results(person, results):
    counts = {status: sum(r["status"] == status for r in results) for status in STATUS_STYLE}
    html('<div class="ym-tiles">'
         f'<div class="ym-tile ok"><b>{counts[ELIGIBLE]}</b>{L["tile_ok"]}</div>'
         f'<div class="ym-tile info"><b>{counts[NEEDS_MORE_INFO]}</b>{L["tile_info"]}</div>'
         f'<div class="ym-tile no"><b>{counts[NOT_ELIGIBLE]}</b>{L["tile_no"]}</div></div>')

    if st.session_state.pop("rechecked", False):
        st.success(L["rechecked"])
    render_questions(results)

    for result in results:
        if result["status"] != NOT_ELIGIBLE:
            render_scheme_card(result, person)
    not_eligible = [r for r in results if r["status"] == NOT_ELIGIBLE]
    if not_eligible:
        with st.expander(f"❌ {L['not_eligible_heading'].format(n=len(not_eligible))}"):
            for result in not_eligible:
                render_scheme_card(result, person, with_details_box=False)
    st.caption(L["data_warning"])


# ---------------------------------------------------------------------------
# Follow-up questions: ask only the 1-3 answers we need, then check again
# ---------------------------------------------------------------------------
def question_widget(field, key):
    """Show the right input for one question. Returns the answer, or None if left empty."""
    info = FIELDS[field]
    question = info["q_kn"] if lang == "kn" else info["q_en"]
    if info["type"] == "number":
        biggest = 100_000_000 if field == "annual_income" else 3000
        return st.number_input(question, min_value=0, max_value=biggest, value=None, step=1, key=key)
    return st.radio(question, list(info["options"]), index=None, horizontal=True, key=key,
                    format_func=lambda value: show_value(field, value, lang))


def save_answers(answers):
    """Add the answers to the person's details. Empty answers = "I don't know" (never asked again)."""
    person = dict(st.session_state["person"])
    skipped = st.session_state.setdefault("skipped", [])
    for field, value in answers.items():
        if value is None:
            skipped.append(field)
        else:
            person[field] = value
    st.session_state["person"] = engine.normalize_person(person)
    st.session_state["rechecked"] = True


def render_questions(results):
    fields = engine.pick_questions(results, st.session_state.get("skipped", []))
    if not fields:
        return
    with card("questions"):
        st.markdown(f"**{L['questions_title']}**")
        st.caption(L["questions_help"])
        with st.form("questions", border=False):
            answers = {field: question_widget(field, f"q_{field}") for field in fields}
            if st.form_submit_button(L["check_again"], type="primary"):
                save_answers(answers)
                st.rerun()


# ---------------------------------------------------------------------------
# STEP 4: prepare the application for one scheme (readiness, PDF, documents)
# ---------------------------------------------------------------------------
def render_readiness(ready):
    """The readiness card: a progress ring with the % in the middle, lists beside it."""
    with card("readiness"):
        col_ring, col_lists = st.columns([1, 2], vertical_alignment="center")
        with col_ring:
            html(f'<div class="ym-ring">{ring_svg(ready["percent"])}'
                 f'<div class="ym-ring-label">{L["readiness"].format(p=ready["percent"])}</div></div>')
        with col_lists:
            st.markdown(f"**✅ {L['completed']} ({len(ready['done'])})**")
            for item in ready["done"]:
                st.markdown(f"- {item}")
            st.markdown(f"**⏳ {L['remaining']} ({len(ready['remaining'])})**")
            for item in ready["remaining"]:
                st.markdown(f"- {item}")
            if not ready["remaining"]:
                st.markdown(L["all_done"])
        st.caption(L["not_approval"])


def render_prepare(person, results):
    """Returns the chosen scheme (or None)."""
    candidates = [r for r in results if r["status"] != NOT_ELIGIBLE]
    if not candidates:
        st.warning(L["none_found"])
        return None
    names = [tr(r["scheme"], "name", lang) for r in candidates]
    chosen = st.selectbox(L["prepare_for"], names)
    result = candidates[names.index(chosen)]
    scheme = result["scheme"]

    # Keys for this scheme's checkboxes / download (by number, so they survive a language switch)
    doc_keys = [f"doc_{scheme['id']}_{i}" for i in range(len(scheme["documents"]))]
    form_key = f"form_done_{scheme['id']}"

    ready = engine.readiness(result, person, [st.session_state.get(k, False) for k in doc_keys],
                             st.session_state.get(form_key, False), lang)
    render_readiness(ready)

    with card("form"):
        st.markdown(f"**📄 {L['step3'].split(':')[-1].strip()}**")
        st.download_button(L["download_pdf"], data=cached_pdf(person, scheme),
                           file_name=f"{scheme['id']}_draft_application.pdf", mime="application/pdf",
                           on_click=lambda: st.session_state.update({form_key: True}),
                           type="primary", use_container_width=True)
        st.caption(L["pdf_note"])

    with card("documents"):
        st.markdown(f"**🗂️ {L['carry']}** — {L['tick_docs']}")
        for doc, key in zip(tr(scheme, "documents", lang), doc_keys):
            st.checkbox(doc, key=key)
        st.markdown(f"**{L['how_to_apply']}:** {tr(scheme, 'how_to_apply', lang)}")
        st.link_button(f"🔗 {L['apply']}", scheme["apply_link"], use_container_width=True)
        st.caption(f"{L['official_source']}: {scheme['source_link']} · "
                   f"{L['last_verified']}: {scheme.get('last_verified') or L['not_verified']}")
    return scheme


# ---------------------------------------------------------------------------
# STEP 5: voice reply
# ---------------------------------------------------------------------------
def build_summary(person, results, scheme):
    """A short summary for the voice reply."""
    parts = []
    if person.get("name"):
        parts.append(L["say_hello"].format(name=person["name"]))
    eligible = [tr(r["scheme"], "name", lang) for r in results if r["status"] == ELIGIBLE]
    more_info = [tr(r["scheme"], "name", lang) for r in results if r["status"] == NEEDS_MORE_INFO]
    parts.append(L["say_eligible"].format(names=", ".join(eligible)) if eligible else L["say_none"])
    if more_info:
        parts.append(L["say_more_info"].format(names=", ".join(more_info)))
    if scheme:
        parts.append(L["say_docs"].format(scheme=tr(scheme, "name", lang),
                                          docs=", ".join(tr(scheme, "documents", lang))))
    return " ".join(parts)


def render_listen(person, results, scheme):
    with card("listen"):
        summary = build_summary(person, results, scheme)
        st.markdown(f"🔊 {summary}")
        try:
            st.audio(speak(summary, lang), format="audio/mp3")
        except Exception as error:
            print(f"[Yojana Mitra] gTTS failed: {error!r}")
            st.error(L["voice_failed"])


# ---------------------------------------------------------------------------
# AJJI MODE: big text, big buttons, simple Kannada, voice first, one thing at a time
# ---------------------------------------------------------------------------
A = T["ajji"]
AJJI_QUESTIONS = 3  # ask at most this many questions before showing results

AJJI_CSS = """
<style>
  /* Big, high-contrast text with lots of space */
  .stApp p, .stApp li, .stApp label, .stApp .stMarkdown { font-size: 1.5rem !important; line-height: 1.6;
                                                          color: #111827 !important; }
  .stApp h1 { font-size: 2.6rem !important; color: #064E3B !important; }
  .stApp h2 { font-size: 2.1rem !important; color: #111827 !important; line-height: 1.35 !important; }
  .stApp h3 { font-size: 1.8rem !important; color: #111827 !important; }
  [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] { gap: 1.2rem; }

  /* Every button: full width, at least 64px tall, 24px+ text, strong border */
  .stButton, .stDownloadButton, .stLinkButton { width: 100% !important; }
  .stButton > button, .stDownloadButton > button, .stLinkButton > a {
      width: 100% !important; min-height: 72px; border-radius: 18px !important;
      background: #FFFFFF; color: #052E1C !important; border: 3px solid #065F46 !important; }
  .stButton > button p, .stDownloadButton > button p, .stLinkButton > a p {
      font-size: 1.65rem !important; font-weight: 700 !important; color: inherit !important; }
  .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
      background: #065F46 !important; color: #FFFFFF !important; }
  .stButton > button:hover { background: #ECFDF5; }
  .stButton > button[kind="primary"]:hover { background: #047857 !important; }

  /* The mic: a big round button in the middle of a dashed box */
  [data-testid="stAudioInput"] label p { text-align: center; width: 100%; font-weight: 700; }
  [data-testid="stAudioInput"] > div:last-child {
      min-height: 210px; height: auto !important; border: 3px dashed #059669 !important; border-radius: 22px !important;
      background: #F0FDF4 !important; flex-direction: column !important; justify-content: center !important;
      align-items: center !important; gap: 12px; padding: 18px !important; }
  [data-testid="stAudioInput"] > div:last-child > div:has(> [data-testid="stAudioInputActionButton"]) {
      flex: 0 0 auto !important; width: auto !important; height: auto !important; }
  [data-testid="stAudioInputActionButton"] {
      width: 104px !important; height: 104px !important; min-width: 104px !important; min-height: 104px !important;
      border-radius: 50% !important; background: #065F46 !important; color: #FFFFFF !important;
      box-shadow: 0 8px 22px rgba(6, 95, 70, .35); }
  [data-testid="stAudioInputActionButton"] svg { width: 52px !important; height: 52px !important; }
  [data-testid="stAudioInput"] > div:last-child > div:nth-child(3) { align-self: stretch; }  /* wave: full width */
  [data-testid="stAudioInputWaveformTimeCode"] { font-size: 1.3rem !important; }

  /* Big number box */
  [data-testid="stNumberInput"] input { font-size: 1.6rem !important; min-height: 64px; }
</style>
"""


def ajji_say(text):
    """Read the text out loud (plays automatically when the screen appears)."""
    try:
        st.audio(speak(text, "kn"), format="audio/mp3", autoplay=True)
    except Exception as error:
        print(f"[Yojana Mitra] gTTS failed: {error!r}")


def ajji_reset():
    for key in ["person", "used_offline", "skipped", "ajji_asked", "ajji_index"]:
        st.session_state.pop(key, None)


def ajji_start():
    """Screen 1: say hello, record a voice note."""
    st.markdown(f"# {A['hello']}")
    st.markdown(f"### {A['hello_say']}")
    ajji_say(A["hello_say"])
    voice = st.audio_input(A["mic"])
    st.caption(L["mic_hint"])
    with st.expander(A["type_instead"]):
        typed = st.text_area(T["kn"]["text_help"], height=120, key="ajji_typed")
    if st.button(A["next"], type="primary", use_container_width=True):
        if not (voice or typed.strip()):
            st.warning(L["need_input"])
        elif understand(typed.strip(), voice, None):
            st.session_state["ajji_asked"] = 0
            st.rerun()


def ajji_question(field):
    """Screen 2: one question, big answer buttons."""
    info = FIELDS[field]
    number = st.session_state.get("ajji_asked", 0) + 1
    st.caption(A["question_n"].format(n=number, total=AJJI_QUESTIONS))
    st.markdown(f"## {info['q_kn']}")
    ajji_say(info["q_kn"])

    def answer(value):
        save_answers({field: value})
        st.session_state.pop("rechecked", None)
        st.session_state["ajji_asked"] = number

    if info["type"] == "number":
        value = st.number_input(info["kn"], min_value=0, value=None, step=1, key=f"ajji_num_{field}")
        if st.button(A["ok"], type="primary", use_container_width=True) and value is not None:
            answer(value)
            st.rerun()
    else:
        for option, (_, kannada) in info["options"].items():
            if st.button(kannada, key=f"ajji_{field}_{option}", use_container_width=True):
                answer(option)
                st.rerun()
    if st.button(A["dont_know"], use_container_width=True):
        answer(None)
        st.rerun()


def ajji_results(person, results):
    """Screen 3: one scheme at a time."""
    candidates = [r for r in results if r["status"] != NOT_ELIGIBLE]
    if not candidates:
        st.markdown(f"## {A['none']}")
        ajji_say(A["none"])
    else:
        index = min(st.session_state.get("ajji_index", 0), len(candidates) - 1)
        result = candidates[index]
        scheme = result["scheme"]
        status = A["yes_status"] if result["status"] == ELIGIBLE else A["maybe_status"]
        docs = scheme["documents_kn"]

        st.caption(A["scheme_n"].format(i=index + 1, n=len(candidates)))
        with card(f"{STATUS_STYLE[result['status']][0]}_ajji"):
            st.markdown(f"### {status}")
            st.markdown(f"# {scheme['name_kn']}")
            st.markdown(scheme["benefits_kn"])
            st.markdown(f"**{A['docs']}:**")
            for doc in docs:
                st.markdown(f"- {doc}")
            st.markdown(f"**{A['where']}:** {scheme['how_to_apply_kn']}")
            ready = engine.readiness(result, person, [False] * len(docs), False, "kn")
            st.caption(f"{A['ready'].format(p=ready['percent'])} · {A['not_approval']}")
        ajji_say(f"{scheme['name_kn']}. {status.strip('✅❓ ')}. {scheme['benefits_kn']} "
                 f"{A['docs']}: {', '.join(docs)}.")

        # One big button per row (easier to tap than two half-width buttons)
        if index < len(candidates) - 1 and st.button(A["next_scheme"], type="primary", use_container_width=True):
            st.session_state["ajji_index"] = index + 1
            st.rerun()
        st.download_button(A["download"], data=cached_pdf(person, scheme), use_container_width=True,
                           file_name=f"{scheme['id']}_draft_application.pdf", mime="application/pdf")
        if index > 0 and st.button(A["back"], use_container_width=True):
            st.session_state["ajji_index"] = index - 1
            st.rerun()

    more_questions = engine.pick_questions(results, st.session_state.get("skipped", []), 1)
    if more_questions and st.button(A["more_q"], use_container_width=True):
        st.session_state["ajji_asked"] = 0
        st.rerun()
    if st.button(A["restart"], use_container_width=True):
        ajji_reset()
        st.rerun()


def render_ajji():
    st.markdown(AJJI_CSS, unsafe_allow_html=True)
    person = st.session_state.get("person")
    if person is None:
        ajji_start()
        return
    results = engine.check_all(person, load_schemes())
    if st.session_state.get("ajji_asked", 0) < AJJI_QUESTIONS:
        fields = engine.pick_questions(results, st.session_state.get("skipped", []), max_questions=1)
        if fields:
            ajji_question(fields[0])
            return
    ajji_results(person, results)


# ---------------------------------------------------------------------------
# The page itself
# ---------------------------------------------------------------------------
html(CSS)

# Language toggle (Kannada is the default)
choice = st.sidebar.radio(T["en"]["language"], ["ಕನ್ನಡ", "English"])
lang = "kn" if choice == "ಕನ್ನಡ" else "en"
L = T[lang]

# Ajji mode switch, at the top of the page so it's easy to find (also on phones)
if st.toggle(A["toggle"], key="ajji_mode"):
    lang, L = "kn", T["kn"]  # Ajji mode is always Kannada
    render_ajji()
    render_footer()
    st.stop()  # don't draw the normal page

render_hero()

person = st.session_state.get("person")
results = engine.check_all(person, load_schemes()) if person else []
questions_left = bool(person) and bool(engine.pick_questions(results, st.session_state.get("skipped", [])))
render_tracker(1 if not person else 3 if questions_left else 4)


def run_demo(text):
    """Demo button: put the demo text in the box and run it."""
    st.session_state["typed_input"] = text
    st.session_state["run_now"] = True


# ---- 1. Tell us ----
section(1, L["sec_input"])

# Demo people: a grid of small cards (3 per row on a computer; Streamlit stacks them on a phone)
st.caption(L["demo"])
for row_start in range(0, len(PERSONAS), 3):
    cols = st.columns(3)
    for col, persona in zip(cols, PERSONAS[row_start:row_start + 3]):
        with col, card(f"persona_{persona['id']}"):
            html(f'<div class="ym-p-emoji">{persona["emoji"]}</div>'
                 f'<div class="ym-p-name">{persona["name_" + lang]}</div>'
                 f'<div class="ym-p-desc">{persona["desc_" + lang]}</div>')
            st.button(L["try"], key=f"demo_{persona['id']}", use_container_width=True,
                      on_click=run_demo, args=(persona["text"],))

with card("input"):
    # Three ways to give input - the user can use any one (or more)
    tab_voice, tab_text, tab_photo = st.tabs([L["tab_voice"], L["tab_text"], L["tab_photo"]])
    with tab_voice:
        # st.audio_input records a WAV file (16 kHz), which we send to Gemini as "audio/wav"
        voice = st.audio_input(L["voice_help"])
        st.caption(L["mic_hint"])
    with tab_text:
        typed = st.text_area(L["text_help"], height=100, key="typed_input")
    with tab_photo:
        photo = st.file_uploader(L["photo_help"], type=["jpg", "jpeg", "png", "webp"])
        if photo:
            st.image(photo, width=250)

    clicked = st.button(L["run"], type="primary", use_container_width=True)

if clicked or st.session_state.pop("run_now", False):
    if not (voice or typed.strip() or photo):
        st.warning(L["need_input"])
    elif not get_api_key() and not typed.strip():
        st.error(L["no_key"])  # without a key, only typed text can work (offline reader)
    elif understand(typed.strip(), voice, photo):
        st.rerun()  # draw the results (and the tracker) with the new details

# ---- 2-5. Results ----
if person:
    section("✓", L["sec_details"])
    render_details(person)

    section(2, L["sec_eligibility"])
    render_results(person, results)  # (step 3, the follow-up questions, is shown inside)

    section(4, L["sec_prepare"])
    chosen_scheme = render_prepare(person, results)

    section(5, L["sec_listen"])
    render_listen(person, results, chosen_scheme)

    st.write("")
    if st.button(L["start_over"]):
        for key in ["person", "used_offline", "skipped"]:
            st.session_state.pop(key, None)
        st.rerun()

render_footer()
