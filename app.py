"""
app.py
------
FastAPI server. Run with:
    uvicorn app:app --reload
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from parser import extract_from_pdf
from excel_generator import generate_excel

app = FastAPI(title="DocAuto")


BASE_DIR = Path(__file__).parent

@app.get("/", response_class=HTMLResponse)
async def index():
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/process")
async def process_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        data = extract_from_pdf(tmp_path)
        h    = data["header"]
        n    = len(data["lineas"])

        if n == 0:
            raise HTTPException(
                status_code=422,
                detail="No se encontraron líneas móviles en el PDF. "
                       "Asegúrate de subir un recibo de telefonía empresarial (Movistar, Claro o Entel)."
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
