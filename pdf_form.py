"""
pdf_form.py - make a filled (draft) application form as a PDF, in Kannada + English.
"""

from datetime import date
from pathlib import Path

from fpdf import FPDF

from engine import FIELDS, show_value

FONT_DIR = Path(__file__).parent / "fonts"
KANNADA_FONT = FONT_DIR / "NotoSansKannada-Regular.ttf"
ENGLISH_FONT = FONT_DIR / "NotoSans-Regular.ttf"  # used for English letters

BASIC_FIELDS = ["name", "age", "gender", "marital_status", "district", "annual_income", "ration_card"]


def make_pdf(person, scheme):
    """Returns the PDF file as bytes."""
    pdf = FPDF()
    pdf.add_page()

    # Kannada font, with an English font as backup for English letters
    pdf.add_font("Kannada", fname=str(KANNADA_FONT))
    pdf.add_font("English", fname=str(ENGLISH_FONT))
    pdf.set_font("Kannada", size=12)
    pdf.set_fallback_fonts(["English"])
    try:
        # Text shaping joins Kannada letters correctly (needs the 'uharfbuzz' package)
        pdf.set_text_shaping(True)
    except Exception:
        pass  # without it the PDF still works, Kannada just looks a bit less neat

    # Title
    pdf.set_font_size(18)
    pdf.cell(0, 12, "ಅರ್ಜಿ ನಮೂನೆ (ಕರಡು) / Application Form (Draft)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font_size(14)
    pdf.cell(0, 10, f"{scheme['name_kn']} / {scheme['name']}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Which rows to show: basic details + whatever this scheme's rules look at
    rows = list(BASIC_FIELDS)
    for rule in scheme["rules"]:
        if rule["field"] not in rows:
            rows.append(rule["field"])

    # Applicant details table: label on the left, value on the right
    pdf.set_font_size(10)
    with pdf.table(col_widths=(60, 40), first_row_as_headings=False, line_height=5,
                   text_align="LEFT", padding=1) as table:
        for key in rows:
            info = FIELDS[key]
            value = show_value(key, person.get(key), "en")
            if value == "-":
                value = "________________"  # blank line so the person can write it by hand
            row = table.row()
            row.cell(f"{info['kn']}\n{info['en']}")
            row.cell(value)
    pdf.ln(4)

    # Benefits
    pdf.set_font_size(11)
    pdf.multi_cell(0, 7, f"ಸೌಲಭ್ಯ / Benefit: {scheme['benefits_kn']}\n{scheme['benefits']}",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Documents checklist with empty boxes to tick
    pdf.cell(0, 8, "ಲಗತ್ತಿಸಬೇಕಾದ ದಾಖಲೆಗಳು / Documents attached:", new_x="LMARGIN", new_y="NEXT")
    for doc_kn, doc_en in zip(scheme["documents_kn"], scheme["documents"]):
        pdf.cell(0, 7, f"[   ]  {doc_kn} / {doc_en}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Declaration + signature
    pdf.multi_cell(0, 7, "ಮೇಲಿನ ಮಾಹಿತಿ ಸತ್ಯವೆಂದು ನಾನು ಘೋಷಿಸುತ್ತೇನೆ. / "
                         "I declare that the above information is true.",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(95, 8, f"ದಿನಾಂಕ / Date: {date.today():%d-%m-%Y}")
    pdf.cell(0, 8, "ಸಹಿ / Signature: ______________", new_x="LMARGIN", new_y="NEXT")

    # Footer note
    pdf.ln(8)
    pdf.set_font_size(8)
    pdf.multi_cell(0, 5, "Draft prepared by Yojana Mitra to help you. This is NOT an official form and NOT an "
                         "approval. Apply on the official portal: " + scheme["apply_link"])

    return bytes(pdf.output())
