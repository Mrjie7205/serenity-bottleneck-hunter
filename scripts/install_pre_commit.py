"""Install an opt-in repository-local hook without overwriting an existing hook."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys


def install(repo):
    root = Path(subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], text=True).strip())
    configured = subprocess.run(["git", "-C", str(root), "config", "--get", "core.hooksPath"], capture_output=True, text=True)
    if configured.returncode == 0:
        raise ValueError("A custom hooksPath is configured; add the verifier to that hook manually.")
    raw = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--git-path", "hooks/pre-commit"], text=True).strip()
    hook = Path(raw) if Path(raw).is_absolute() else root / raw
    verifier = root / "scripts/verify_tickers.py"
    if not verifier.is_file():
        raise ValueError("The repository does not contain scripts/verify_tickers.py")
    content = '#!/bin/sh\n# serenity-bottleneck-hunter managed hook\nexec ' + shlex.quote(sys.executable.replace('\\', '/')) + ' scripts/verify_tickers.py --staged\n'
    if hook.is_symlink():
        raise FileExistsError("An existing hook symlink was preserved.")
    if hook.exists():
        if hook.read_text(encoding="utf-8-sig") == content:
            return hook
        raise FileExistsError("An existing hook was preserved. Add the verifier command to it manually.")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(content, encoding="utf-8", newline="\n")
    hook.chmod(hook.stat().st_mode | 0o111)
    return hook


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    try:
        print("Installed:", install(args.repo))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
