"""Regenerate the JSON fixtures used by the frontend unit tests from the real backend."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from cfg_analyzer.analyzer import analyze_source  # noqa: E402
from cfg_analyzer.validation import validate_request  # noqa: E402

OUT = ROOT / "frontend" / "src" / "__tests__" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
for name in ("15_switch_and_conditions", "06_for_continue", "14_infinite_loop", "13_unreachable"):
    src = (ROOT / "examples" / f"{name}.c").read_text()
    result = analyze_source(validate_request({"source": src}))
    (OUT / f"{name}.json").write_text(json.dumps(result, indent=1))
    print("wrote", name)
