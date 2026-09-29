"""Run the optional local Cockpit; the default is a network-free historical demo."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def init_workspace(path):
    target = Path(path).expanduser().resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError("目录不是空目录，已保留原内容；请使用新的研究目录")
    for child in ("tracking", "reports", "reference"):
        (target / child).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "examples/blank_tracking.csv", target / "tracking/forward_picks.csv")
    (target / "tracking/theme_taxonomy.csv").write_text(
        'layer,layer_name,subsector,board,theme_key,status,market,priority,leaders,bottleneck_pureplays,note,sublayer\n', encoding="utf-8")
    (target / "tracking/cross_theme_index_snapshot.csv").write_text(
        'snapshot_date,symbol,name,tier,archetypes,theme_count,stars,themes_list,themes_active_status\n', encoding="utf-8")
    (target / "reports/catalog.json").write_text('{"schema_version":1,"reports":{}}\n', encoding="utf-8")
    (target / ".gitignore").write_text('.env\n.cockpit/\n', encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Personal research folder with tracking/ and reports/")
    parser.add_argument("--init", type=Path, metavar="DIRECTORY", help="Create empty personal data templates, then exit")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true", help="Validate configuration and bundled UI, then exit")
    args = parser.parse_args()
    if args.init:
        print("Created personal research directory:", init_workspace(args.init))
        return 0
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.data_dir:
        os.environ["SERENITY_DATA_DIR"] = str(args.data_dir.expanduser().resolve())
    sys.path.insert(0, str(ROOT / "cockpit/backend"))
    import settings
    if not (settings.WEB_DIST / 'index.html').is_file():
        raise RuntimeError('缺少前端构建文件。源码用户先运行 npm --prefix cockpit/web ci 和 npm --prefix cockpit/web run build；发布 ZIP 已包含构建文件。')
    try:
        import uvicorn
        import main as backend
    except ImportError as exc:
        raise RuntimeError('请在项目环境安装 pip install -r cockpit/requirements.txt') from exc
    if args.check:
        import data
        picks, reports = data.load_picks(), data.load_reports()
        if settings.DEMO and (not picks or not reports):
            raise RuntimeError('演示数据或报告不完整，请重新下载完整发布包。')
        print(json.dumps({"ok": True, "version": settings.VERSION, "records": len(picks),
                          "reports": len(reports), **settings.mode_info()}, ensure_ascii=False))
        return 0
    print(f'Serenity Cockpit ({settings.mode_info()["dataset_label"]}): http://127.0.0.1:{args.port}')
    uvicorn.run(backend.app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
