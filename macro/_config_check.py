"""Friendly failure when macro/config.py is missing or still the template.

config.py is gitignored (it holds API keys), so a fresh clone does not have it. Every macro
script gets its FRED key through fred_api_key() so the failure is a three-line explanation
instead of an ImportError traceback.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.py")
PLACEHOLDER = "your_key_here"

SETUP_STEPS = (
    "macro/config.py is missing or still has the placeholder key (it is gitignored because it holds API keys).\n"
    "  1. copy macro/config_template.py to macro/config.py\n"
    "  2. put a FRED API key in it - free at https://fred.stlouisfed.org/docs/api/api_key.html\n"
    "  3. re-run: Macro page -> 'Run Macro Report', or  python launcher.py 1 16 17\n"
)


def config_problem() -> str | None:
    """None when config.py exists with a real FRED key, else a short explanation."""
    if not os.path.exists(CONFIG_PATH):
        return "macro/config.py not found"
    try:
        text = open(CONFIG_PATH, encoding="utf-8").read()
    except OSError as e:
        return f"macro/config.py unreadable: {e}"
    if PLACEHOLDER in text.split("FRED_API_KEY", 1)[-1][:80]:
        return "macro/config.py still has the placeholder FRED_API_KEY"
    return None


def fred_api_key() -> str:
    """The FRED key from config.py, or exit 2 with setup instructions on stderr."""
    problem = config_problem()
    if problem is None:
        try:
            from config import FRED_API_KEY          # scripts run with cwd = macro/
        except ImportError:
            from macro.config import FRED_API_KEY    # imported from the repo root (dashboard)
        if FRED_API_KEY and FRED_API_KEY != PLACEHOLDER:
            return FRED_API_KEY
        problem = "FRED_API_KEY is empty"
    sys.stderr.write(f"{problem}\n{SETUP_STEPS}")
    sys.exit(2)


def optional_key(name: str) -> str:
    """A non-essential key (e.g. ANTHROPIC_API_KEY) from config.py, '' if absent."""
    try:
        try:
            import config as _c
        except ImportError:
            from macro import config as _c
        return getattr(_c, name, "") or ""
    except ImportError:
        return ""
