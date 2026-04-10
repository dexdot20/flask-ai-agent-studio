from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_PATHS = {
    "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSansMono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}

_EXPORT_HEADING_COLOR = colors.HexColor("#14213d")
_EXPORT_TEXT_COLOR = colors.HexColor("#1f2940")
_EXPORT_MUTED_COLOR = colors.HexColor("#5d6882")
_EXPORT_CODE_BG = colors.HexColor("#f3f6fb")
_EXPORT_QUOTE_BG = colors.HexColor("#f7f9fd")
_EXPORT_MATH_BG = colors.HexColor("#f4f7fd")


def _try_register_fonts() -> bool:
    if not all(os.path.exists(path) for path in _FONT_PATHS.values()):
        return False
    try:
        registered = set(pdfmetrics.getRegisteredFontNames())
        for name, path in _FONT_PATHS.items():
            if name in registered:
                continue
            pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False


_UNICODE_FONTS = _try_register_fonts()
BODY_FONT = "DejaVuSans" if _UNICODE_FONTS else "Helvetica"
BOLD_FONT = "DejaVuSans-Bold" if _UNICODE_FONTS else "Helvetica-Bold"
MONO_FONT = "DejaVuSansMono" if _UNICODE_FONTS else "Courier"


def build_print_pdf_styles(
    namespace: str,
    *,
    title_font_size: float = 20,
    title_leading: float = 25,
    body_font_size: float = 10.4,
    body_leading: float = 15.4,
    heading1_font_size: float = 16.4,
    heading1_leading: float = 21.0,
    heading_font_size: float = 13.4,
    heading_leading: float = 17.4,
    subheading_font_size: float = 11.8,
    subheading_leading: float = 15.4,
    code_font_size: float = 8.8,
    code_leading: float = 12.2,
) -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        f"{namespace}Title",
        parent=styles["Title"],
        fontName=BOLD_FONT,
        fontSize=title_font_size,
        leading=title_leading,
        textColor=_EXPORT_HEADING_COLOR,
        spaceAfter=10,
        spaceBefore=0,
    )
    body_style = ParagraphStyle(
        f"{namespace}Body",
        parent=styles["BodyText"],
        fontName=BODY_FONT,
        fontSize=body_font_size,
        leading=body_leading,
        textColor=_EXPORT_TEXT_COLOR,
        spaceAfter=6,
        firstLineIndent=0,
    )
    heading1_style = ParagraphStyle(
        f"{namespace}H1",
        parent=styles["Heading1"],
        fontName=BOLD_FONT,
        fontSize=heading1_font_size,
        leading=heading1_leading,
        textColor=_EXPORT_HEADING_COLOR,
        spaceAfter=7,
        spaceBefore=15,
    )
    heading_style = ParagraphStyle(
        f"{namespace}H2",
        parent=styles["Heading2"],
        fontName=BOLD_FONT,
        fontSize=heading_font_size,
        leading=heading_leading,
        textColor=_EXPORT_HEADING_COLOR,
        spaceAfter=5,
        spaceBefore=11,
    )
    subheading_style = ParagraphStyle(
        f"{namespace}H3",
        parent=styles["Heading3"],
        fontName=BOLD_FONT,
        fontSize=subheading_font_size,
        leading=subheading_leading,
        textColor=_EXPORT_HEADING_COLOR,
        spaceAfter=4,
        spaceBefore=8,
    )
    meta_style = ParagraphStyle(
        f"{namespace}Meta",
        parent=styles["BodyText"],
        fontName=BODY_FONT,
        fontSize=9.1,
        leading=12.0,
        textColor=_EXPORT_MUTED_COLOR,
        spaceAfter=0,
    )
    code_style = ParagraphStyle(
        f"{namespace}Code",
        parent=styles["Code"],
        fontName=MONO_FONT,
        fontSize=code_font_size,
        leading=code_leading,
        leftIndent=10,
        rightIndent=10,
        backColor=_EXPORT_CODE_BG,
        borderPadding=9,
        spaceAfter=8,
    )
    quote_style = ParagraphStyle(
        f"{namespace}Quote",
        parent=body_style,
        fontName=BODY_FONT,
        fontSize=max(9.8, body_font_size - 0.2),
        leading=max(14.4, body_leading - 0.6),
        leftIndent=14,
        rightIndent=4,
        textColor=colors.HexColor("#35435f"),
        backColor=_EXPORT_QUOTE_BG,
        borderPadding=9,
        spaceBefore=4,
        spaceAfter=8,
    )
    math_style = ParagraphStyle(
        f"{namespace}Math",
        parent=body_style,
        fontName=MONO_FONT,
        fontSize=max(9.4, body_font_size - 0.4),
        leading=max(13.4, body_leading - 1.6),
        alignment=TA_CENTER,
        textColor=colors.HexColor("#273654"),
        backColor=_EXPORT_MATH_BG,
        borderPadding=9,
        leftIndent=12,
        rightIndent=12,
        spaceBefore=4,
        spaceAfter=8,
    )
    table_header_style = ParagraphStyle(
        f"{namespace}TableHeader",
        parent=body_style,
        fontName=BOLD_FONT,
        fontSize=9.3,
        leading=12,
        textColor=_EXPORT_HEADING_COLOR,
        spaceAfter=0,
        spaceBefore=0,
    )
    table_body_style = ParagraphStyle(
        f"{namespace}TableBody",
        parent=body_style,
        fontName=BODY_FONT,
        fontSize=9.2,
        leading=12,
        textColor=_EXPORT_TEXT_COLOR,
        spaceAfter=0,
        spaceBefore=0,
    )

    return {
        "title": title_style,
        "body": body_style,
        "heading1": heading1_style,
        "heading": heading_style,
        "subheading": subheading_style,
        "meta": meta_style,
        "code": code_style,
        "quote": quote_style,
        "math": math_style,
        "table_header": table_header_style,
        "table_body": table_body_style,
    }
