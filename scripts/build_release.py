"""Build reproducible v0.2 archives from an explicit public-file allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("SKILL.md", "README.md", "LICENSE", "VERSION", "CHANGELOG.md", ".env.example",
              "requirements.txt", "requirements-ashare.txt", "requirements-lock.txt")
SOURCE_DIRS = ("agents", "scripts", "reference", "examples", "tests")
COCKPIT_FILES = ("README.md", "run.py", "requirements.txt", "requirements-test.txt", "requirements-lock.txt",
    "THIRD_PARTY_NOTICES.txt", "web/package.json", "web/package-lock.json", "web/tsconfig.json",
    "web/vite.config.ts", "web/index.html", "demo/reports/demo-report.html", "demo/reports/catalog.json")
COCKPIT_DIRS = ("backend", "demo", "tests", "web/src", "web/tests", "web/dist")
TRACKING_FILES = ("forward_picks.csv", "theme_benchmark.csv", "cross_theme_index_snapshot.csv",
    "scorecard.md", "cross_theme_scan.py", "score_tracker.py", "check_desc_freshness.py",
    "_full_scan.py", "_scan_agent.py", "_scan_agent_cn.py", "_scan_AIAgent_CN_v1.json",
    "_scan_AIAgent_v1.json", "_scan_AMR_v2.json", "_scan_自动驾驶L4_v2.json")


def release_files(root=ROOT):
    paths = [root / name for name in ROOT_FILES]
    for directory in SOURCE_DIRS:
        paths.extend(p for p in (root / directory).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix != '.pyc' and not p.name.startswith('.'))
    # Only the existing, explicitly public tracking assets; generated caches are excluded.
    paths.extend(root / 'tracking' / name for name in TRACKING_FILES)
    if not (root / 'cockpit/web/dist/index.html').is_file():
        raise FileNotFoundError('Build the optional Cockpit UI with npm --prefix cockpit/web run build before packaging.')
    paths.extend(root / 'cockpit' / name for name in COCKPIT_FILES)
    for directory in COCKPIT_DIRS:
        paths.extend(p for p in (root / 'cockpit' / directory).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix != '.pyc' and not p.name.startswith('.'))
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Release file is not a regular in-repository asset: '+str(path))
        if not path.is_file():
            raise FileNotFoundError(path)
    return sorted(set(paths))


def build(output):
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    name = 'serenity-bottleneck-hunter'
    archive = destination / f'{name}-v{version}.zip'
    manifest = {}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in release_files():
            relative = path.relative_to(ROOT).as_posix()
            payload = path.read_bytes()
            # Git checkouts may change CRLF. Normalize text so platform-specific checkout does not alter the archive.
            if path.suffix not in {'.png', '.jpg', '.jpeg', '.pdf'}:
                payload = payload.replace(b'\r\n', b'\n')
            entry = zipfile.ZipInfo(name+'/'+relative, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            zipped.writestr(entry, payload)
            manifest[relative] = hashlib.sha256(payload).hexdigest()
    skill = archive.with_suffix('.skill')
    shutil.copyfile(archive, skill)
    (destination / 'manifest.json').write_text(json.dumps({'version':version,'revision':'cockpit-r2',
        'cockpit_included':True,'files':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checksums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in (archive, skill))
    (destination / 'SHA256SUMS.txt').write_text(checksums,encoding='utf-8')
    return archive


def smoke_archive(archive, cockpit=False):
    with tempfile.TemporaryDirectory() as folder:
        with zipfile.ZipFile(archive) as zipped:
            # This archive was assembled only from the fixed allowlist above.
            for name in zipped.namelist():
                target = (Path(folder) / name).resolve()
                if not target.is_relative_to(Path(folder).resolve()):
                    raise ValueError('Unsafe archive member')
            zipped.extractall(folder)
        extracted = Path(folder) / 'serenity-bottleneck-hunter'
        subprocess.run([sys.executable, str(extracted/'scripts/run_demo.py')], cwd=folder, check=True)
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(extracted/'tests'), '-q'], cwd=folder, check=True)
        if cockpit:
            subprocess.run([sys.executable, str(extracted/'cockpit/run.py'), '--check'], cwd=folder, check=True)
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(extracted/'cockpit/tests'), '-q'], cwd=folder, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT/'dist'))
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--cockpit-smoke', action='store_true', help='Also validate Cockpit; requires its test dependencies')
    args = parser.parse_args()
    result = build(args.output)
    if args.smoke or args.cockpit_smoke:
        smoke_archive(result, cockpit=args.cockpit_smoke)
    print(result)
