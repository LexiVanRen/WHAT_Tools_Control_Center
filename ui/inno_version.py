import re
from pathlib import Path

_VERSION_RE = re.compile(r'^\s*#define\s+MyAppVersion\s+"([^"]+)"\s*$', re.IGNORECASE)

def read_myappversion_from_iss(iss_path: str) -> str:
    p = Path(iss_path)
    print(p)
    if not p.exists() or not p.is_file():
        return ""
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = _VERSION_RE.match(line)
            if m:
                return m.group(1).strip()
    except Exception:
        return ""
    return ""
