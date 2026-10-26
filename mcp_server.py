"""Market Intelligence MCP entry point (HTTP on 8766, or stdio)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def lower_priority():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)
    else:
        os.nice(5)


def main():
    parser = argparse.ArgumentParser(description="Market Intelligence MCP — private LAN HTTP or stdio")
    parser.add_argument("--transport", choices=("streamable-http", "stdio"), default="streamable-http")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--allowed-host", action="append")
    parser.add_argument("--allowed-origin", action="append", default=[])
    args = parser.parse_args()
    from market_mcp.config import load_config, normalise
    try:
        config = load_config(args.config)
        config = normalise({**config, **({"database": str(args.database)} if args.database else {}),
                            **({"port": args.port} if args.port is not None else {}),
                            **({"bind_address": args.host} if args.host else {}),
                            **({"allowed_hosts": args.allowed_host} if args.allowed_host else {})})
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if not Path(config["database"]).is_file():
        parser.error("Database missing: bootstrap the project or set --database to its existing market.db")
    os.environ["MARKETDB_PATH"] = config["database"]
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[variable] = "1"
    lower_priority()
    try:
        from market_mcp.server import create_server, http_app
    except ModuleNotFoundError as exc:
        if exc.name in ("mcp", "anyio", "starlette", "uvicorn"):
            parser.exit(1, "Install the optional server dependencies: python -m pip install -r requirements-mcp.txt\n")
        raise
    server = create_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        import uvicorn
        print(f"Market Intelligence MCP: port {config['port']}; database {config['database']}", file=sys.stderr)
        uvicorn.run(http_app(server, config["bind_address"], config["allowed_hosts"], args.allowed_origin),
                    host=config["bind_address"], port=config["port"], workers=1, limit_concurrency=16,
                    access_log=False, log_level="warning", proxy_headers=False, timeout_keep_alive=5)


if __name__ == "__main__":
    main()
