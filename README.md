# Market Intelligence Platform

A local market intelligence dashboard for tracking relative strength, breadth and macro conditions across AU/US equities and commodities.

Provides actionable reports for screeners and trading view watchlist to easily import them into tradingview.

Drawdown Analysis Tool:
Choose up to 3 priods of time to conduct a drawdown analysis and relative strength comparison on all of the existing watchlist.  AU/US stocks, major commodities, AU gold mining, Uranium.

RRG Relative Rotation Graphs - relative strength vs relative momentum with adjustable tails up to 63 trading days.  Separate graphs for AU and US sectors.  Useful for monitoring rotation across all sectors and major metals.

Additional tools:
Metatrader 5 Expert Advisor set file comparison tool.
Metatrader 5 trade export html report viewer + filters.

## Requirements
- Python 3.10+
- See `requirements.txt` for all dependencies

## Installation

1. Clone the repo
2. Create and activate a virtual environment:

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac

3. Install dependencies:
pip install -r requirements.txt

4. Set up FRED API key:
   - Copy `macro/config_template.py` to `macro/config.py`
   - Add your FRED API key (free at fred.stlouisfed.org)

## Launch
streamlit run dashboard.py

## Full Documentation
See `Market_Intelligence_Platform_Guide_v1.4.docx` in "docs" folder for complete installation, usage and technical reference.

Upload to your own AI to allow it to understand how all scripts work and calculations to allow for modification/additions.

## Dashboard Pages
- **Macro** — VIX regime, live market readings, macro cycle positioning
- **AU/US Market** — breadth, benchmark RS, sector peer screener
- **Commodities** — gold, silver, copper, uranium, lithium, platinum, palladium
- **Uranium / AU Gold Miners** — dedicated universe screens
- **RRG Charts** — relative rotation graphs with downloadable PNG
- **Breadth RRG** — sector breadth participation rotation graph (Ab20/50/200)
- **DeMark Signals** — TD Setup 9 and Countdown 13 scanner, daily and weekly, US market
- **Drawdown Analysis** — period-based performance analysis vs benchmark and peers
- **Actionable & Exports** — filtered lists with TradingView import
- **EA Comparator** — MetaTrader .set file comparison and export
- **MT5 Analysis** — trade history analysis from MT5 HTML reports
- **Run Scripts** — trigger data collection scripts from the dashboard
- **Settings** — toggle pages on/off