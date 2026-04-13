"""
parser.py
---------
Reads a Movistar Empresas PDF and returns structured data.
Uses pdfplumber + regex — no API needed.
"""

import re
import sys


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

    return {
        "empresa":       empresa,
        "ruc":           ruc,
        "n_recibo":      recibo,
        "fecha_emision": fecha,
        "operador":      operador,
        "periodo":       periodo,
    }

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

        raw_amounts = amount_re.findall(block)
        amounts = [float(a.replace(',', '')) for a in raw_amounts]

        cargos     = [a for a in amounts if a > 0]
        descuentos = [a for a in amounts if a < 0]

        adicional_block = re.search(
            r'Cargos Adicionales Afectos:(.*?)(?=Descuentos|Cargos Adicionales Inafectos|Anexo|\Z)',
            block, re.DOTALL | re.IGNORECASE
        )
        cargo_adicional = 0.0
        if adicional_block:
            extra = amount_re.findall(adicional_block.group(1))
            cargo_adicional = sum(
                float(a.replace(',', '')) for a in extra
                if float(a.replace(',', '')) > 0
            )

        cargo_mensual = sum(cargos) - cargo_adicional
        desc_total    = sum(descuentos)
        total_linea   = cargo_mensual + desc_total + cargo_adicional

        lineas.append({
            "numero_linea":    phone,
            "plan":            plan,
            "cargo_mensual":   round(cargo_mensual, 2),
            "descuentos":      round(desc_total, 2),
            "cargo_adicional": round(cargo_adicional, 2),
            "total_linea":     round(total_linea, 2),
        })

    return lineas

def extract_from_pdf(pdf_path: str) -> dict:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("Error: pdfplumber not installed. Run: .venv/bin/pip install pdfplumber")

    with pdfplumber.open(pdf_path) as pdf:
        page1_text = pdf.pages[0].extract_text() or ""
        lines_text = ""
        for page in pdf.pages[2:]:
            t = page.extract_text()
            if t:
                lines_text += t + "\n"

    header = _parse_header(page1_text, lines_text)

    cutoff = lines_text.find("Detalle del recibo")
    if cutoff > 0:
        lines_text = lines_text[:cutoff]

    lineas = _parse_lines(lines_text)

    # Enrich each linea with header fields and blank manual columns
    for linea in lineas:
        linea["fecha_recepcion"]      = header["fecha_emision"]
        linea["operador"]             = header["operador"]
        linea["fecha_salida_ingreso"] = ""
        linea["tipo_equipo"]          = ""
        linea["inicio_contrato"]      = ""
        linea["usuario"]              = ""
        linea["cargo_puesto"]         = ""
        linea["dni"]                  = ""
        linea["area"]                 = ""
        linea["obra"]                 = ""
        linea["marca"]                = ""

    return {"header": header, "lineas": lineas}
