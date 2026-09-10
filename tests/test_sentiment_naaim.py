"""Regression coverage for NAAIM's delayed public table."""
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

from sentiment import sentiment_data as sentiment


class NaaimTests(unittest.TestCase):
    def fetch(self, html, cached=None, fresh=False, error=None):
        response = Mock(text=html)
        response.raise_for_status.side_effect = error
        with patch.object(sentiment, "_cache_get", return_value=(cached, fresh)), \
             patch.object(sentiment.requests, "get", return_value=response) as get, \
             patch.object(sentiment, "_cache_put", side_effect=lambda name, df: df) as put:
            result = sentiment.fetch_naaim()
        return result, get, put

    def test_public_table_and_cached_history(self):
        raw = pd.DataFrame({
            "Date": ["06/10/2026", "06/03/2026", "06/03/2026", "invalid"],
            "NAAIM Number": [79.27, 86.82, 0, 50],
            "Quarter 1": [75, 85.75, 0, 0],
            "Quarter 2": [90, 95, 0, 0],
            "Quarter 3": [100, 103.75, 0, 0],
        })
        cached = pd.DataFrame({
            "date": pd.to_datetime(["2020-01-01", "2026-06-03"]),
            "exposure": [50, 80], "q1": [25, 70],
            "median": [50, 80], "q3": [75, 90],
        })
        result, get, put = self.fetch(raw.to_html(index=False), cached)
        self.assertEqual(result.exposure.tolist(), [50, 86.82, 79.27])
        self.assertEqual(result.q1.tolist(), [25, 85.75, 75])
        self.assertTrue(result.date.is_monotonic_increasing)
        self.assertEqual(get.call_args.args[0], sentiment.NAAIM_TABLE_URL)
        put.assert_called_once()

    def test_fresh_cache_skips_network(self):
        cached = pd.DataFrame({"exposure": [50]})
        result, get, put = self.fetch("", cached, fresh=True)
        self.assertIs(result, cached)
        get.assert_not_called()
        put.assert_not_called()

    def test_failed_refresh_preserves_cache(self):
        cached = pd.DataFrame({"exposure": [50]})
        for error in (None, requests.HTTPError("unavailable")):
            with self.subTest(error=error):
                result, _, put = self.fetch("<html>No table</html>", cached, error=error)
                self.assertIs(result, cached)
                put.assert_not_called()

    def test_missing_table_without_cache_raises(self):
        with self.assertRaises(ValueError):
            self.fetch("<html>No table</html>")


if __name__ == "__main__":
    unittest.main()
