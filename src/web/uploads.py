from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.datastructures import UploadFile


async def save_uploaded_file(
    upload: UploadFile,
    *,
    upload_dir: Path,
    upload_extensions: set[str],
    safe_str,
) -> str:
    file_name = safe_str(upload.filename)
    if not file_name:
        raise ValueError("upload filename is empty")
    suffix = Path(file_name).suffix.lower()
    if suffix not in upload_extensions:
        raise ValueError(f"unsupported upload file suffix: {suffix}")

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name).stem).strip("._")
    if not safe_stem:
        safe_stem = "upload"

    upload_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    output_path = upload_dir / f"{stamp}_{safe_stem}{suffix}"

    content = await upload.read()
    output_path.write_bytes(content)
    await upload.close()
    return str(output_path)
