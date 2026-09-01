from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART_DIR = ROOT / "scripts" / ".repair"
INSTALLER = ROOT / "scripts" / "apply_aninexus_repair.py"
EXPECTED_SHA256 = "1d3968c1d0daee73fb03b71d7d0b2fcaec1bdd6cb463ff921e07538556937b46"


def main() -> None:
    parts = sorted(PART_DIR.glob("part-*.txt"))
    if len(parts) != 4:
        raise RuntimeError(f"expected 4 payload parts, found {len(parts)}")

    source = "".join(path.read_text(encoding="utf-8") for path in parts)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"repair payload checksum mismatch: {digest}")

    INSTALLER.write_text(source, encoding="utf-8")
    subprocess.run([sys.executable, str(INSTALLER)], cwd=ROOT, check=True)

    shutil.rmtree(PART_DIR, ignore_errors=True)
    Path(__file__).unlink(missing_ok=True)
    print("AniNexus repair bootstrap completed.")


if __name__ == "__main__":
    main()
