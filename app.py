"""
app.py
------
FastAPI server. Run with:
    uvicorn app:app --reload
"""

import os
import secrets
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

import parser_movistar
import parser_claro
from excel_generator import generate_excel
from rate_limit import RateLimitExceeded, check_rate_limit

load_dotenv()

app = FastAPI(title="DocAuto")

RATE_LIMIT_MAX = 2
RATE_LIMIT_WINDOW_SECONDS = 3600
COOKIE_NAME = "docauto_rl"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365  # 1 year


def _raw_client_ip(request: Request) -> str:
    # Vercel places the real client IP first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _client_subnet(request: Request) -> str:
    # Peruvian ISPs reassign IPs within the same /16 after a modem restart
    # (the /24 changes, /16 usually stays), so keying the rate limit on /16
    # defeats the restart bypass. Cost: up to 65,536 IPs share one counter
    # — fine at current scale, revisit if DocAuto hits heavy usage.
    ip = _raw_client_ip(request)
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.0.0"
    return ip  # IPv6 or malformed — use as-is


def _serialize_cookie(name: str, value: str, max_age: int, secure: bool) -> str:
    # FastAPI's HTTPException path drops cookies set via the injected Response,
    # so error responses need the cookie injected manually via this header string.
    parts = [f"{name}={value}", f"Max-Age={max_age}", "Path=/", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


BASE_DIR = Path(__file__).parent

@app.get("/", response_class=HTMLResponse)
async def index():
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/process")
async def process_pdf(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    carrier: str = Form("movistar"),
):
    # Read existing cookie or mint a new UUID. Refresh expiry on every use.
    cookie_id = request.cookies.get(COOKIE_NAME) or secrets.token_urlsafe(16)
    secure_cookie = request.url.scheme == "https"

    # Success path: the injected Response carries the cookie through.
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_id,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
    )

    # Error path: HTTPException drops the injected Response's cookies, so
    # every HTTPException raised from this handler must carry Set-Cookie
    # explicitly. The wrapping try/except below handles that uniformly.
    cookie_header = _serialize_cookie(
        COOKIE_NAME, cookie_id, COOKIE_MAX_AGE_SECONDS, secure_cookie,
    )

    try:
        return await _process_pdf_inner(request, cookie_id, file, carrier)
    except HTTPException as exc:
        merged = dict(exc.headers or {})
        merged["Set-Cookie"] = cookie_header
        raise HTTPException(exc.status_code, exc.detail, headers=merged) from exc


async def _process_pdf_inner(
    request: Request,
    cookie_id: str,
    file: UploadFile,
    carrier: str,
):
    # Two parallel rate limits: IP /16 subnet (catches modem-restart bypass)
    # and cookie UUID (catches users who change IP but keep the browser).
    # Either over its limit → 429.
    try:
        await check_rate_limit(
            identifier=_client_subnet(request),
            limit=RATE_LIMIT_MAX,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
            namespace="process",
        )
        await check_rate_limit(
            identifier=cookie_id,
            limit=RATE_LIMIT_MAX,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
            namespace="cookie",
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Has alcanzado el límite de {RATE_LIMIT_MAX} conversiones por hora. "
                "Intenta de nuevo más tarde."
            ),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

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

        # Carrier mismatch: both parsers detect the real carrier from PDF text.
        # If it differs from what the user selected, surface a clear error.
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
