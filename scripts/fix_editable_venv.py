#!/usr/bin/env python3
"""Fix macOS-hidden .pth files in the project venv so `import lerobot` works.

Python 3.12+ site.py skips .pth files with UF_HIDDEN (st_flags & 0x8000).
After `uv sync`, every .pth under site-packages can get UF_HIDDEN on macOS,
so editable installs break while console scripts still install.
"""

from __future__ import annotations

import argparse
import configparser
import os
import stat
import subprocess
from pathlib import Path

UF_HIDDEN = stat.UF_HIDDEN
WRAPPER_MARKER = "# LEROBOT_PTH_FIX"
ACTIVATE_MARKER_START = "# >>> lerobot-macos-pth-fix >>>"
ACTIVATE_MARKER_END = "# <<< lerobot-macos-pth-fix <<<"
ACTIVATE_HOOK = f"""{ACTIVATE_MARKER_START}
# Python 3.12+ skips UF_HIDDEN .pth files; uv can mark them hidden on macOS.
if [ -n "${{VIRTUAL_ENV:-}}" ]; then
  for _lerobot_pth in "${{VIRTUAL_ENV}}"/lib/python*/site-packages/*.pth; do
    [ -e "$_lerobot_pth" ] || continue
    chflags nohidden "$_lerobot_pth" 2>/dev/null || true
  done
  unalias python 2>/dev/null || true
  hash -r 2>/dev/null || true
fi
{ACTIVATE_MARKER_END}
"""


def site_packages(venv: Path) -> Path:
    lib = venv / "lib"
    for child in sorted(lib.glob("python*/site-packages")):
        return child
    raise FileNotFoundError(f"No site-packages under {lib}")


def pth_flags(path: Path) -> int:
    return os.lstat(path).st_flags


def unhide_pth(path: Path) -> bool:
    if pth_flags(path) & UF_HIDDEN:
        subprocess.run(["chflags", "nohidden", str(path)], check=True)
        return True
    return False


def unhide_all_pth(sp: Path, quiet: bool) -> list[str]:
    fixed: list[str] = []
    for pth in sorted(sp.glob("*.pth")):
        before = pth_flags(pth)
        if before & UF_HIDDEN:
            unhide_pth(pth)
            after = pth_flags(pth)
            fixed.append(pth.name)
            if not quiet:
                print(f"Unhid {pth.name} (st_flags {before} -> {after})")
        elif not quiet:
            print(f"OK {pth.name} (st_flags={before})")
    return fixed


def console_script_modules(sp: Path) -> dict[str, str]:
    """Map CLI name -> python -m module (from lerobot dist-info entry_points)."""
    for ep in sp.glob("lerobot-*.dist-info/entry_points.txt"):
        parser = configparser.ConfigParser()
        parser.read(ep, encoding="utf-8")
        if not parser.has_section("console_scripts"):
            continue
        modules: dict[str, str] = {}
        for name, target in parser.items("console_scripts"):
            module = target.split(":", 1)[0]
            modules[name] = module
        return modules
    return {}


def wrap_console_script(script_path: Path, module: str) -> bool:
    if script_path.is_file() and WRAPPER_MARKER in script_path.read_text(encoding="utf-8"):
        return False
    wrapper = f"""#!/bin/bash
{WRAPPER_MARKER}
set -euo pipefail
_VENV="$(cd "$(dirname "$0")/.." && pwd)"
for _pth in "$_VENV"/lib/python*/site-packages/*.pth; do
  [ -e "$_pth" ] || continue
  chflags nohidden "$_pth" 2>/dev/null || true
done
exec "$_VENV/bin/python3" -m {module} "$@"
"""
    script_path.write_text(wrapper, encoding="utf-8")
    script_path.chmod(0o755)
    return True


def wrap_python_launcher(venv: Path, quiet: bool) -> bool:
    """Wrap .venv/bin/python so `python` / `python3` unhide .pth before starting."""
    bin_dir = venv / "bin"
    python_link = bin_dir / "python"
    real_backup = bin_dir / "._python_real"

    if python_link.is_file() and not python_link.is_symlink():
        if WRAPPER_MARKER in python_link.read_text(encoding="utf-8"):
            return False
    elif python_link.is_symlink():
        real_target = os.path.realpath(python_link)
        if real_backup.exists() and os.path.realpath(real_backup) != real_target:
            real_backup.unlink()
        if not real_backup.exists():
            real_backup.symlink_to(real_target)
    else:
        if not quiet:
            print(f"Skip python wrap: missing {python_link}")
        return False

    if python_link.is_symlink():
        python_link.unlink()

    wrapper = f"""#!/bin/bash
{WRAPPER_MARKER}
set -euo pipefail
_VENV="$(cd "$(dirname "$0")/.." && pwd)"
for _pth in "$_VENV"/lib/python*/site-packages/*.pth; do
  [ -e "$_pth" ] || continue
  chflags nohidden "$_pth" 2>/dev/null || true
done
exec "$(dirname "$0")/._python_real" "$@"
"""
    python_link.write_text(wrapper, encoding="utf-8")
    python_link.chmod(0o755)
    if not quiet:
        print(f"Wrapped {python_link.name} (python3 -> unhide .pth -> ._python_real)")
    return True


def wrap_all_console_scripts(venv: Path, sp: Path, quiet: bool) -> list[str]:
    modules = console_script_modules(sp)
    if not modules:
        if not quiet:
            print("No lerobot console_scripts in dist-info; run uv sync first")
        return []

    wrapped: list[str] = []
    bin_dir = venv / "bin"
    for name, module in sorted(modules.items()):
        script = bin_dir / name
        if not script.is_file():
            continue
        if wrap_console_script(script, module):
            wrapped.append(name)
            if not quiet:
                print(f"Wrapped {name} -> python -m {module}")
    return wrapped


def install_activate_hook(venv: Path, quiet: bool) -> None:
    activate = venv / "bin" / "activate"
    if not activate.is_file():
        raise FileNotFoundError(f"Missing {activate}")

    text = activate.read_text(encoding="utf-8")
    if ACTIVATE_MARKER_START in text:
        start = text.index(ACTIVATE_MARKER_START)
        end = text.index(ACTIVATE_MARKER_END) + len(ACTIVATE_MARKER_END)
        text = text[:start] + ACTIVATE_HOOK.strip() + text[end:]
        if not quiet:
            print(f"Updated activate hook in {activate}")
    else:
        text = text.rstrip() + "\n\n" + ACTIVATE_HOOK + "\n"
        if not quiet:
            print(f"Installed activate hook in {activate}")

    activate.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")


def verify_import(venv: Path, repo: Path, quiet: bool) -> int:
    py = venv / "bin" / "python3"
    proc = subprocess.run(
        [str(py), "-c", "import lerobot; print(lerobot.__file__)"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    if proc.returncode != 0:
        if not quiet:
            print("import lerobot failed:", proc.stderr.strip() or proc.stdout.strip())
            print("Try: ./scripts/sync.sh --extra feetech --extra viz --extra dataset")
        return 1
    if not quiet:
        print("import lerobot OK:", proc.stdout.strip())
    return 0


def _hide_all_pth(sp: Path) -> None:
    for pth in sp.glob("*.pth"):
        subprocess.run(["chflags", "hidden", str(pth)], check=False)


def verify_cli_without_activate(venv: Path, repo: Path, quiet: bool) -> int:
    """Ensure lerobot-teleoperate works even when .pth files are still hidden."""
    sp = site_packages(venv)
    _hide_all_pth(sp)
    try:
        cli = venv / "bin" / "lerobot-teleoperate"
        proc = subprocess.run(
            [str(cli), "--help"],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        if proc.returncode != 0:
            if not quiet:
                print("lerobot-teleoperate --help failed:", proc.stderr.strip() or proc.stdout.strip())
            return 1
        if not quiet:
            print("lerobot-teleoperate --help OK (with hidden .pth, no activate)")
        return 0
    finally:
        for pth in sp.glob("*.pth"):
            unhide_pth(pth)


def verify_python_with_hidden_pth(venv: Path, repo: Path, quiet: bool) -> int:
    """Ensure `python -c import lerobot` works via wrapped .venv/bin/python3."""
    sp = site_packages(venv)
    _hide_all_pth(sp)
    try:
        py = venv / "bin" / "python3"
        proc = subprocess.run(
            [str(py), "-c", "import lerobot; print(lerobot.__file__)"],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        if proc.returncode != 0:
            if not quiet:
                print("python3 -c import lerobot failed:", proc.stderr.strip() or proc.stdout.strip())
            return 1
        if not quiet:
            print("python3 -c import lerobot OK (with hidden .pth):", proc.stdout.strip())
        return 0
    finally:
        for pth in sp.glob("*.pth"):
            unhide_pth(pth)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print errors")
    parser.add_argument(
        "--skip-activate-hook",
        action="store_true",
        help="Do not append the hook to .venv/bin/activate",
    )
    parser.add_argument(
        "--skip-wrap-cli",
        action="store_true",
        help="Do not wrap lerobot-* console scripts with bash shims",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    venv = repo / ".venv"
    sp = site_packages(venv)
    pth_files = list(sp.glob("*.pth"))

    if not pth_files:
        if not args.quiet:
            print("No .pth files in site-packages; run: ./scripts/sync.sh --extra feetech --extra viz --extra dataset")
        return 1

    unhide_all_pth(sp, quiet=args.quiet)
    if not args.skip_wrap_cli:
        wrap_python_launcher(venv, quiet=args.quiet)
        wrap_all_console_scripts(venv, sp, quiet=args.quiet)
    if not args.skip_activate_hook:
        install_activate_hook(venv, quiet=args.quiet)

    code = verify_import(venv, repo, quiet=args.quiet)
    if code != 0:
        return code

    if not args.skip_wrap_cli:
        code = verify_cli_without_activate(venv, repo, quiet=args.quiet)
        if code != 0:
            return code
        return verify_python_with_hidden_pth(venv, repo, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
