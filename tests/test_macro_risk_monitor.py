"""Risk-monitor regressions: disagreement, sparse data and legacy report inputs."""
import unittest

import pandas as pd

from macro.risk_monitor import (
    build_risk_monitor, get_vix_regime, parse_risk_inputs, volatility_snapshot,
)


class RiskMonitorTests(unittest.TestCase):
    def healthy(self, **changes):
        data = dict(vix=16, vvix=80, vix_vvix=0.2, vix_vix3m=0.9,
                    xly_xlp_chg_63d=3, rspd_rsps_chg_63d=2,
                    risk_ratio_chg_10d=4, cyc_iwm_spx_chg_63d=6,
                    ad_divergence='CONFIRMING — breadth and price both RISING', hy_spread=3)
        data.update(changes)
        return data

    def test_broad_support_is_risk_on(self):
        result = build_risk_monitor(self.healthy())
        self.assertEqual(result['regime'], 'RISK ON')
        self.assertEqual(result['available'], 5)

    def test_calm_vix_cannot_override_defensive_rotation(self):
        result = build_risk_monitor(self.healthy(xly_xlp_chg_63d=-6,
                                                rspd_rsps_chg_63d=-7,
                                                risk_ratio_chg_10d=-4))
        self.assertEqual(result['regime'], 'RISK OFF')
        self.assertEqual(result['risk_off'], 2)

    def test_consumer_ratios_share_one_vote(self):
        result = build_risk_monitor(self.healthy(xly_xlp_chg_63d=-6, rspd_rsps_chg_63d=-7))
        self.assertEqual(result['risk_off'], 1)
        self.assertEqual(result['regime'], 'CAUTIOUS')

    def test_consumer_disagreement_means_caution(self):
        result = build_risk_monitor(self.healthy(xly_xlp_chg_63d=-6))
        self.assertEqual(result['groups'][1]['status'], 'CAUTION')
        self.assertEqual(result['regime'], 'CAUTIOUS')

    def test_weakening_is_not_coloured_supportive(self):
        result = build_risk_monitor(self.healthy(xly_xlp_chg_63d=-0.1))
        self.assertEqual(next(r for r in result['rows'] if r['key'] == 'xly_xlp_chg_63d')['status'], 'CAUTION')
        self.assertEqual(result['regime'], 'CAUTIOUS')

    def test_confirming_falling_breadth_is_defensive(self):
        result = build_risk_monitor(self.healthy(
            cyc_iwm_spx_chg_63d=0,
            ad_divergence='CONFIRMING — breadth and price both FALLING'))
        self.assertEqual(result['groups'][3]['status'], 'RISK OFF')
        self.assertEqual(result['regime'], 'CAUTIOUS')

    def test_complacency_and_term_inversion_block_risk_on(self):
        for changes in (dict(vix=14, vix_vvix=0.16), dict(vix=19, vix_vvix=0.16),
                        dict(vix_vix3m=1)):
            with self.subTest(changes=changes):
                self.assertEqual(build_risk_monitor(self.healthy(**changes))['regime'], 'CAUTIOUS')

    def test_stress_overrides_even_when_other_groups_missing(self):
        for data in ({'vix': 26}, {'hy_spread': 6}):
            with self.subTest(data=data):
                self.assertEqual(build_risk_monitor(data)['regime'], 'RISK OFF')

    def test_missing_and_nonfinite_data_never_vote_supportive(self):
        result = build_risk_monitor(dict(vix=float('nan'), hy_spread=float('inf'),
                                        xly_xlp_chg_63d=None, risk_ratio_chg_10d='bad'))
        self.assertEqual(result['regime'], 'INSUFFICIENT DATA')
        self.assertEqual(result['available'], 0)
        self.assertTrue(all(r['status'] == 'UNAVAILABLE' for r in result['rows']))

    def test_calm_vix_alone_is_insufficient(self):
        result = build_risk_monitor({'vix': 14})
        self.assertEqual(result['regime'], 'INSUFFICIENT DATA')
        self.assertEqual(result['available_signals'], 1)

    def test_zero_changes_are_neutral(self):
        result = build_risk_monitor(self.healthy(xly_xlp_chg_63d=0, rspd_rsps_chg_63d=0,
                                                risk_ratio_chg_10d=0, cyc_iwm_spx_chg_63d=0,
                                                ad_divergence=None))
        self.assertEqual(result['regime'], 'MIXED')

    def test_boundary_levels(self):
        for vix, expected in ((19.99, 'RISK ON'), (20, 'CAUTIOUS'), (25, 'CAUTIOUS'), (25.01, 'RISK OFF')):
            with self.subTest(vix=vix):
                self.assertEqual(build_risk_monitor(self.healthy(vix=vix))['regime'], expected)
        self.assertEqual(build_risk_monitor(self.healthy(hy_spread=4))['regime'], 'CAUTIOUS')
        self.assertEqual(build_risk_monitor(self.healthy(hy_spread=6))['regime'], 'RISK OFF')

    def test_volatility_labels_have_no_fallthrough_and_no_buy_signal(self):
        for vix in (0, 14, 15, 17, 19, 20, 25, 26, None, float('nan')):
            for ratio in (0.16, 0.17, 0.18, 0.26, None):
                with self.subTest(vix=vix, ratio=ratio):
                    label, context, _ = get_vix_regime(vix, None, ratio)
                    self.assertTrue(label and context)
                    self.assertNotIn('OPPORTUNITY', label)
                    self.assertNotIn('RISK ON', label)

    def test_legacy_report_preserves_negative_and_zero_trends(self):
        text = '''VIX: 16.00 VVIX: 100.00 VIX/VVIX: 0.1600
XLY/XLP ratio: 1.23 ▼2.50% 5d ▼6.25% 63d ⚠ RISK OFF
RSPD/RSPS ratio: 1.45 ▲0.00% 5d ▼1.25% 63d → WEAKENING
Sector Groups Risk On/Off ratio: 1.6 ▼0.50% 5d ▼3.50% 10d ⚠ RISK OFF
HY Spread: 3.25%
A/D Line: ⚠ BEARISH — breadth deteriorating while price rises
'''
        data = parse_risk_inputs(text)
        self.assertEqual(data['xly_xlp_chg_63d'], -6.25)
        self.assertEqual(data['rspd_rsps_chg_5d'], 0)
        self.assertEqual(data['risk_ratio_chg_10d'], -3.5)
        self.assertEqual(build_risk_monitor(data)['regime'], 'RISK OFF')

    def test_snapshot_numbers_and_nulls_take_precedence(self):
        data = parse_risk_inputs('VIX: 14 VVIX: 80 VIX/VVIX: 0.1750',
                                 {'vix': 26.1234, 'vvix': None, 'vix_vvix': None})
        self.assertEqual(data['vix'], 26.1234)
        self.assertIsNone(data['vvix'])
        self.assertIsNone(data['vix_vvix'])

    def test_volatility_comparisons_do_not_mix_sessions(self):
        vix = pd.Series([15, 16], index=pd.to_datetime(['2026-10-22', '2026-10-23']))
        vvix = pd.Series([80], index=pd.to_datetime(['2026-10-22']))
        term = pd.DataFrame({'Close': [20]}, index=pd.to_datetime(['2026-10-23']))
        data = volatility_snapshot(vix, vvix, term)
        self.assertEqual(data['vix_as_of'], '2026-10-23')
        self.assertIsNone(data['vvix'])
        self.assertIsNone(data['vix_vvix'])
        self.assertEqual(data['vix_vix3m'], 0.8)

    def test_empty_volatility_history_is_unavailable(self):
        data = volatility_snapshot(pd.DataFrame(), None, pd.Series(dtype=float))
        self.assertTrue(all(value is None for value in data.values()))


if __name__ == '__main__':
    unittest.main()
