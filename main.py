"""
main.py
-------
Entry point. Run with:
    .venv/bin/python3 main.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from parser import extract_from_pdf
from excel_generator import generate_excel

load_dotenv()


def main():
    pdf_path = os.getenv("PDF_PATH", "/Users/martinquispe/Downloads/S3AA-0076408902.pdf")

    if not Path(pdf_path).exists():
        sys.exit(f"Error: PDF not found → {pdf_path}")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = str(output_dir / f"control_telefonia_{timestamp}.xlsx")

    print(f"Reading: {pdf_path}")
    data = extract_from_pdf(pdf_path)

    h = data["header"]
    n = len(data["lineas"])
    print(f"Extracted {n} lines  |  {h['empresa']}  |  Recibo {h['n_recibo']}")

    print("Generating Excel...")
    generate_excel(data, output_path)

    print(f"\nDone!  →  {output_path}")


if __name__ == "__main__":
    main()
