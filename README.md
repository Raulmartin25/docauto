# DocAuto

Automatización inteligente de recibos de telefonía empresarial.  
Convierte un recibo PDF en un Excel de control en segundos.

---

## El problema

Las empresas con flotas de celulares (construcción, minería, telecomunicaciones) procesan sus recibos de telefonía **manualmente**: abrir el PDF, copiar cada línea a Excel, asignar centros de costo. Un recibo con 139 líneas toma entre 3 y 4 horas.

## La solución

DocAuto lee el PDF automáticamente, extrae todas las líneas móviles y genera un Excel listo para que el equipo administrativo solo complete los datos internos (usuario, área, obra).

---

## Stack

| Capa | Herramienta |
|------|-------------|
| Backend / API | [FastAPI](https://fastapi.tiangolo.com/) (Python) |
| Extracción PDF | [pdfplumber](https://github.com/jsvine/pdfplumber) + regex |
| Generación Excel | [openpyxl](https://openpyxl.readthedocs.io/) |
| Frontend | HTML + [Tailwind CSS](https://tailwindcss.com/) (CDN) |
| Servidor | [Uvicorn](https://www.uvicorn.org/) |

---

## Estructura del proyecto

```
docauto/
├── app.py               # Servidor FastAPI — endpoints HTTP
├── parser_movistar.py   # Parser de recibos Movistar Empresas
├── parser_claro.py      # Parser de recibos Claro Empresas
├── parser_utils.py      # Helpers compartidos entre parsers
├── excel_generator.py   # Genera el archivo Excel formateado
├── main.py              # CLI de desarrollo (sin servidor)
├── templates/
│   └── index.html       # UI con Tailwind CSS
├── output/              # Excels generados (creado automáticamente)
├── requirements.txt
├── .env                 # Variables de entorno (no subir a git)
└── .env.example
```

---

## Deploy local

### 1. Clonar el repositorio

```bash
git clone <repo-url>
cd docauto
```

### 2. Configurar la versión de Python con pyenv

```bash
pyenv local 3.14.2
pip install -r requirements.txt
```

### 3. Levantar el servidor

```bash
uvicorn app:app --reload --port 8000
```

Deberías ver en la terminal:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process ...
```

Abre **http://localhost:8000** en el navegador.

### 4. Usar la aplicación

1. Arrastra el PDF o haz clic para seleccionarlo (solo recibos de telefonía empresarial)
2. Selecciona el operador: **Movistar** o **Claro**
3. Clic en **Procesar →**
4. Edita cualquier celda de la tabla si es necesario
5. Clic en **Descargar Excel**

> Si el PDF no corresponde al operador seleccionado, la aplicación lo detecta y muestra un error claro antes de procesar.

> Para detener el servidor: `CTRL+C` en la terminal.

---

## Modo CLI (sin servidor)

Genera el Excel directamente en `output/` sin levantar ningún servidor:

```bash
PDF_PATH=/ruta/al/recibo.pdf python main.py
PDF_PATH=/ruta/al/recibo.pdf CARRIER=claro python main.py
```

---

## Excel generado

El archivo tiene dos tipos de columnas:

| Color | Columnas | Origen |
|-------|----------|--------|
| Rojo | Fecha de recepción, Línea, Operador, Plan, Cargo mensual, Descuentos, Total línea | Extraídas automáticamente del PDF |
| Amarillo | Fecha de salida/ingreso, Tipo de equipo, Inicio de contrato, Usuario, Cargo, DNI, Área, Obra, Marca | Completar manualmente |

Las columnas se filtran automáticamente según el operador — Claro y Movistar tienen estructuras de facturación distintas.

---

## Operadores soportados

- Movistar Empresas
- Claro Empresas

---

## Roadmap

- [x] Soporte para recibos de Movistar Empresas
- [x] Soporte para recibos de Claro Empresas
- [ ] Soporte para recibos de Entel
- [ ] Carga de roster de empleados para auto-completar columnas manuales
- [ ] Historial de recibos procesados
- [ ] Autenticación por empresa
- [ ] Deploy en Railway + Supabase

---

## Variables de entorno

Solo aplican al modo CLI (`main.py`). El servidor web (`app.py`) recibe estos valores desde el formulario.

| Variable | Descripción | Valores |
|----------|-------------|---------|
| `PDF_PATH` | Ruta al PDF a procesar | Requerido |
| `CARRIER` | Operador del recibo | `movistar` (default) \| `claro` |
