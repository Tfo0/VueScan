import re
from pathlib import Path


HREF_RE = re.compile(r"href\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
def iter_html_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in {".html", ".htm"}:
            raise ValueError(f"Unsupported file type: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path not found: {input_path}")

    files = sorted(
        [
            p
            for p in input_path.rglob("*")
            if p.is_file() and p.suffix.lower() in {".html", ".htm"}
        ]
    )
    if not files:
        raise FileNotFoundError(f"No html/htm file found in directory: {input_path}")
    return files


def extract_hrefs(html_path: Path, http_only: bool = True) -> list[str]:
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    values: list[str] = []
    for href in HREF_RE.findall(text):
        value = href.strip()
        if not value:
            continue
        if http_only and not HTTP_RE.match(value):
            continue
        values.append(value)
    return values


def collect_hrefs(input_path: Path, limit: int | None = None, http_only: bool = True) -> tuple[list[str], int]:
    files = iter_html_files(input_path)
    seen: set[str] = set()
    urls: list[str] = []
    total_hrefs = 0

    for file_path in files:
        for value in extract_hrefs(file_path, http_only=http_only):
            total_hrefs += 1
            if value in seen:
                continue
            seen.add(value)
            urls.append(value)
            if limit is not None and len(urls) >= limit:
                return urls, total_hrefs
    return urls, total_hrefs


def write_urls(urls: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(urls), encoding="utf-8")
