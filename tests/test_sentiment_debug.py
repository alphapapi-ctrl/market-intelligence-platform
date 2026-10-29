import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from sentiment.debug import SentimentDebug


class SentimentDebugTests(unittest.TestCase):
    def test_disabled_is_silent_and_preserves_return_value(self):
        output = io.StringIO()
        with patch('sentiment.debug.threading.Timer') as timer, redirect_stdout(output):
            debug = SentimentDebug(enabled=False)
            debug.log('step')
            self.assertEqual(debug.call('fetch', lambda: 42), 42)
        self.assertEqual(output.getvalue(), '')
        timer.assert_not_called()

    def test_progress_cancels_previous_watchdog_and_completion_stops_it(self):
        progress = Mock()
        with patch('sentiment.debug.threading.Timer') as timer, redirect_stdout(io.StringIO()):
            debug = SentimentDebug(enabled=True, progress=progress)
            debug.log('step one')
            previous = debug._generation
            debug.log('step two')
            self.assertGreater(debug._generation, previous)
            timer.return_value.cancel.assert_called_once()
            debug.log('COMPLETE sentiment page')
            self.assertIsNone(debug._timer)
            self.assertEqual(timer.call_count, 2)
        progress.assert_called_with('COMPLETE sentiment page')

    def test_stall_reports_only_active_callers_stack(self):
        output = io.StringIO()
        debug = SentimentDebug(enabled=True)
        with redirect_stdout(output):
            debug._report_stall(debug._generation, 'chart step')
        self.assertIn('SLOW:', output.getvalue())
        self.assertIn('test_stall_reports_only_active_callers_stack', output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            debug._report_stall(debug._generation - 1, 'cancelled step')
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
