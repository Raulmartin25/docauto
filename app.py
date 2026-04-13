"""
app.py
------
FastAPI server. Run with:
    .venv/bin/uvicorn app:app --reload
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from parser import extract_from_pdf
from excel_generator import generate_excel

app = FastAPI(title="DocAuto")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


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

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"control_telefonia_{h['n_recibo']}_{ts}.xlsx"
        generate_excel(data, str(OUTPUT_DIR / filename))

        return {
            "empresa":       h["empresa"],
            "n_recibo":      h["n_recibo"],
            "operador":      h["operador"],
            "fecha_emision": h["fecha_emision"],
            "periodo":       h["periodo"],
            "total_lineas":  n,
            "filename":      filename,
            "header":        h,
            "lineas":        data["lineas"],
        }
    finally:
        os.unlink(tmp_path)


@app.post("/download-edited")
async def download_edited(request: Request):
    body = await request.json()
    header = body.get("header", {})
    lineas = body.get("lineas", [])

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"control_telefonia_{header.get('n_recibo', 'edited')}_{ts}.xlsx"
    out_path = str(OUTPUT_DIR / filename)
    generate_excel({"header": header, "lineas": lineas}, out_path)

    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@app.get("/download/{filename}")
async def download(filename: str):
    if not filename.startswith("control_telefonia_") or not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Archivo no válido.")

    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
