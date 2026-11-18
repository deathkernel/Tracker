from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

html = Path("index.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
if not scripts:
    raise SystemExit("No inline JavaScript block found in index.html")
with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
    handle.write("\n".join(scripts))
    script_path = Path(handle.name)
try:
    subprocess.run(["node", "--check", str(script_path)], check=True)
finally:
    script_path.unlink(missing_ok=True)
print(f"Validated {len(scripts)} inline JavaScript block(s).")
