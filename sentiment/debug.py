"""Temporary terminal diagnostics for the sentiment page."""
import time
import traceback
import uuid
import pandas as pd

# Set to False to silence all sentiment diagnostics.
SENTIMENT_DEBUG = True


class SentimentDebug:
    def __init__(self):
        self.run_id = uuid.uuid4().hex[:8]
        self.started = time.perf_counter()

    def log(self, message):
        if SENTIMENT_DEBUG:
            print(
                f"[sentiment {self.run_id} {time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"+{time.perf_counter() - self.started:.3f}s {message}",
                flush=True,
            )

    def call(self, label, function, *args, **kwargs):
        self.log(f"START {label}")
        started = time.perf_counter()
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            self.log(f"ERROR {label}: {type(exc).__name__}: {exc}")
            if SENTIMENT_DEBUG:
                traceback.print_exc()
            raise
        details = ""
        if isinstance(result, pd.DataFrame) and "date" in result.columns:
            details = f" rows={len(result)} latest={result['date'].max()}"
        self.log(f"DONE {label} ({time.perf_counter() - started:.3f}s){details}")
        return result
