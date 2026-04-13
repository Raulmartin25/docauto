"""
excel_generator.py
------------------
Takes structured data (from parser.py) and writes a formatted Excel file.
"""

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# (column label, width, is_auto_extracted, data_key)
COLUMNS = [
    # True  = Auto-extracted from the PDF
    # False = Fill manually
    ("FECHA DE RECEPCIÓN",          16,  True,  "fecha_recepcion"),
    ("LÍNEA",                       14,  True,  "numero_linea"),
    ("FECHA DE SALIDA O INGRESO",   22, False,  "fecha_salida_ingreso"),
    ("OPERADOR",                    13,  True,  "operador"),
    ("TIPO DE EQUIPO",              16, False,  "tipo_equipo"),
    ("INICIO DE CONTRATO",          18, False,  "inicio_contrato"),
    ("USUARIO",                     22, False,  "usuario"),
    ("CARGO",                       16, False,  "cargo_puesto"),
    ("DNI",                         12, False,  "dni"),
    ("ÁREA",                        16, False,  "area"),
    ("OBRA",                        22, False,  "obra"),
    ("MARCA",                       13, False,  "marca"),
    ("PLAN",                        38,  True,  "plan"),
    ("CARGO MENSUAL S/ (sin IGV)",  22,  True,  "cargo_mensual"),
    ("DESCUENTOS S/",               16,  True,  "descuentos"),
    ("TOTAL LÍNEA S/ (sin IGV)",    20,  True,  "total_linea"),
]

_NUMERIC_KEYS = {"cargo_mensual", "descuentos", "total_linea"}

def _border():
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)

def _fill(hex_color):
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")

def _center():
    return Alignment(horizontal="center", vertical="center")

def generate_excel(data: dict, output_path: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Control Telefonía"

    h      = data["header"]
    lineas = data["lineas"]
    n_cols = len(COLUMNS)
    last   = get_column_letter(n_cols)

    # ── Row 1 – Title ─────────────────────────────────────────────────────
    ws.merge_cells(f"A1:{last}1")
    ws["A1"] = f"CONTROL DE TELEFONÍA MÓVIL  ·  {h['empresa']}"
    ws["A1"].font      = Font(bold=True, size=13, color="1F4E79")
    ws["A1"].alignment = _center()
    ws["A1"].fill      = _fill("D6E4F0")
    ws.row_dimensions[1].height = 28

    # ── Row 2 – Receipt metadata ──────────────────────────────────────────
    meta = [
        ("Operador",  h["operador"]),
        ("Recibo N°", h["n_recibo"]),
        ("Emisión",   h["fecha_emision"]),
        ("Período",   h["periodo"]),
        ("RUC",       h["ruc"]),
    ]
    col = 1
    for label, value in meta:
        ws.cell(2, col,     label).font = Font(bold=True, size=9, color="1F4E79")
        ws.cell(2, col,     label).fill = _fill("D6E4F0")
        ws.cell(2, col + 1, value).font = Font(size=9)
        ws.cell(2, col + 1, value).fill = _fill("D6E4F0")
        col += 2
    if col <= n_cols:
        ws.merge_cells(f"{get_column_letter(col)}2:{last}2")
        ws.cell(2, col).fill = _fill("D6E4F0")
    ws.row_dimensions[2].height = 18

    # ── Row 3 – Legend ────────────────────────────────────────────────────
    ws.merge_cells(f"A3:{last}3")
    ws["A3"] = (
        "  Columnas AMARILLAS → completar manualmente   |   "
        "Columnas ROJAS → extraídas automáticamente del recibo PDF"
    )
    ws["A3"].font      = Font(italic=True, size=8, color="595959")
    ws["A3"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[3].height = 14

    # ── Row 4 – Column headers ────────────────────────────────────────────
    HDR_ROW = 4
    for ci, (label, width, is_auto, _key) in enumerate(COLUMNS, 1):
        cell = ws.cell(HDR_ROW, ci, label)
        cell.fill      = _fill("C00000" if is_auto else "1F4E79")
        cell.font      = Font(bold=True, size=9, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = _border()
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[HDR_ROW].height = 32

    # ── Data rows ─────────────────────────────────────────────────────────
    for i, linea in enumerate(lineas):
        row_data = []
        for _, _, _, key in COLUMNS:
            val = linea.get(key, "")
            if key in _NUMERIC_KEYS and val != "":
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    pass
            row_data.append(val)
        ws.append(row_data)
        dr  = ws.max_row
        alt = i % 2 == 0

        for ci, (_, _, is_auto, _key) in enumerate(COLUMNS, 1):
            cell = ws.cell(dr, ci)
            cell.border    = _border()
            cell.alignment = Alignment(vertical="center")
            if is_auto:
                cell.fill = _fill("FCE4D6" if alt else "FADADD")
                if ci >= 14:
                    cell.number_format = "#,##0.00"
            else:
                cell.fill = _fill("FFFFC0") if cell.value == "" else _fill("EBF3FB" if alt else "FFFFFF")

    # ── Totals row ────────────────────────────────────────────────────────
    ds = HDR_ROW + 1
    de = ws.max_row
    tr = ws.max_row + 1

    ws.cell(tr, 1, "TOTAL").font      = Font(bold=True, color="FFFFFF")
    ws.cell(tr, 1).fill               = _fill("1F4E79")
    ws.cell(tr, 1).alignment          = _center()
    ws.cell(tr, 1).border             = _border()
    ws.cell(tr, 2, f"{len(lineas)} líneas").font = Font(bold=True, color="FFFFFF")
    ws.cell(tr, 2).fill               = _fill("1F4E79")
    ws.cell(tr, 2).alignment          = _center()
    ws.cell(tr, 2).border             = _border()

    for ci in range(3, n_cols + 1):
        cell = ws.cell(tr, ci)
        if ci >= 14:
            cell.value         = f"=SUM({get_column_letter(ci)}{ds}:{get_column_letter(ci)}{de})"
            cell.number_format = "#,##0.00"
        cell.fill      = _fill("1F4E79")
        cell.font      = Font(bold=True, color="FFFFFF")
        cell.alignment = _center()
        cell.border    = _border()

    ws.freeze_panes = f"A{HDR_ROW + 1}"
    wb.save(output_path)
