"""Generate and strictly validate the historical public demo without network access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from render_report import render

ROOT = Path(__file__).resolve().parents[1]


def run(output=None):
    directory = Path(output).resolve() if output else ROOT / "reports"
    registry = ROOT / "tracking/forward_picks.csv"
    before = hashlib.sha256(registry.read_bytes()).hexdigest()
    spec = json.loads((ROOT / "examples/demo_spec.json").read_text(encoding="utf-8"))
    spec.update(out=str(directory / "demo-report.html"), tracking_file=str(directory / "demo_tracking.csv"))
    report = render(spec)
    subprocess.run([sys.executable, str(ROOT / "scripts/verify_report.py"), report,
                    "--scan", str(ROOT / "examples/demo_scan.json"), "--tracking", spec["tracking_file"],
                    "--today", spec["date"], "--strict"], check=True)
    if hashlib.sha256(registry.read_bytes()).hexdigest() != before:
        raise RuntimeError("The historical public registry unexpectedly changed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Output directory; defaults to the package's reports directory")
    args = parser.parse_args()
    print("Offline demo passed:", run(args.output))
