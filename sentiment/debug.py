"""Temporary terminal diagnostics for the sentiment page."""
import time
import traceback
import uuid
import sys
import threading
import pandas as pd

# Set to False to silence all sentiment diagnostics.
SENTIMENT_DEBUG = False


class SentimentDebug:
    def __init__(self, enabled=None, progress=None, slow_seconds=15):
        self.enabled = SENTIMENT_DEBUG if enabled is None else enabled
        self.progress = progress
        self.slow_seconds = slow_seconds
        self._timer = None
        self._generation = 0
        self._thread_id = threading.get_ident()
        self._caller_id = id(sys._getframe(1))
        self.run_id = uuid.uuid4().hex[:8]
        self.started = time.perf_counter()

    def close(self):
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _report_stall(self, generation, message):
        if generation != self._generation:
            return
        frame = sys._current_frames().get(self._thread_id)
        caller = frame
        while caller is not None and id(caller) != self._caller_id:
            caller = caller.f_back
        # The original page run may have finished, stopped, or been replaced.
        if caller is None:
            return
        stack = ''.join(traceback.format_stack(frame))
        print(f"[sentiment {self.run_id}] SLOW: no progress for "
              f"{self.slow_seconds}s after {message}\n{stack}", flush=True)

    def log(self, message):
        if self.enabled:
            self.close()
            print(
                f"[sentiment {self.run_id} {time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"+{time.perf_counter() - self.started:.3f}s {message}",
                flush=True,
            )
            if self.progress is not None:
                self.progress(message)
            if message.startswith("COMPLETE"):
                return
            self._timer = threading.Timer(
                self.slow_seconds, self._report_stall, (self._generation, message))
            self._timer.daemon = True
            self._timer.start()

    def call(self, label, function, *args, **kwargs):
        if not self.enabled:
            return function(*args, **kwargs)
        self.log(f"START {label}")
        started = time.perf_counter()
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            self.log(f"ERROR {label}: {type(exc).__name__}: {exc}")
            if self.enabled:
                traceback.print_exc()
            raise
        except BaseException:
            self.close()
            raise
        details = ""
        if isinstance(result, pd.DataFrame) and "date" in result.columns:
            details = f" rows={len(result)} latest={result['date'].max()}"
        self.log(f"DONE {label} ({time.perf_counter() - started:.3f}s){details}")
        return result
