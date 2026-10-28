"""A running process captures its code fingerprint at startup for deployment checks."""
from functools import lru_cache
import hashlib
from pathlib import Path

VERSION = "1.1.0"


@lru_cache(maxsize=1)
def code_version():
    root = Path(__file__).resolve().parents[1]
    paths = [*sorted((root / 'market_mcp').glob('*.py')),
             *[root / 'etf' / name for name in ('income_config.py', 'income_rules.py', 'income_store.py',
                                               'etf_income_data.py', 'etf_backtest.py', 'etf_prices.py')]]
    # Git's Windows line-ending conversion must not make identical source look different.
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest() for p in paths}
    digest = hashlib.sha256(''.join(f'{key}:{value}\n' for key, value in sorted(manifest.items())).encode()).hexdigest()
    return {'service_version': VERSION, 'source_sha256': digest, 'files': manifest}
