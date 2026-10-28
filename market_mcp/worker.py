"""A detached job worker. Only executes the fixed operation registry."""
from __future__ import annotations

import os
import runpy
import sys
import traceback

from . import jobs


def execute(kind: str, args: dict):
    from marketdb import db
    if kind == "update":
        from marketdb.run_daily import main
        argv = []
        if args["universes"] is not None:
            argv += ["--universe", *args["universes"]]
        if args["studies"] is not None:
            argv += ["--studies", *args["studies"]]
        if not args["fetch_prices"]:
            argv.append("--skip-fetch")
        argv.append("--refresh-universe" if args["refresh_universe"] else "--no-refresh-check")
        if args["rebuild_breadth"]:
            argv.append("--rebuild-breadth")
        if args["end"]:
            argv += ["--end", args["end"]]
        return main(argv)
    # Respect the daily runner's existing lock for other MCP writers as well.
    with db.RunLock() as held:
        if not held:
            raise RuntimeError(f"Another dashboard/daily process is updating the database: {held.holder}")
        if kind == "income_review":
            from .income import build_snapshot
            from etf.income_config import fingerprint
            from etf.income_store import save_review
            snapshot = build_snapshot(**args)
            snapshot['job_id'] = os.environ.get('MARKET_MCP_JOB_ID')
            snapshot['review_id'] = fingerprint({k: v for k, v in snapshot.items() if k != 'review_id'})
            return {'steps': [{'step': 'income_review', 'status': 'saved', **save_review(snapshot)}]}
        elif kind == "demark":
            from marketdb.demark import run_scan
            with db.session() as con:
                result, report = run_scan(con, args["universe"], args["min_cap"], args["max_cap"], args["end"])
                if result is None or result.empty:
                    raise RuntimeError("DeMark scan produced no results; check universe and price coverage")
        elif kind == "drawdown":
            from marketdb.drawdown import run_study, summary_text
            with db.session() as con:
                result = run_study(args["universe"], args["periods"], con, study_name=args["study_name"],
                                   filter_col=args["filter_column"], filter_val=args["filter_value"])
                print(summary_text(args["study_name"], result))
                if len(result) < len(args["periods"]):
                    print(f"WARNING: only {len(result)} of {len(args['periods'])} drawdown periods produced results")
        elif kind == "report":
            path = jobs.ROOT / jobs.REPORTS[args["report"]]
            os.chdir(path.parent)
            sys.path.insert(0, str(path.parent))
            sys.argv = [str(path)]
            runpy.run_path(str(path), run_name="__main__")
            if args['report'] in ('etf_income', 'etf_backtest'):
                import json
                with jobs.connection_for_audit() as con:
                    records = con.execute("SELECT payload FROM reports WHERE kind=? ORDER BY created DESC LIMIT 100",
                                          (args['report'] + '_run',)).fetchall()
                artifacts = [json.loads(row[0]) for row in records]
                artifacts = [a for a in artifacts if a.get('job_id') == os.environ.get('MARKET_MCP_JOB_ID')]
                if not artifacts:
                    raise RuntimeError('ETF generation produced no immutable output for this job; older daily/cache data is not proof of success')
                return {'steps': [{'step': args['report'], 'status': 'saved', 'run_id': a['run_id'],
                    'report_kind': a['kind'] + '_run', 'frames': a['frames'],
                    'warnings': (['Some universe tickers have no usable data'] if a.get('sources', {}).get('missing_tickers') else [])
                                + (['Some underlying RS values used the existing neutral fallback'] if a.get('sources', {}).get('missing_underlying_rs') else [])}
                    for a in artifacts]}
        else:
            raise ValueError("Unknown job kind")
    return 0


def main(job_id: str) -> int:
    os.environ['MARKET_MCP_JOB_ID'] = job_id
    from .version import code_version
    code_version()
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[variable] = "1"
    from marketdb import db
    with jobs.store() as con:
        row = con.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None or row["status"] != "starting":
            raise ValueError("Job is not waiting to run")
        job = jobs.job_value(row)
        con.execute("UPDATE jobs SET status='running',started=? WHERE job_id=?", (jobs.now(), job_id))
    before = 0
    try:
        with jobs.connection_for_audit() as audit:
            before = audit.execute("SELECT COALESCE(MAX(run_id),0) FROM runs").fetchone()[0]
    except Exception:
        pass
    status, message, code, outcome = "completed", "Finished. Stored results are available through the read tools.", 0, None
    try:
        print(f"Started {job['kind']} at {jobs.now()} — database {jobs.database_path()}", flush=True)
        executed = execute(job["kind"], job["arguments"])
        if isinstance(executed, dict):
            outcome, code = executed, 0
        else:
            code = executed or 0
        if code:
            status, message = "failed", f"Process exited with code {code}; inspect the log."
        else:
            with jobs.connection_for_audit() as audit:
                failed = audit.execute("SELECT run_id,kind,status,notes FROM runs WHERE run_id>? AND status IN ('error','partial','aborted')", (before,)).fetchall()
            sys.stdout.flush()
            log = (jobs.job_dir() / f"{job_id}.log").read_text(encoding="utf-8", errors="replace")
            if failed or any(step.get('warnings') for step in (outcome or {}).get('steps', [])) or any(marker in log for marker in ("coverage below", "FAILED", "WARNING:", "no results", "No data", "insufficient data")):
                status, message = "completed_with_warnings", "Some operations failed, were skipped or produced no data. Inspect the log and read_runs."
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
        status, message = ("failed", f"Script exited: {exc.code}") if code else ("completed_with_warnings", "Script exited early; check the log and stored outputs.")
    except BaseException as exc:
        traceback.print_exc()
        status, message, code = "failed", str(exc), 1
    finally:
        with jobs.store() as con:
            import json
            con.execute("UPDATE jobs SET status=?,finished=?,exit_code=?,message=?,outcome=? WHERE job_id=?",
                        (status, jobs.now(), code, message, json.dumps(outcome) if outcome is not None else None, job_id))
        print(f"{status}: {message}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
