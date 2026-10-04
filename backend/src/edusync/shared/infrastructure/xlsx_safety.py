"""Excel formula-injection defence (CWE-1236) for every generated workbook.

EduSync exports never contain intentional formulas. Any cell value starting with "=" comes from
user data (names, notes, imported files) and must be stored as plain text, never as a live formula.
"""
from __future__ import annotations

# XlsxWriter turns strings starting with "=" into formulas unless told otherwise.
XLSXWRITER_OPTIONS = {"in_memory": True, "strings_to_formulas": False}


def neutralize_formulas(workbook) -> None:
    """openpyxl: keep every "=..." cell as literal text (Excel displays it, never evaluates it)."""
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
