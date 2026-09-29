"""Explicit separation of public code, read-only demo data, and personal state."""
import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = PACKAGE_ROOT / "cockpit" / "demo"
selected = os.environ.get("SERENITY_DATA_DIR", "").strip()
DATA_DIR = Path(selected).expanduser().resolve() if selected else DEMO_DIR
DEMO = DATA_DIR == DEMO_DIR.resolve()
if not (DATA_DIR / "tracking" / "forward_picks.csv").is_file():
    raise RuntimeError("研究目录缺少 tracking/forward_picks.csv；请先运行 cockpit/run.py --init <目录>")
STATE_DIR = (PACKAGE_ROOT / "cockpit" / ".runtime" / "demo") if DEMO else DATA_DIR / ".cockpit"
WEB_DIST = PACKAGE_ROOT / "cockpit" / "web" / "dist"
VERSION = "0.2.0-cockpit-r2"
from dotenv import load_dotenv
if not DEMO:
    load_dotenv(DATA_DIR / ".env")
load_dotenv(PACKAGE_ROOT / ".env")


def mode_info():
    return {"demo": DEMO, "dataset_label": "离线历史演示" if DEMO else "个人研究",
            "live_data_enabled": not DEMO, "price_asof": "2026-06-01" if DEMO else None}


def require_personal_data():
    if DEMO:
        raise PermissionError("离线演示不会取价或保存告警，请先指定自己的研究目录")
