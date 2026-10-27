"""Shared subprocess helpers for running Python scripts/modules from this codebase.

Centralizes interpreter resolution and argument building so CLI, dashboard, and
bootstrap code paths use the same execution behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
from pathlib import Path
import sys
from typing import Mapping, Sequence


def python_executable() -> str:
    """Resolve a stable Python interpreter for in-repo helpers.

    Preference order:
    1. MARKETDB_PYTHON (explicit override)
    2. Project .venv / venv binaries (Windows and POSIX fallbacks)
    3. The current process executable
    4. Bare "python" fallback
    """
    configured = os.environ.get("MARKETDB_PYTHON")
    if configured and Path(configured).is_file():
        return str(Path(configured))

    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / "venv" / "Scripts" / "python.exe",
        project_root / ".venv" / "bin" / "python",
        project_root / "venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)

    if getattr(sys, "executable", None) and Path(sys.executable).is_file():
        return str(Path(sys.executable))
    return str(sys.executable or "python")


def _coerce_env(env: Mapping[str, str] | None) -> dict[str, str]:
    merged = os.environ.copy()
    merged.update(env or {})
    merged["PYTHONIOENCODING"] = "utf-8"
    return merged


@dataclass(frozen=True)
class RunResult:
    returncode: int
    command: list[str]
    stdout: str | None = None
    stderr: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _run_command(args: list[str], *, cwd: str | os.PathLike[str] | None = None,
                 env: Mapping[str, str] | None = None,
                 capture_output: bool = False) -> RunResult:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=_coerce_env(env),
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return RunResult(proc.returncode, [str(a) for a in args], proc.stdout, proc.stderr)


def run_script(script_path: str | os.PathLike[str], *args: str, cwd: str | os.PathLike[str] | None = None,
               env: Mapping[str, str] | None = None, capture_output: bool = False) -> RunResult:
    return _run_command([python_executable(), str(script_path), *map(str, args)], cwd=cwd, env=env,
                        capture_output=capture_output)


def run_module(module: str, *args: str, cwd: str | os.PathLike[str] | None = None,
               env: Mapping[str, str] | None = None, capture_output: bool = False) -> RunResult:
    return _run_command([python_executable(), "-m", module, *map(str, args)], cwd=cwd, env=env,
                        capture_output=capture_output)
