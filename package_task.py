from __future__ import annotations

import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXED_TIME = (2026, 8, 12, 0, 0, 0)
with zipfile.ZipFile(ROOT / "task/输入数据包.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted((ROOT / "input/input_data").rglob("*")):
        if path.is_file():
            info = zipfile.ZipInfo(path.relative_to(ROOT / "input").as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
