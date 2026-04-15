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
