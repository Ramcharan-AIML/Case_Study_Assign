"""Generates the two binary sample sources (an English text PDF and a scanned,
image-only Marathi PDF). The HTML, TXT and MyScheme JSON samples are plain
files checked into data/ and are written by hand.

Everything here is synthetic: the state "Vindhyachal" does not exist and all
links use the reserved .example domain or a synthetic:// placeholder.
"""
from __future__ import annotations

import random
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageFilter

DATA = Path(__file__).resolve().parent.parent / "data" / "sources"

SCH001_PAGES = [
    [
        "GOVERNMENT OF VINDHYACHAL (SYNTHETIC)",
        "Department of Social Justice and Empowerment",
        "Notification No. SJE/PEN/2026/114                         Dated: 12.03.2026",
        "",
        "Subject: Vriddha Samman Pension Yojana - revision of assistance",
        "",
        "1. Scheme Name: Vriddha Samman Pension Yojana",
        "2. Benefit:",
        "Monthly pension of Rs. 1,500 (Rupees One Thousand Five Hundred only) per month,",
        "credited by DBT to the beneficiary's Aadhaar-seeded bank account.",
        "This revises the earlier assistance of Rs. 1,000 per month with effect from 01.04.2026.",
        "3. Eligibility:",
        "a. Resident of Vindhyachal for at least 10 years.",
        "b. Age 60 years or above.",
        "c. Annual family income not exceeding Rs. 1,20,000.",
        "d. Not receiving any other government pension.",
    ],
    [
        "4. Documents Required:",
        "a. Aadhaar card",
        "b. Age proof (birth certificate / school leaving certificate / voter ID)",
        "c. Income certificate issued by Tehsildar",
        "d. Domicile certificate",
        "e. Bank passbook (first page)",
        "5. How to Apply:",
        "a. Apply online at the Social Justice portal or at the nearest Common Service Centre (CSC).",
        "b. The application is verified by the Block Social Welfare Officer within 30 days.",
        "6. Last Date: Applications for the year 2026-27 must be submitted by 30 June 2026.",
        "7. Official Link: https://sje.vindhyachal.example/vsp",
        "",
        "By order, Secretary, Department of Social Justice and Empowerment (synthetic)",
    ],
]

SCH003_HTML = """
<div style="font-family: sans-serif; font-size: 13px; line-height: 1.55">
<p style="text-align:center"><b>विंध्याचल शासन (काल्पनिक)</b><br/>महिला व बाल विकास विभाग</p>
<p>परिपत्रक क्र. मबावि/२०२६/४७ &nbsp;&nbsp;&nbsp;&nbsp; दिनांक: २०.०७.२०२६</p>
<p><b>योजनेचे नाव:</b> निराधार विधवा अर्थसहाय्य योजना</p>
<p><b>लाभ:</b> पात्र लाभार्थीस दरमहा ₹ १,२०० अर्थसहाय्य थेट बँक खात्यात जमा केले जाईल.</p>
<p><b>पात्रता:</b><br/>१. अर्जदार विधवा असावी व वय १८ वर्षांपेक्षा जास्त असावे.<br/>
२. कुटुंबाचे वार्षिक उत्पन्न ₹ ५०,००० पेक्षा कमी असावे.</p>
<p><b>आवश्यक कागदपत्रे:</b> आधार कार्ड, पतीचा मृत्यू दाखला, उत्पन्नाचा दाखला, बँक पासबुक</p>
<p><b>अर्ज कसा करावा:</b> तहसील कार्यालयात विहित नमुन्यातील अर्ज सादर करावा.</p>
<p><b>अंतिम दिनांक:</b> ३१ डिसेंबर २०२६</p>
<p style="text-align:right">आदेशानुसार,<br/>उपसचिव (काल्पनिक)</p>
</div>
"""


def make_sch001_pdf(path: Path) -> None:
    doc = fitz.open()
    for lines in SCH001_PAGES:
        page = doc.new_page(width=595, height=842)  # A4
        y = 72
        for line in lines:
            page.insert_text((60, y), line, fontsize=10, fontname="helv")
            y += 18
    doc.save(path)


def make_sch003_scan(pdf_path: Path, png_path: Path) -> None:
    """Render shaped Devanagari via MuPDF, rasterise, then degrade like a phone scan."""
    tmp = fitz.open()
    page = tmp.new_page(width=595, height=842)
    page.insert_htmlbox(fitz.Rect(50, 50, 545, 800), SCH003_HTML)
    pix = page.get_pixmap(dpi=120)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")

    rng = random.Random(7)  # deterministic noise so the sample is reproducible
    img = img.rotate(1.3, expand=False, fillcolor=235)
    px = img.load()
    for _ in range(img.width * img.height // 60):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        px[x, y] = rng.choice((150, 200, 245))
    img = img.filter(ImageFilter.GaussianBlur(0.6))

    img.save(png_path)
    img.convert("RGB").save(pdf_path, "PDF", resolution=120)  # image-only PDF: no text layer


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    make_sch001_pdf(DATA / "SCH001_pension_notification_en.pdf")
    make_sch003_scan(DATA / "SCH003_widow_assistance_scan_mr.pdf", DATA / "SCH003_widow_assistance_scan_mr.png")
    print(f"Wrote sample PDFs to {DATA}")


if __name__ == "__main__":
    main()
