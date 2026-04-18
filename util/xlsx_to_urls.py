import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
URL_RE = re.compile(r"^https?://", re.IGNORECASE)
def _excel_col_to_index(col: str) -> int:
    idx = 0
    for ch in col:
        if not ("A" <= ch <= "Z"):
            break
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def _split_cell_ref(cell_ref: str) -> tuple[str, int]:
    col = []
    row = []
    for ch in cell_ref:
        if ch.isalpha():
            col.append(ch.upper())
        elif ch.isdigit():
            row.append(ch)
    col_s = "".join(col) or "A"
    row_n = int("".join(row)) if row else 0
    return col_s, row_n


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []

    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root.findall(".//x:si", XML_NS):
        text_parts = [t.text or "" for t in si.findall(".//x:t", XML_NS)]
        values.append("".join(text_parts))
    return values


def _resolve_first_sheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    first_sheet = workbook.find(".//x:sheets/x:sheet", XML_NS)
    if first_sheet is None:
        raise ValueError("No worksheet found in workbook.")

    rel_id = first_sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    if not rel_id:
        raise ValueError("Worksheet relationship id missing.")

    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    target = None
    for rel in rels.findall(".//r:Relationship", REL_NS):
        if rel.get("Id") == rel_id:
            target = rel.get("Target")
            break

    if not target:
        raise ValueError(f"Cannot resolve worksheet target for relation: {rel_id}")

    target_path = target.lstrip("/")
    if not target_path.startswith("xl/"):
        target_path = "xl/" + target_path
    return target_path


def _read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.get("t", "")
    if cell_type == "inlineStr":
        parts = [t.text or "" for t in cell.findall(".//x:t", XML_NS)]
        return "".join(parts).strip()

    value_node = cell.find("x:v", XML_NS)
    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text.strip()
    if cell_type == "s":
        try:
            idx = int(raw)
            if 0 <= idx < len(shared_strings):
                return shared_strings[idx].strip()
        except Exception:
            return ""
        return ""
    return raw.strip()


def extract_first_column_urls_from_xlsx(xlsx_path: Path) -> list[str]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_path = _resolve_first_sheet_path(zf)
        sheet_root = ET.fromstring(zf.read(sheet_path))

    urls: list[str] = []
    for row in sheet_root.findall(".//x:sheetData/x:row", XML_NS):
        a_cell = None
        for cell in row.findall("x:c", XML_NS):
            ref = cell.get("r", "")
            col, _ = _split_cell_ref(ref)
            if _excel_col_to_index(col) == 1:
                a_cell = cell
                break

        if a_cell is None:
            continue

        value = _read_cell_value(a_cell, shared_strings).strip()
        if not value:
            continue
        if not URL_RE.match(value):
            continue
        urls.append(value)
    return urls


def iter_xlsx_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError(f"Unsupported file type: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path not found: {input_path}")

    files = sorted(
        p for p in input_path.iterdir() if p.is_file() and p.suffix.lower() in {".xlsx", ".xlsm"}
    )
    if not files:
        raise FileNotFoundError(f"No xlsx/xlsm file found in directory: {input_path}")
    return files


def collect_urls(input_path: Path, limit: int | None = None) -> tuple[list[str], int]:
    files = iter_xlsx_files(input_path)
    seen: set[str] = set()
    urls: list[str] = []
    total_rows = 0

    for file_path in files:
        for value in extract_first_column_urls_from_xlsx(file_path):
            total_rows += 1
            url = value.strip()
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if limit is not None and len(urls) >= limit:
                return urls, total_rows
    return urls, total_rows


def write_urls(urls: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(urls), encoding="utf-8")
