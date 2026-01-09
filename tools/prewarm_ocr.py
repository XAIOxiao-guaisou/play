r"""Pre-warm EasyOCR models into project-local cache.

Usage:
  .venv\Scripts\python.exe tools\prewarm_ocr.py

It will:
- Ensure model cache dir: data/ocr_models
- Try to initialize easyocr.Reader (triggers model download if missing)
- Print a clear result and next steps when download is interrupted.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def main() -> int:
    print("[prewarm_ocr] python=", sys.executable)

    model_dir = Path("data/ocr_models")
    model_dir.mkdir(parents=True, exist_ok=True)
    print("[prewarm_ocr] model_dir=", model_dir.resolve())

    # Common EasyOCR model filenames (may vary slightly by version)
    expected = [
        "craft_mlt_25k.pth",  # detector
        "zh_sim_g2.pth",      # recognizer (simplified chinese)
        "english_g2.pth",     # recognizer (english)
    ]

    existing = {p.name for p in model_dir.glob("*.pth")}
    print(f"[prewarm_ocr] existing_pth={sorted(existing)}")

    missing = [name for name in expected if name not in existing]
    if missing:
        print(f"[prewarm_ocr] missing_expected={missing} (will try auto-download)")
    else:
        print("[prewarm_ocr] expected model files already present")

    try:
        import easyocr  # type: ignore
    except Exception as exc:
        print("[prewarm_ocr] ERROR: easyocr import failed:", repr(exc))
        print("[prewarm_ocr] Fix: pip install easyocr")
        return 2

    t0 = time.time()
    try:
        reader = easyocr.Reader(
            ["ch_sim", "en"],
            gpu=False,
            model_storage_directory=str(model_dir.resolve()),
            download_enabled=True,
        )
        _ = reader
    except Exception as exc:
        dt = time.time() - t0
        print(f"[prewarm_ocr] ERROR: reader init failed after {dt:.1f}s")
        print("[prewarm_ocr]", repr(exc))
        print("[prewarm_ocr] Likely cause: model download interrupted / unstable network")
        print("[prewarm_ocr] Next steps:")
        print("  1) re-run this script until success (it will resume/redo downloads)")
        print("  2) or manually place model .pth files into data/ocr_models")
        return 3

    dt = time.time() - t0
    existing = {p.name for p in model_dir.glob("*.pth")}
    print(f"[prewarm_ocr] OK: reader initialized in {dt:.1f}s")
    print(f"[prewarm_ocr] now_pth={sorted(existing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
