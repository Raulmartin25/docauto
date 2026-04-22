"""
parser_utils.py
---------------
Shared helpers used by all carrier parsers.
"""

# Fields every linea dict must include but are filled in manually by the user
# (not extractable from the PDF). Both parsers initialise these to empty string
# so the Excel generator and browser preview always find every expected key.
# Add new manual columns here — one place, both parsers pick them up.
BLANK_MANUAL_FIELDS: dict = {
    "fecha_salida_ingreso": "",
    "tipo_equipo":          "",
    "inicio_contrato":      "",
    "usuario":              "",
    "cargo_puesto":         "",
    "dni":                  "",
    "area":                 "",
    "obra":                 "",
    "marca":                "",
}


def parse_float(s) -> float:
    """Convert a string amount (may contain commas) to float. Returns 0.0 on failure."""
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


# pdfplumber emits "(cid:N)" for glyphs whose Unicode mapping is missing from
# the font. Movistar's receipts rely on a handful of these for Spanish accents.
_CID_MAP = {
    "(cid:176)": "º",   "(cid:218)": "Ú",   "(cid:237)": "í",   "(cid:243)": "ó",
    "(cid:233)": "é",   "(cid:225)": "á",   "(cid:250)": "ú",   "(cid:241)": "ñ",
    "(cid:161)": "¡",   "(cid:191)": "¿",   "(cid:150)": "-",   "(cid:201)": "É",
    "(cid:193)": "Á",   "(cid:205)": "Í",   "(cid:211)": "Ó",   "(cid:209)": "Ñ",
}


def normalize_text(s: str) -> str:
    """Replace pdfplumber's (cid:N) escapes with their actual glyphs."""
    if not s:
        return s
    for cid, char in _CID_MAP.items():
        s = s.replace(cid, char)
    return s
