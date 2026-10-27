# Macro risk monitor

The Macro page and daily macro report use `macro/risk_monitor.py` for a shared
market-risk reading. VIX describes volatility; consumer leadership and other
groups supply confirmation. The report saves its numeric inputs alongside its
text so the page does not combine a report with an unrelated latest snapshot.
Legacy reports use the snapshot for their report date, with text as a fallback.

| Group | Inputs | Warning rules |
|---|---|---|
| Volatility | VIX, VIX/VVIX, VIX/VIX3M | VIX 20–25: caution; >25: stress override. With VIX <20, VIX/VVIX <0.18: caution (<0.17: complacency). VIX/VIX3M >=1: flat/inverted term structure warning. |
| Consumer leadership | XLY/XLP and equal-weight RSPD/RSPS, 63d change | Positive: supportive; zero: neutral; negative: caution; below -5%: risk off. Both ratios share one group vote. |
| Sector rotation | Existing sector risk-on/risk-off basket ratio, 10d change | Above +3%: supportive; -3% through negative values: caution; below -3%: risk off; zero through +3%: neutral. |
| Participation | IWM/SPX 63d change and stored internal breadth divergence | Small caps above +5%: supportive; negative: caution; below -5%: risk off. Bearish divergence or breadth and price both falling: risk off. Bullish divergence or both rising: supportive. |
| Credit | HY option-adjusted spread level, percent | Below 4%: supportive; 4% to below 6%: caution; >=6%: stress override. This measures level, not spread velocity. |

Conflicting supportive and risk-off inputs within a group produce caution.
Otherwise risk off takes precedence over caution, then supportive, then neutral.
Unavailable inputs do not vote. Coverage shows groups with at least one usable
input; the detailed panel also reports individual input coverage.

The headline applies these rules in order:

1. VIX >25, HY spread >=6%, or two risk-off groups: **RISK OFF**.
2. Fewer than three available groups: **INSUFFICIENT DATA**.
3. Any risk-off or caution group: **CAUTIOUS**.
4. At least three supportive groups, including volatility and consumer leadership,
   with no warnings: **RISK ON**.
5. Otherwise: **MIXED**.

VIX, VVIX and VIX3M comparisons use closes from the same session, without filling
missing closes from an earlier session. Older snapshots do not contain the term
structure input; run Macro Report to collect it. The page displays the report date
and flags reports older than a week. Different signal groups retain their original
daily or published-data cadence; these are report readings, not live quotes.

The breadth input is the existing leader-minus-laggard/weak proxy, not exchange
advance/decline data. The sector basket retains the existing nominal-price sum
`(XLK+XLC+XLY)/(XLU+XLP+XLV)`; it is not an equal-weight sector return index.
Thresholds and group votes are descriptive application heuristics, not calibrated
probabilities, recession diagnoses, or a backtested trading strategy.

Cboe defines [VIX as expected near-term volatility](https://www.cboe.com/tradable-products/vix/),
[VVIX as volatility of volatility](https://www.cboe.com/us/indices/dashboard/VVIX),
and [VIX3M as a three-month volatility gauge](https://www.cboe.com/tradable-products/vix/term-structure).
These definitions support the distinction between volatility context and broader
risk confirmation; they do not validate the application's threshold choices.

Validation: `python -m unittest discover -s tests -p test_macro_risk_monitor.py -v`.
