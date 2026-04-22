"""
parser_movistar.py
------------------
Reads a Movistar Empresas PDF and returns structured data.
Uses pdfplumber + regex — no API needed.
"""

import re

from parser_utils import BLANK_MANUAL_FIELDS, normalize_text, parse_float
from plan_categories import CATEGORY_COLUMNS, categorize_linea, is_roaming_charge


def _parse_header(page1_text: str, full_text: str = "") -> dict:
    def find(pattern):
        m = re.search(pattern, page1_text)
        return m.group(1).strip() if m else ""

    recibo = find(r'N[º°"\(cid:176\)]+\s*recibo:\s*(\S+)')
    ruc    = find(r'RUC:\s*(\d{11})')

    year_match = re.search(r'\b(20\d{2})\b', page1_text)
    year = year_match.group(1) if year_match else "2026"

    two_dates = re.search(r'(\d{2}/\d{2})\s+\d{2}/\d{2}', page1_text)
    fecha = f"{two_dates.group(1)}/{year}" if two_dates else ""

    periodo_match = re.search(r'(\d+[A-Za-z]+\s+al\s+\d+[A-Za-z]+)', page1_text + " " + full_text)
    periodo = periodo_match.group(1) if periodo_match else ""

    all_text = (page1_text + " " + full_text).lower()
    if "movistar" in all_text:
        operador = "Movistar"
    elif "claro" in all_text:
        operador = "Claro"
    elif "entel" in all_text:
        operador = "Entel"
    else:
        operador = "Desconocido"

    # Company name appears on the line immediately before "RUC:XXXXXXXXXXX"
    empresa_match = re.search(r'([^\n]+)\n\s*RUC:\s*\d{11}', page1_text)
    empresa = empresa_match.group(1).strip() if empresa_match else ""
    empresa = re.sub(r'\s+S/[\d,]+\.\d{2}.*$', '', empresa).strip()

    # Top-level amounts from the "Resumen de Recibo" block on page 1.
    # Captured so the category summary sheet can reconcile vs. the real total.
    def _amount(label_re: str) -> float:
        m = re.search(label_re + r'\s*S/\s*(-?[\d,]+\.\d{2})', page1_text, re.IGNORECASE)
        return parse_float(m.group(1)) if m else 0.0

    return {
        "empresa":       empresa,
        "ruc":           ruc,
        "n_recibo":      recibo,
        "fecha_emision": fecha,
        "operador":      operador,
        "periodo":       periodo,
        "redondeo":       _amount(r'Redondeo'),
        "total_a_pagar":  _amount(r'Total\s+a\s+pagar'),
    }

# Row inside an Anexo section, e.g. "B2B Movistar Empresas S/62.9 (16Mar al 15Abr) S/53.30".
# Group 1: concept (plan/descuento/cargo name), group 2: amount. A trailing
# "(period)" paren group is allowed and swallowed so it doesn't leak into the
# concept. The amount is required to have two decimals (S/1.23), which lets us
# distinguish it from plan-name tokens like "S/62.9" or "S/155".
_PLAN_ROW_RE = re.compile(
    r'^(.+?)(?:\s+\([^)]+\))?\s+S/(-?[\d,]+\.\d{2})\s*$'
)

def _extract_section_rows(block: str, section_re: str) -> list[tuple[str, float]]:
    """Pull (concept, amount) pairs out of a named section of an Anexo block.

    Concept strings still carry the '(16Mar al 15Abr)' period suffix if present
    in the source; callers that need the bare plan name should strip it.
    """
    m = re.search(section_re, block, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    rows = []
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line:
            continue
        row = _PLAN_ROW_RE.match(line)
        if not row:
            continue
        rows.append((row.group(1).strip(), parse_float(row.group(2))))
    return rows


def _section_sum(block: str, section_re: str, amount_re, mode: str = "positive") -> float:
    """Sum amounts found inside a named section of an Anexo block.

    mode="positive" → sum positive values only
    mode="negative" → sum negative values only
    mode="all"      → sum all values
    """
    m = re.search(section_re, block, re.DOTALL | re.IGNORECASE)
    if not m:
        return 0.0
    vals = [parse_float(a) for a in amount_re.findall(m.group(1))]
    if mode == "positive":
        return sum(v for v in vals if v > 0)
    if mode == "negative":
        return sum(v for v in vals if v < 0)
    return sum(vals)


# Splits "Cargos Adicionales Afectos" into:
#   roaming total, non-roaming total, and the raw rows (for category mapping).
def _split_afecto_afectos(block: str) -> tuple[float, float, list]:
    rows = _extract_section_rows(
        block,
        r'Cargos Adicionales Afectos:(.*?)(?=Cargos Adicionales Inafectos|Redondeo|Anexo|\Z)',
    )
    roaming = other = 0.0
    kept = []
    for concept, amount in rows:
        if amount <= 0:
            continue
        kept.append({"concept": concept, "amount": round(amount, 2)})
        if is_roaming_charge(concept):
            roaming += amount
        else:
            other += amount
    return round(roaming, 2), round(other, 2), kept


def _parse_lines(full_text: str) -> list:
    amount_re = re.compile(r'S/(-?[\d,]+\.\d{2})')
    plan_re   = re.compile(
        r'Cargos Mensuales:\s*(.+?)\s*\((?:\d+[A-Za-z]+\s+al\s+\d+[A-Za-z]+)\)',
        re.IGNORECASE
    )

    blocks = re.split(r'(?=\bAnexo\s+\d+:\s+\d{9,10}\b)', full_text)

    lineas = []
    for block in blocks:
        header_match = re.match(r'\bAnexo\s+\d+:\s+(\d{9,10})\b', block.strip())
        if not header_match:
            continue

        phone = header_match.group(1)

        plan_match = plan_re.search(block)
        plan = plan_match.group(1).strip() if plan_match else "Sin plan"

        # Parse each section independently to avoid cross-section contamination
        plan_rows = _extract_section_rows(
            block,
            r'Cargos Mensuales:(.*?)(?=Descuentos|Cargos Adicionales|Redondeo|Anexo|\Z)',
        )
        cargo_mensual = sum(a for _, a in plan_rows if a > 0)

        desc_total = _section_sum(
            block,
            r'Descuentos[^:]*:(.*?)(?=Cargos Adicionales|Redondeo|Anexo|\Z)',
            amount_re, mode="negative",
        )

        cargo_inafecto = _section_sum(
            block,
            r'Cargos Adicionales Inafectos:(.*?)(?=Redondeo|Anexo|\Z)',
            amount_re, mode="positive",
        )

        roaming, afecto_otros, afecto_rows = _split_afecto_afectos(block)

        total_linea = cargo_mensual + desc_total + roaming + afecto_otros

        lineas.append({
            "numero_linea":    phone,
            "plan":            plan,
            "plan_rows":       [{"concept": c, "amount": round(a, 2)} for c, a in plan_rows],
            "cargo_mensual":   round(cargo_mensual, 2),
            "descuentos":      round(desc_total, 2),
            "roaming":         roaming,
            "cargo_adicional_afecto": afecto_otros,
            "adicional_afecto_rows": afecto_rows,
            "cargo_adicional_inafecto": round(cargo_inafecto, 2),
            "total_linea":     round(total_linea, 2),
        })

    return lineas

def extract_from_pdf(pdf_path: str) -> dict:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber not installed. Run: pip install pdfplumber") from exc

    with pdfplumber.open(pdf_path) as pdf:
        page1_text = normalize_text(pdf.pages[0].extract_text() or "")
        lines_text = ""
        for page in pdf.pages[2:]:
            t = page.extract_text()
            if t:
                lines_text += normalize_text(t) + "\n"

    header = _parse_header(page1_text, lines_text)

    cutoff = lines_text.find("Detalle del recibo")
    if cutoff > 0:
        lines_text = lines_text[:cutoff]

    lineas = _parse_lines(lines_text)

    # Enrich each linea with header fields, blank manual columns, and a
    # flattened per-category breakdown (so each category becomes its own
    # column in the Excel main sheet).
    for linea in lineas:
        linea["fecha_recepcion"] = header["fecha_emision"]
        linea["operador"]        = header["operador"]
        linea.update(BLANK_MANUAL_FIELDS)
        cats = categorize_linea(linea)
        for cat_label, _short, key in CATEGORY_COLUMNS:
            linea[key] = cats.get(cat_label, 0.0)

    return {"header": header, "lineas": lineas}
