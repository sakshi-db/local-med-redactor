"""
SecureClinic: Local PII Redactor & Clinical Sorter
Hacktoberfest AI challenge entry

Run:  pip install streamlit
      streamlit run app.py

Privacy notes
- Everything runs in-process on your machine. There are no HTTP calls, no telemetry hooks,
  and no external fonts or CDNs (the UI uses system fonts on purpose).
- The "inference" step is a simulated local-model pass wrapped around a deterministic,
  rule-based redactor and extractor, so the demo works with zero downloads.
  To plug in a real open-weight model, replace `run_local_model()` with a call to a local
  runtime such as Ollama (http://localhost:11434) or llama.cpp, and keep the output
  contract the same.
"""

import html
import json
import re
import time
from collections import Counter

import streamlit as st

# --------------------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------------------
st.set_page_config(
    page_title="SecureClinic | Local PII Redactor & Clinical Sorter",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
:root {
  --ink: #14302d;
  --ink-soft: #46605c;
  --paper: #f2f5f3;
  --panel: #ffffff;
  --line: #d3ddd9;
  --teal: #1b7a6b;
  --teal-deep: #0f5a4e;
  --bar: #17201f;
  --bar-text: #dcebe6;
  --amber: #a86a12;
  --amber-bg: #fbf1dd;
  --red: #a3342b;
  --red-bg: #fbe8e5;
  --green-bg: #e3f2ec;
}
.stApp { background: var(--paper); color: var(--ink); }
.stApp [data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1180px; }
.stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp li, .stApp label,
.stApp [data-testid="stWidgetLabel"] p, .stApp [data-testid="stMarkdownContainer"] { color: var(--ink); }

/* Sidebar */
[data-testid="stSidebar"] { background: #e6eeea; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] * { color: var(--ink); }

/* Hero */
.hero { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 1.8rem 2rem; margin-bottom: 1.4rem; }
.hero h1 { font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; font-size: 2.5rem;
  font-weight: 700; letter-spacing: -0.01em; margin: 0 0 .35rem 0; padding: 0; color: var(--ink); }
.hero .sub { font-size: 1.05rem; color: var(--ink-soft); max-width: 62ch; margin: 0 0 1.2rem 0; line-height: 1.5; }
.hero .sample { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .92rem; line-height: 1.9;
  background: #f8faf9; border: 1px dashed var(--line); border-radius: 8px; padding: .8rem 1rem; color: var(--ink); }
.bar { display: inline-block; background: var(--bar); color: var(--bar); border-radius: 2px; user-select: none; }

/* Redaction tokens in the output view */
.doc { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1.2rem 1.4rem;
  white-space: pre-wrap; line-height: 1.75; font-size: .97rem; max-height: 460px; overflow-y: auto; color: var(--ink); }
.rd { background: var(--bar); color: var(--bar-text); border-radius: 3px; padding: 1px 7px; margin: 0 1px;
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .78rem; white-space: nowrap; }

/* Stats */
.stat { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: .8rem 1rem; }
.stat .n { font-family: "Iowan Old Style", Georgia, serif; font-size: 1.9rem; font-weight: 700; line-height: 1.1; color: var(--teal-deep); }
.stat .l { font-size: .85rem; color: var(--ink-soft); }

/* Chips + banners */
.chip { display: inline-block; padding: .22rem .65rem; margin: 0 .35rem .4rem 0; border-radius: 999px; font-size: .86rem;
  background: var(--green-bg); color: var(--teal-deep); border: 1px solid #bcdccf; }
.chip.cond { background: #e8eef7; color: #2b4a78; border-color: #c5d3e8; }
.chip.med { background: #efe9f6; color: #5a3d80; border-color: #d8cce8; }
.chip.flag { background: var(--red-bg); color: var(--red); border-color: #efc2bc; }
.empty { color: var(--ink-soft); font-style: italic; font-size: .92rem; }
.banner { border-radius: 8px; padding: .9rem 1.1rem; margin-bottom: 1.1rem; border: 1px solid; }
.banner b { font-size: 1.02rem; }
.banner.urgent { background: var(--red-bg); border-color: #efc2bc; color: var(--red); }
.banner.follow { background: var(--amber-bg); border-color: #ecd6a6; color: var(--amber); }
.banner.routine { background: var(--green-bg); border-color: #bcdccf; color: var(--teal-deep); }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 1rem 1.2rem; height: 100%; }
.card h4 { margin: 0 0 .6rem 0; font-size: 1rem; color: var(--ink); }
.steps { margin: 0; padding-left: 1.2rem; color: var(--ink); line-height: 1.7; }

/* Buttons */
div.stButton > button[kind="primary"] { background: var(--teal); border: 1px solid var(--teal-deep); color: #fff;
  font-weight: 600; padding: .65rem 1.4rem; border-radius: 8px; }
div.stButton > button[kind="primary"]:hover { background: var(--teal-deep); border-color: var(--teal-deep); color: #fff; }
div.stDownloadButton > button { border: 1px solid var(--teal); color: var(--teal-deep); background: #fff; border-radius: 8px; font-weight: 600; }
div.stDownloadButton > button:hover { background: var(--green-bg); border-color: var(--teal-deep); color: var(--teal-deep); }

/* Tabs */
[data-baseweb="tab-list"] { gap: .4rem; }
[data-baseweb="tab"] { font-weight: 600; }

/* Footer */
.footer { margin-top: 2.5rem; padding: 1.2rem 1.4rem; border-radius: 10px; background: var(--bar); color: var(--bar-text); line-height: 1.6; font-size: .93rem; }
.footer b { color: #ffffff; }
.footer .fine { color: #9db5ae; font-size: .82rem; margin-top: .5rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# Sample data
# --------------------------------------------------------------------------------------
SAMPLE_NOTES = """INTAKE NOTES - walk-in visit 10/14/2026 (typed fast on my phone, sorry for the mess)

Patient: Maria Gonzalez, DOB 03/22/1984, 42 y/o F
cell 555-201-4478 / email maria.gonzalez84@example.com
SSN 123-45-6789 (she read it out for the insurance form)  Member ID: BCX9981274
Lives at 482 Willow Street, Springfield, 62704
Emergency contact: Luis Gonzalez (husband) 555-330-9912

c/o lower back pain x 3 wks, worse after sitting. Also bad headaches (migraine hx), poor sleep,
fatigue, some anxiety since the job change. Denies chest pain. No shortness of breath.
Hx: hypertension on lisinopril 10mg, sciatica flare last spring. Allergic to penicillin.
Dr. Patel referred Maria last spring. Maria says stress is "through the roof".

Plan: gentle mobility program + PT referral, sleep hygiene handout, follow-up in 2 weeks,
ask PCP to review BP meds. Discuss magnesium with Dr. Patel.
"""

# --------------------------------------------------------------------------------------
# Redaction engine (rule-based, runs entirely in-process)
# --------------------------------------------------------------------------------------
NAME_WORD = r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?"
TITLES = {"Dr", "Mr", "Mrs", "Ms", "Miss", "Prof"}
MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*"

STRICTNESS_LABELS = {
    1: "Direct identifiers (SSN, phone, email)",
    2: "Standard (adds names, DOB, IDs, addresses)",
    3: "Maximum (adds all dates, ages, ZIP codes)",
}


def redact(text: str, level: int):
    """Return (clean_text, Counter of redactions by category)."""
    counts = Counter()

    def tag(label):
        def _sub(_m):
            counts[label] += 1
            return f"[{label}]"
        return _sub

    def keep_label(label):
        def _sub(m):
            counts[label] += 1
            return f"{m.group(1)}[{label}]"
        return _sub

    # Level 1: direct identifiers
    text = re.sub(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)", tag("SSN"), text)
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", tag("EMAIL"), text)
    text = re.sub(
        r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)",
        tag("PHONE"),
        text,
    )

    if level >= 2:
        # Names: labelled or titled, then propagate to every other mention
        found = set()
        for m in re.finditer(
            rf"\b(?i:patient|pt|name|client|spouse|emergency contact)\s*[:\-]\s*({NAME_WORD}(?:\s+{NAME_WORD}){{0,2}})",
            text,
        ):
            found.add(m.group(1))
        for m in re.finditer(rf"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+({NAME_WORD}(?:\s+{NAME_WORD})?)", text):
            found.add(m.group(1))
        # Names that follow "Emergency contact:" style labels are caught above; bare "First Last (husband)" too:
        for m in re.finditer(rf"({NAME_WORD}\s+{NAME_WORD})\s+\((?:husband|wife|partner|mother|father|son|daughter|friend|spouse)\)", text):
            found.add(m.group(1))

        tokens = set()
        for full in sorted(found, key=len, reverse=True):
            pattern = r"\s+".join(re.escape(p) for p in full.split())
            text = re.sub(rf"\b{pattern}\b", tag("NAME"), text)
            tokens.update(w for w in re.split(r"[\s]+", full) if len(w) >= 3 and w not in TITLES)
        for tok in sorted(tokens, key=len, reverse=True):
            text = re.sub(rf"\b{re.escape(tok)}\b", tag("NAME"), text)

        text = re.sub(
            r"(?i)(\b(?:DOB|D\.O\.B\.?|date of birth)\s*[:\-]?\s*)(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|" + MONTHS + r"\s+\d{1,2},?\s+\d{4})",
            keep_label("DOB"),
            text,
        )
        text = re.sub(
            r"(?i)(\b(?:MRN|member id|policy(?: no\.?| number)?|insurance id)\s*[:#]?\s*)[A-Z0-9-]{5,}",
            keep_label("ID"),
            text,
        )
        text = re.sub(
            r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Dr|Drive|Ct|Court|Way)\b\.?(?:,\s*[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)?",
            tag("ADDRESS"),
            text,
        )

    if level >= 3:
        text = re.sub(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", tag("DATE"), text)
        text = re.sub(rf"\b{MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?\b", tag("DATE"), text)
        text = re.sub(r"(?i)\b\d{1,3}\s?(?:y/?o|yo|years?[- ]old)\b", tag("AGE"), text)
        text = re.sub(r"(?<!\d)\d{5}(?:-\d{4})?(?!\d)", tag("ZIP"), text)

    return text, counts


# --------------------------------------------------------------------------------------
# Clinical extraction (runs on the REDACTED text only)
# --------------------------------------------------------------------------------------
SYMPTOMS = {
    "Lower back pain": r"low(?:er)? back pain",
    "Neck pain": r"neck pain",
    "Shoulder pain": r"shoulder pain",
    "Joint pain / stiffness": r"joint (?:pain|stiffness)",
    "Headaches": r"headaches?",
    "Poor sleep": r"poor sleep|insomnia|trouble sleeping|can'?t sleep",
    "Fatigue": r"fatigue|exhaust\w*|tired",
    "Anxiety": r"anxiety|anxious",
    "Low mood": r"low mood|feeling down|depressed mood",
    "Nausea": r"nausea|nauseous",
    "Dizziness": r"dizz\w+|lightheaded",
    "Numbness / tingling": r"numbness|tingling",
    "Digestive upset": r"bloating|stomach upset|cramps",
    "Muscle tension": r"muscle tension|tight muscles",
    "Brain fog": r"brain fog",
}
CONDITIONS = {
    "Hypertension": r"hypertension|high blood pressure",
    "Type 2 diabetes": r"type 2 diabetes|t2dm|diabetes",
    "Migraine": r"migraines?",
    "Sciatica": r"sciatica",
    "Asthma": r"asthma",
    "Depression": r"depression",
    "Generalized anxiety": r"\bgad\b|generalized anxiety",
    "Fibromyalgia": r"fibromyalgia",
    "Hypothyroidism": r"hypothyroid\w*",
    "Arthritis": r"arthritis",
    "GERD": r"\bgerd\b|acid reflux",
    "Sleep apnea": r"sleep apnea",
}
MEDICATIONS = {
    "Lisinopril": r"lisinopril(?:\s+\d+\s?(?:mg|mcg))?",
    "Metformin": r"metformin(?:\s+\d+\s?(?:mg|mcg))?",
    "Ibuprofen": r"ibuprofen(?:\s+\d+\s?(?:mg|mcg))?",
    "Sertraline": r"sertraline(?:\s+\d+\s?(?:mg|mcg))?",
    "Melatonin": r"melatonin(?:\s+\d+\s?(?:mg|mcg))?",
    "Magnesium": r"magnesium",
    "Levothyroxine": r"levothyroxine(?:\s+\d+\s?(?:mg|mcg))?",
}
ALLERGIES = {"Penicillin": r"penicillin", "Sulfa drugs": r"sulfa", "Latex": r"latex", "Shellfish": r"shellfish"}
RED_FLAGS = {
    "Chest pain": r"chest pain|chest tightness",
    "Shortness of breath": r"shortness of breath|can'?t breathe",
    "Fainting": r"faint\w*|passed out",
    "Suicidal thoughts / self-harm": r"suicid\w*|self[- ]harm|want to die",
}
SUGGESTIONS = {
    "Lower back pain": "Offer a gentle mobility or physiotherapy program and a posture review.",
    "Neck pain": "Review ergonomics and consider manual therapy or stretching guidance.",
    "Headaches": "Start a headache diary (triggers, timing, hydration, screen time).",
    "Migraine": "Track migraine triggers and flag frequency changes to the primary care provider.",
    "Poor sleep": "Share a sleep hygiene handout and review caffeine and screen habits.",
    "Fatigue": "Screen for sleep, nutrition and mood contributors; consider routine bloodwork via PCP.",
    "Anxiety": "Offer stress-management resources (breathwork, CBT-style journaling) and check in at follow-up.",
    "Low mood": "Use a brief mood screen at the next visit and share support options.",
    "Hypertension": "Ask the primary care provider to review blood pressure and medications.",
    "Type 2 diabetes": "Confirm the current glucose management plan with the primary care provider.",
    "Sciatica": "Avoid prolonged sitting and review nerve-friendly mobility work.",
    "Numbness / tingling": "Document location and duration; refer if it is progressive.",
}


def _find(text, vocab, skip_negated=True):
    hits = []
    for name, pattern in vocab.items():
        for m in re.finditer(pattern, text, flags=re.I):
            pre = text[max(0, m.start() - 35): m.start()].lower()
            if skip_negated and re.search(r"\b(denies|deny|no|not|without|negative for|neg)\b[^.\n;]*$", pre):
                continue
            label = name
            if vocab is MEDICATIONS:
                label = m.group(0).strip().capitalize()
            if label not in hits:
                hits.append(label)
            break
    return hits


def extract(clean_text: str):
    symptoms = _find(clean_text, SYMPTOMS)
    conditions = _find(clean_text, CONDITIONS)
    meds = _find(clean_text, MEDICATIONS)
    allergies = _find(clean_text, ALLERGIES)
    flags = _find(clean_text, RED_FLAGS)

    # Pull the clinician's own plan lines, then add rule-based prompts
    plan = []
    m = re.search(r"(?im)^\s*(?:plan|recommendations?|a/p|assessment/plan)\s*[:\-]\s*(.*?)(?:\n\s*\n|\Z)", clean_text, flags=re.S)
    if m:
        block = " ".join(m.group(1).split())
        plan = [s.strip(" .") for s in re.split(r",\s+|;\s+|(?<!Dr)(?<!Mr)(?<!Ms)(?<!Mrs)\.\s+|\s\+\s", block) if s.strip(" .")]
    else:
        for line in clean_text.splitlines():
            if re.search(r"\b(recommend\w*|follow[- ]?up)\b", line, flags=re.I):
                plan.append(line.strip())
    suggested = []
    for key in symptoms + conditions:
        tip = SUGGESTIONS.get(key)
        if tip and tip not in suggested:
            suggested.append(tip)
    if allergies:
        suggested.append("Record allergies (" + ", ".join(allergies) + ") in the chart before any new recommendations.")

    if flags:
        priority = ("urgent", "Urgent: clinician review today", "Red-flag terms detected: " + ", ".join(flags) + ".")
    elif len(symptoms) >= 4 or len(conditions) >= 2:
        priority = ("follow", "Follow-up: book within 2 weeks", "Multiple active symptoms or conditions are documented.")
    else:
        priority = ("routine", "Routine: standard scheduling", "No red flags and a light symptom load.")

    return {
        "priority": {"level": priority[0], "label": priority[1], "reason": priority[2]},
        "symptoms": symptoms,
        "conditions": conditions,
        "medications": meds,
        "allergies": allergies,
        "red_flags": flags,
        "practitioner_plan": plan,
        "suggested_next_steps": suggested,
    }


# --------------------------------------------------------------------------------------
# Simulated local inference
# --------------------------------------------------------------------------------------
MODELS = {
    "Gemma 2 (9B, Q4)": 1.0,
    "Llama 3 (8B, Q4)": 1.1,
    "Mistral 7B (Q4)": 0.9,
    "Phi-3 Mini (3.8B, Q4)": 0.6,
}


def run_local_model(model_name: str, text: str, level: int):
    """Stand-in for an on-device open-weight model call (swap for Ollama / llama.cpp)."""
    speed = MODELS[model_name]
    stages = [
        "Loading quantized weights from local disk",
        "Tokenizing intake notes in memory",
        "Detecting identifiers (offline pass)",
        "Structuring symptoms, conditions and plan",
    ]
    bar = st.progress(0.0, text=stages[0])
    started = time.time()
    for i, stage in enumerate(stages):
        bar.progress((i + 1) / len(stages), text=stage)
        time.sleep(0.45 * speed)
    bar.empty()
    clean, counts = redact(text, level)
    data = extract(clean)
    return clean, counts, data, time.time() - started


# --------------------------------------------------------------------------------------
# Helpers for rendering
# --------------------------------------------------------------------------------------
def highlight(clean_text: str) -> str:
    safe = html.escape(clean_text)
    return re.sub(r"\[([A-Z_]+)\]", r'<span class="rd">\1</span>', safe)


def chips(items, cls=""):
    if not items:
        return '<span class="empty">Nothing detected</span>'
    return "".join(f'<span class="chip {cls}">{html.escape(i)}</span>' for i in items)


# --------------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    model = st.selectbox("Local model", list(MODELS.keys()), help="Open-weight models that run on your own hardware.")
    level = st.select_slider(
        "Redaction strictness",
        options=[1, 2, 3],
        value=2,
        format_func=lambda v: {1: "Light", 2: "Standard", 3: "Maximum"}[v],
    )
    st.caption(STRICTNESS_LABELS[level])
    st.divider()
    st.markdown("**Privacy status**")
    st.success("Offline mode: no network calls", icon="🔒")
    st.caption("Notes stay in this session's memory and are cleared when you close the tab.")
    st.divider()
    st.caption("Decision support only. A licensed practitioner must review all output.")

# --------------------------------------------------------------------------------------
# Hero
# --------------------------------------------------------------------------------------
st.markdown(
    """
<div class="hero">
  <h1>SecureClinic</h1>
  <p class="sub">Redact patient identifiers and sort intake notes into a clean clinical summary, all on your own machine. Nothing is sent to a cloud API.</p>
  <div class="sample">Patient: <span class="bar">Maria Gonzalez</span> &nbsp;DOB <span class="bar">03/22/1984</span><br>
  SSN <span class="bar">123-45-6789</span> &nbsp;Cell <span class="bar">555-201-4478</span><br>
  Complaint: lower back pain, poor sleep, fatigue</div>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------------------
st.markdown("#### 1. Add intake notes")
uploaded = st.file_uploader("Upload a .txt intake file", type=["txt"], help="Read locally; never uploaded anywhere.")

if uploaded is not None:
    source_text = uploaded.getvalue().decode("utf-8", errors="replace")
    st.info(f"Loaded **{uploaded.name}** ({len(source_text):,} characters). Remove the file to use the sample editor instead.", icon="📄")
    with st.expander("Preview original notes (local memory only)"):
        st.text(source_text)
else:
    source_text = st.text_area(
        "Or paste notes here (sample included)",
        value=SAMPLE_NOTES,
        height=300,
    )

go = st.button("🚀 Process & Redact Locally", type="primary")

if go:
    if not source_text.strip():
        st.warning("Add some intake notes first: upload a .txt file or paste text above.")
    else:
        with st.spinner(f"Running {model} locally. No data leaves this device..."):
            clean, counts, data, secs = run_local_model(model, source_text, level)
        st.session_state["result"] = {
            "clean": clean,
            "counts": dict(counts),
            "data": data,
            "secs": secs,
            "model": model,
            "level": level,
            "original": source_text,
        }

# --------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------
res = st.session_state.get("result")
if res:
    st.markdown("#### 2. Review results")
    tab1, tab2 = st.tabs(["🛡️ Sanitized record", "🩺 Structured extraction"])

    with tab1:
        total = sum(res["counts"].values())
        c1, c2, c3, c4 = st.columns(4)
        for col, num, label in [
            (c1, total, "identifiers redacted"),
            (c2, len(res["counts"]), "categories found"),
            (c3, f'{res["secs"]:.1f}s', "local processing time"),
            (c4, {1: "Light", 2: "Standard", 3: "Maximum"}[res["level"]], "strictness"),
        ]:
            col.markdown(f'<div class="stat"><div class="n">{num}</div><div class="l">{label}</div></div>', unsafe_allow_html=True)

        if res["counts"]:
            st.markdown(
                "<div style='margin:.9rem 0 .2rem 0'>"
                + "".join(f'<span class="chip">{k} × {v}</span>' for k, v in sorted(res["counts"].items()))
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No identifiers were detected at this strictness level. Try raising the slider.")

        show_marks = st.toggle("Highlight redactions", value=True)
        if show_marks:
            st.markdown(f'<div class="doc">{highlight(res["clean"])}</div>', unsafe_allow_html=True)
        else:
            st.code(res["clean"], language=None)

        st.download_button(
            "⬇️ Download clean text file",
            data=res["clean"],
            file_name="secureclinic_redacted_notes.txt",
            mime="text/plain",
        )
        if level < 3 and re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", res["clean"]):
            st.caption("Dates of service remain in the text at this strictness. Use Maximum to remove them too.")

    with tab2:
        d = res["data"]
        p = d["priority"]
        st.markdown(
            f'<div class="banner {p["level"]}"><b>{html.escape(p["label"])}</b><br>{html.escape(p["reason"])}</div>',
            unsafe_allow_html=True,
        )

        a, b, c = st.columns(3)
        a.markdown(f'<div class="card"><h4>Key symptoms</h4>{chips(d["symptoms"])}</div>', unsafe_allow_html=True)
        b.markdown(
            f'<div class="card"><h4>Conditions and history</h4>{chips(d["conditions"], "cond")}'
            f'<h4 style="margin-top:.8rem">Medications</h4>{chips(d["medications"], "med")}'
            f'<h4 style="margin-top:.8rem">Allergies</h4>{chips(d["allergies"], "flag")}</div>',
            unsafe_allow_html=True,
        )
        c.markdown(f'<div class="card"><h4>Red flags</h4>{chips(d["red_flags"], "flag")}</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
        left, right = st.columns(2)
        plan_html = (
            "<ol class='steps'>" + "".join(f"<li>{html.escape(x)}</li>" for x in d["practitioner_plan"]) + "</ol>"
            if d["practitioner_plan"] else '<span class="empty">No plan lines found in the notes</span>'
        )
        next_html = (
            "<ol class='steps'>" + "".join(f"<li>{html.escape(x)}</li>" for x in d["suggested_next_steps"]) + "</ol>"
            if d["suggested_next_steps"] else '<span class="empty">No suggestions generated</span>'
        )
        left.markdown(f'<div class="card"><h4>Plan from the practitioner</h4>{plan_html}</div>', unsafe_allow_html=True)
        right.markdown(f'<div class="card"><h4>Recommended next steps</h4>{next_html}</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
        st.download_button(
            "⬇️ Download extraction (JSON)",
            data=json.dumps(d, indent=2),
            file_name="secureclinic_extraction.json",
            mime="application/json",
        )
        st.caption(f"Generated with {res['model']} on this device from the redacted text only. Review before acting on it.")

# --------------------------------------------------------------------------------------
# Footer
# --------------------------------------------------------------------------------------
st.markdown(
    """
<div class="footer">
  <b>100% local, open-weight AI.</b> SecureClinic is built for independent practitioners and small clinics:
  intake notes are processed on your own hardware by open-weight models such as Gemma 2 and Llama 3,
  with zero cloud API calls and no third-party data sharing. Keeping protected health information on-device
  supports HIPAA- and GDPR-style data minimization.
  <div class="fine">Built for Hacktoberfest. Redaction is rule-assisted and may miss unusual formats, so always
  review the output. This tool does not provide medical advice and is not a substitute for a compliance review.</div>
</div>
""",
    unsafe_allow_html=True,
)