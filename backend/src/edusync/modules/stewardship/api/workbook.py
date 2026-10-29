"""Permission-scoped inventory workbook rendering (no cross-school data access here)."""
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas


def workbook_bytes(title: str, headers: list[str], records: list[tuple]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = title[:31]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="17365D")
    for record in records:
        sheet.append([str(value) if value is not None else "" for value in record])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(48, max(14, max(len(str(cell.value or "")) for cell in column) + 2))
    neutralize_formulas(book)
    output = BytesIO()
    book.save(output)
    return output.getvalue()
