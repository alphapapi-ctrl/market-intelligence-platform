"""
stocks/asx_substantial_holders.py
=================================
Scrapes substantial holder notices (ASIC forms 603/604/605) from the ASX
daily announcements pages and accumulates them into a history CSV.

Forms:
    603 — Becoming a substantial holder      (accumulation signal)
    604 — Change in substantial holding      (adding or reducing)
    605 — Ceasing to be a substantial holder (distribution signal)

Runs on today's + previous trading day's announcements, dedupes by ASX
announcement id, so running daily builds a continuous record.

Usage:
    python stocks/asx_substantial_holders.py
"""

import os
import re
import json
import requests
import pandas as pd
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE, 'results', 'substantial_holders')
HISTORY_FILE = os.path.join(RESULTS_DIR, 'substantial_holders_history.csv')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}

URLS = [
    'https://www.asx.com.au/asx/v2/statistics/todayAnns.do',
    'https://www.asx.com.au/asx/v2/statistics/prevBusDayAnns.do',
]

# title -> form classification (order matters: check 'ceasing' before 'change')
FORM_MAP = [
    ('becoming a substantial holder', '603', 'BECOMING'),
    ('ceasing to be a substantial holder', '605', 'CEASING'),
    ('change in substantial holding', '604', 'CHANGE'),
]

ROW_RE = re.compile(
    r'<tr[^>]*>\s*<td>([A-Z0-9]{2,6})</td>\s*'                 # ticker
    r'<td>\s*(\d{2}/\d{2}/\d{4})<br>\s*'                       # date
    r'<span class="dates-time">([^<]*)</span>\s*</td>'         # time
    r'(.*?)'                                                   # middle (price-sensitive cell)
    r'href="(/asx/v2/statistics/displayAnnouncement\.do\?display=pdf&amp;idsId=(\d+))">\s*'
    r'([^<]+?)<br>',                                           # title
    re.DOTALL)


def classify(title):
    t = title.lower().strip()
    for needle, form, action in FORM_MAP:
        if needle in t:
            return form, action
    return None, None


def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  fetch error {url}: {e}")
        return ''


def parse_notices(html):
    rows = []
    for m in ROW_RE.finditer(html):
        ticker, date_s, time_s, middle, href, ids_id, title = m.groups()
        form, action = classify(title)
        if not form:
            continue
        price_sensitive = 'asterisk' in middle.lower() or '$' in middle
        try:
            dt = datetime.strptime(date_s, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            dt = date_s
        rows.append({
            'ann_id'   : ids_id,
            'date'     : dt,
            'time'     : time_s.strip(),
            'ticker'   : ticker,
            'form'     : form,
            'action'   : action,
            'title'    : title.strip(),
            'pdf_url'  : 'https://www.asx.com.au' + href.replace('&amp;', '&'),
        })
    return rows


def run():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    today = datetime.today().strftime('%Y%m%d')

    all_rows = []
    for url in URLS:
        label = 'today' if 'today' in url else 'previous day'
        print(f"Fetching {label} announcements...")
        html = fetch_page(url)
        rows = parse_notices(html)
        print(f"  {len(rows)} substantial holder notices")
        all_rows.extend(rows)

    if not all_rows:
        print("No notices found — page structure may have changed or no filings today")

    df_new = pd.DataFrame(all_rows)

    # merge into history, dedupe on announcement id
    if os.path.exists(HISTORY_FILE):
        hist = pd.read_csv(HISTORY_FILE, dtype={'ann_id': str})
        combined = pd.concat([hist, df_new], ignore_index=True)
    else:
        combined = df_new

    if not combined.empty:
        combined['ann_id'] = combined['ann_id'].astype(str)
        combined = (combined.drop_duplicates(subset='ann_id', keep='first')
                            .sort_values(['date', 'time'], ascending=False))
        combined.to_csv(HISTORY_FILE, index=False)

    # dated snapshot of what's new this run
    if not df_new.empty:
        snap_file = os.path.join(RESULTS_DIR, f"{today}_substantial_holders.csv")
        df_new.drop_duplicates(subset='ann_id').to_csv(snap_file, index=False)
        print(f"Saved: {snap_file}")

    n_hist = len(combined) if not combined.empty else 0
    print(f"History: {n_hist} notices total -> {HISTORY_FILE}")

    # summary by action
    if not df_new.empty:
        print("\nThis run:")
        for action, grp in df_new.drop_duplicates(subset='ann_id').groupby('action'):
            print(f"  {action:<8} ({grp.iloc[0]['form']}): {', '.join(sorted(grp['ticker'].unique()))}")

    return combined


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run()
