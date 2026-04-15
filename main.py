"""
main.py
-------
Local dev CLI. Run with:
    PDF_PATH=/path/to/bill.pdf python main.py
    PDF_PATH=/path/to/bill.pdf CARRIER=claro python main.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import parser_movistar
import parser_claro
from excel_generator import generate_excel

load_dotenv()


def main():
    pdf_path = os.getenv("PDF_PATH")
    if not pdf_path:
        sys.exit("Error: PDF_PATH not set. Export PDF_PATH=/path/to/bill.pdf or add it to .env")

    if not Path(pdf_path).exists():
        sys.exit(f"Error: PDF not found → {pdf_path}")

    carrier = os.getenv("CARRIER", "movistar").lower()
    if carrier not in ("movistar", "claro"):
        sys.exit(f"Error: CARRIER must be 'movistar' or 'claro', got '{carrier}'")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = str(output_dir / f"control_telefonia_{timestamp}.xlsx")

    print(f"Reading: {pdf_path}  [carrier={carrier}]")
    data = parser_claro.extract_from_pdf(pdf_path) if carrier == "claro" else parser_movistar.extract_from_pdf(pdf_path)

    h = data["header"]
    n = len(data["lineas"])
    print(f"Extracted {n} lines  |  {h['empresa']}  |  Recibo {h['n_recibo']}")

    print("Generating Excel...")
    xlsx_bytes = generate_excel(data)
    Path(output_path).write_bytes(xlsx_bytes)

    print(f"\nDone!  →  {output_path}")


if __name__ == "__main__":
    main()
