"""
plan_categories.py
------------------
Classifies Movistar Empresas plan strings into the 8 reporting categories
used in the client's control sheet.
"""

import re

CATEGORIES = [
    "B2B Movistar",
    "Paquete Móvil",
    "Internet Móvil",
    "Internet Teletrabajo",
    "Movistar Empresas",
    "Roaming, llamadas región y SMS internacional",
    "Descuentos y bonificaciones",
    "Monto total",
]

OTROS = "Otros"

_PATTERNS = [
    (re.compile(r"^\s*B2B[_\s]", re.IGNORECASE),                          "B2B Movistar"),
    (re.compile(r"^\s*Paquete\s+M[oó]vil", re.IGNORECASE),                "Paquete Móvil"),
    (re.compile(r"^\s*(Recarga\s+)?Internet\s+m[oó]vil", re.IGNORECASE),  "Internet Móvil"),
    (re.compile(r"^\s*Plan\s+Internet\s+de\s+Teletrabajo", re.IGNORECASE),
                                                                           "Internet Teletrabajo"),
    (re.compile(r"^\s*(Mi\s+)?Movistar\s+Empresas", re.IGNORECASE),       "Movistar Empresas"),
]

_ROAMING_RE = re.compile(
    r"roaming|internacional|larga\s+distancia|ldi|sms\s+internacional",
    re.IGNORECASE,
)


def classify_plan(plan: str) -> str:
    """Map a plan string to one of the 5 plan-family categories, or 'Otros'.

    LDI / roaming / international markers take precedence: e.g. "Paquete Móvil
    LDI" is a long-distance-international pack, so it belongs in cat 6 even
    though the name starts with "Paquete Móvil".
    """
    if not plan:
        return OTROS
    if _ROAMING_RE.search(plan):
        return CATEGORIES[5]
    for pattern, category in _PATTERNS:
        if pattern.search(plan):
            return category
    return OTROS


def is_roaming_charge(concept: str) -> bool:
    """True if an additional-afecto concept looks like roaming/LDI/int'l."""
    return bool(_ROAMING_RE.search(concept or ""))


def _num(v) -> float:
    """Coerce a numeric field that may arrive as a string after the browser
    round-trip. Empty / non-numeric values become 0.0."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


# Per-line category breakdown shown in the Excel main sheet and preview.
# Tuple order matches CATEGORIES[:7]. Short labels are used as Excel column
# headers; full labels live in CATEGORIES and drive the Resumen sheet.
CATEGORY_COLUMNS = [
    # (full label used in Resumen,                   short column header,        linea dict key)
    (CATEGORIES[0], "B2B Movistar",                  "cat_b2b"),
    (CATEGORIES[1], "Paquete Móvil",                 "cat_paquete_movil"),
    (CATEGORIES[2], "Internet Móvil",                "cat_internet_movil"),
    (CATEGORIES[3], "Internet Teletrabajo",          "cat_internet_teletrabajo"),
    (CATEGORIES[4], "Movistar Empresas",             "cat_movistar_empresas"),
    (CATEGORIES[5], "Roaming / LDI / SMS Int.",      "cat_roaming"),
    (CATEGORIES[6], "Descuento y Bonificación",      "cat_descuentos"),
]


def categorize_linea(linea: dict) -> dict:
    """Distribute a linea's amounts across the 7 non-total categories.

    Returns a dict keyed by the same strings as CATEGORIES[:7] plus OTROS
    (0.0 if nothing fell through). All values are sin-IGV and rounded.
    """
    out = {c: 0.0 for c in CATEGORIES[:7]}
    out[OTROS] = 0.0

    # Monthly plan charges. A single anexo can bundle several plans
    # (e.g. B2B + Paquete Móvil LDI), so we classify each row separately.
    plan_rows = linea.get("plan_rows") or [
        {"concept": linea.get("plan", ""), "amount": linea.get("cargo_mensual", 0.0)}
    ]
    for row in plan_rows:
        amount = _num(row.get("amount"))
        cat    = classify_plan(row.get("concept", ""))
        if cat in out:
            out[cat] += amount
        else:
            out[OTROS] += amount

    # Additional afecto charges (roaming, data recharges, etc.).
    for row in linea.get("adicional_afecto_rows", []):
        amount  = _num(row.get("amount"))
        concept = row.get("concept", "")
        if is_roaming_charge(concept):
            out[CATEGORIES[5]] += amount
            continue
        cat = classify_plan(concept)
        if cat in out:
            out[cat] += amount
        else:
            out[OTROS] += amount

    out[CATEGORIES[6]] += _num(linea.get("descuentos"))

    return {k: round(v, 2) for k, v in out.items()}


def summarize_by_category(header: dict, lineas: list) -> list:
    """Return the 8-category summary as a list of (label, amount) tuples.

    Amounts are sin-IGV except `Monto total`, which is the final billed amount
    from the receipt header (con IGV + inafectos + redondeo). When a cargo
    concept doesn't fit any plan family, it falls into an 'Otros' bucket
    appended after category 6 so the sheet remains reconciled.
    """
    totals = {c: 0.0 for c in CATEGORIES}
    otros  = 0.0

    for linea in lineas:
        cats = categorize_linea(linea)
        for k, v in cats.items():
            if k == OTROS:
                otros += v
            elif k in totals:
                totals[k] += v

    totals[CATEGORIES[6]] += _num(header.get("redondeo"))
    totals[CATEGORIES[7]]  = _num(header.get("total_a_pagar"))

    result = [(cat, round(totals[cat], 2)) for cat in CATEGORIES]
    if round(otros, 2) != 0.0:
        # Keep the 8 required categories first; surface stragglers after cat 6
        # so the report stays auditable.
        result.insert(6, (OTROS, round(otros, 2)))
    return result
