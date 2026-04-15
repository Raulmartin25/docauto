"""
parser_claro.py
---------------
Reads a Claro Empresas PDF and returns structured data.
Uses pdfplumber + regex — no API needed.

Claro bill layout (CONSOLIDADO table columns after N° Celular):
  1. Total cargos fijos VOZ contratados
  2. Total tráfico VOZ adicional
  3. Total Servicios Adicionales
  4. Total LDN
  5. Total LDI
  6. Total Roaming
  7. Total por Equipos
  8. Monto Total por Línea   ← used as total_linea (already without IGV)
"""

import re

from parser_utils import BLANK_MANUAL_FIELDS, parse_float


def _parse_header(page1_text: str) -> dict:
    def find(pattern):
        m = re.search(pattern, page1_text, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    ruc      = find(r'R\.U\.C\.\s*:\s*(\d{11})')
    n_recibo = find(r'Recibo\s*:\s*(\S+)')
    periodo  = find(r'Per[ií]odo\s*:\s*([^\n]+)')
    fecha    = find(r'Fecha\s+Emisi[oó]n\s*:\s*(\d{2}/\w+/\d{4})')

    # Razón social is on the "Razón Social :" line
    empresa = find(r'Raz[oó]n\s+Social\s*:\s*([^\n]+)')

    # Detect carrier from text rather than hardcoding — this lets app.py surface
    # a clear mismatch error if the user uploads a Movistar (or other) bill here.
    if re.search(r'\bmovistar\b', page1_text, re.IGNORECASE):
        operador = "Movistar"
    else:
        operador = "Claro"

    return {
        "empresa":       empresa,
        "ruc":           ruc,
        "n_recibo":      n_recibo,
        "fecha_emision": fecha,
        "operador":      operador,
        "periodo":       periodo,
    }


# Amount: optional minus, digits/commas, dot, two decimals
_AMT = r'-?[\d,]+\.\d{2}'


def _parse_consolidado(full_text: str) -> dict:
    """
    Parse the CONSOLIDADO DE FACTURACIÓN POR LINEA table.

    Table columns (after N° Celular):
      cargos_fijos | trafico_adicional | servicios_adicionales |
      ldn | ldi | roaming | equipos | total_linea

    Returns dict: phone → row data dict.
    """
    start_m = re.search(
        r'CONSOLIDADO\s+DE\s+FACTURACI[OÓ]N\s+POR\s+L[IÍ]NEA', full_text, re.IGNORECASE
    )
    if not start_m:
        return {}

    block = full_text[start_m.start():]

    # Rows: 9-digit phone followed by exactly 8 decimal amounts
    row_re = re.compile(
        rf'^(9\d{{8}})\s+'   # N° Celular
        rf'({_AMT})\s+'      # Total cargos fijos VOZ
        rf'({_AMT})\s+'      # Total tráfico VOZ adicional
        rf'({_AMT})\s+'      # Total Servicios Adicionales
        rf'({_AMT})\s+'      # Total LDN
        rf'({_AMT})\s+'      # Total LDI
        rf'({_AMT})\s+'      # Total Roaming
        rf'({_AMT})\s+'      # Total por Equipos
        rf'({_AMT})',         # Monto Total por Línea
        re.MULTILINE,
    )

    result = {}
    for m in row_re.finditer(block):
        phone = m.group(1)
        result[phone] = {
            "cargo_fijos_voz":       parse_float(m.group(2)),
            "trafico_adicional":     parse_float(m.group(3)),
            "servicios_adicionales": parse_float(m.group(4)),
            "ldn":                   parse_float(m.group(5)),
            "ldi":                   parse_float(m.group(6)),
            "roaming":               parse_float(m.group(7)),
            "equipos":               parse_float(m.group(8)),
            "total_linea":           parse_float(m.group(9)),
        }

    return result


def _parse_planes(full_text: str) -> dict:
    """
    Parse plan names from CARGOS FIJOS DE PLANES DE VOZ CONTRATADOS section.
    Returns dict: phone → plan description (first match per phone).
    """
    start_m = re.search(
        r'CARGOS\s+FIJOS\s+DE\s+PLANES\s+DE\s+VOZ\s+CONTRATADOS', full_text, re.IGNORECASE
    )
    if not start_m:
        return {}

    block = full_text[start_m.start():]

    # Row: phone  description  dd/MMM/yy - dd/MMM/yy  amount
    # e.g.: 913007497 Max Negocios + 29.90 28/MAR/26 - 27/ABR/26 25.33
    row_re = re.compile(
        r'(9\d{8})\s+(.+?)\s+\d{2}/[A-Z]{3}/\d{2}\s+-\s+\d{2}/[A-Z]{3}/\d{2}\s+' + _AMT,
        re.IGNORECASE,
    )

    planes = {}
    for m in row_re.finditer(block):
        phone = m.group(1)
        if phone not in planes:
            planes[phone] = m.group(2).strip()

    return planes


def _parse_lines(consolidado: dict, planes: dict, header: dict) -> list:
    lineas = []
    for phone, row in consolidado.items():
        plan = planes.get(phone, "Sin plan")
        lineas.append({
            "numero_linea":            phone,
            "plan":                    plan,
            "cargo_mensual":           round(row["cargo_fijos_voz"], 2),
            "servicios_adicionales":   round(row["servicios_adicionales"], 2),
            "descuentos":              0.0,
            "cargo_adicional_inafecto": round(row["equipos"], 2),
            "total_linea":             round(row["total_linea"], 2),
            "fecha_recepcion": header["fecha_emision"],
            "operador":        "Claro",
            **BLANK_MANUAL_FIELDS,
        })
    return lineas


def extract_from_pdf(pdf_path: str) -> dict:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber not installed. Run: pip install pdfplumber") from exc

    with pdfplumber.open(pdf_path) as pdf:
        page1_text = pdf.pages[0].extract_text() or ""
        full_text  = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

    header      = _parse_header(page1_text)
    consolidado = _parse_consolidado(full_text)
    planes      = _parse_planes(full_text)
    lineas      = _parse_lines(consolidado, planes, header)

    return {"header": header, "lineas": lineas}
