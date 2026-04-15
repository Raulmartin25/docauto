"""
app.py
------
FastAPI server. Run with:
    uvicorn app:app --reload
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

import parser_movistar
import parser_claro
from excel_generator import generate_excel

app = FastAPI(title="DocAuto")


BASE_DIR = Path(__file__).parent

@app.get("/", response_class=HTMLResponse)
async def index():
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/process")
async def process_pdf(file: UploadFile = File(...), carrier: str = Form("movistar")):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")

    # Assign tmp_path before the try so the finally can always clean up,
    # even if the file write fails mid-way.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name          # captured immediately after file creation
            tmp.write(await file.read())

        try:
            if carrier.lower() == "claro":
                data = parser_claro.extract_from_pdf(tmp_path)
            else:
                data = parser_movistar.extract_from_pdf(tmp_path)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo procesar el PDF: {exc}. "
                       "Asegúrate de subir un recibo de telefonía empresarial válido.",
            ) from exc

        h = data["header"]
        n = len(data["lineas"])

        # Carrier mismatch: Movistar parser detects the real carrier from PDF text.
        # If it found a different carrier than what the user selected, surface it clearly.
        # (Claro parser hardcodes "Claro" so this only fires for the Movistar→other direction.)
        detected = h.get("operador", "")
        if detected and detected.lower() not in ("desconocido", "") and detected.lower() != carrier.lower():
            raise HTTPException(
                status_code=422,
                detail=f"El PDF parece ser de {detected} pero seleccionaste '{carrier}'. "
                       "Selecciona el operador correcto e intenta de nuevo.",
            )

        if n == 0:
            raise HTTPException(
                status_code=422,
                detail="No se encontraron líneas móviles en el PDF. "
                       "Asegúrate de subir un recibo de telefonía empresarial (Movistar o Claro) "
                       "y que el operador seleccionado sea el correcto.",
            )

        return {
            "empresa":       h["empresa"],
            "n_recibo":      h["n_recibo"],
            "operador":      h["operador"],
            "fecha_emision": h["fecha_emision"],
            "periodo":       h["periodo"],
            "total_lineas":  n,
            "header":        h,
            "lineas":        data["lineas"],
        }
    finally:
        if tmp_path:
            os.unlink(tmp_path)


@app.post("/download-edited")
async def download_edited(request: Request):
    body   = await request.json()
    header = body.get("header", {})
    lineas = body.get("lineas", [])

    xlsx_bytes = generate_excel({"header": header, "lineas": lineas})
    filename   = f"control_telefonia_{header.get('n_recibo', 'edited')}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
