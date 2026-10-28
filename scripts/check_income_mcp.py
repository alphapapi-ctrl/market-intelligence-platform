"""Read-only deployment acceptance check against the existing Market Intelligence service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_mcp.version import VERSION, code_version


def verify(url, expected_root=None, expected_database=None):
    base = url.rstrip('/').removesuffix('/mcp')
    opener = build_opener(ProxyHandler({}))
    def get(path):
        with opener.open(base + path, timeout=10) as response:
            return json.load(response)
    counter = 0
    def rpc(method, params):
        nonlocal counter
        counter += 1
        request = Request(base + '/mcp', method='POST', data=json.dumps({
            'jsonrpc': '2.0', 'id': counter, 'method': method, 'params': params}).encode(),
            headers={'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'})
        with opener.open(request, timeout=30) as response:
            data = json.load(response)
        if data.get('error') or data.get('result', {}).get('isError'):
            raise RuntimeError(json.dumps(data))
        return data['result']
    def call(name, arguments):
        result = rpc('tools/call', {'name': name, 'arguments': arguments})
        return json.loads(next(item['text'] for item in result['content'] if item['type'] == 'text'))
    health = get('/health')
    if health.get('service') != 'market-intelligence-mcp' or health.get('version') != VERSION:
        raise ValueError(f"Expected Market Intelligence {VERSION}; running health is {health}")
    if health.get('source_sha256') != code_version()['source_sha256']:
        raise ValueError('Running source fingerprint differs from this checkout; restart the existing MCP task after updating all files')
    if not health.get('database_exists'):
        raise ValueError('Expected existing market database is missing')
    for key, expected in [('app_root', expected_root), ('database', expected_database)]:
        if expected and str(health.get(key, '')).casefold().rstrip('\\/') != str(expected).casefold().rstrip('\\/'):
            raise ValueError(f"Unexpected {key}: {health.get(key)}")
    handshake = rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
        'clientInfo': {'name': 'income-deployment-check', 'version': VERSION}})
    listed = rpc('tools/list', {})['tools']
    names = {tool['name'] for tool in listed}
    needed = {'etf_income_config', 'read_etf_income_results', 'preview_etf_income_review',
              'read_etf_income_review', 'start_etf_income_review', 'read_screener', 'read_prices', 'market_catalog'}
    if not needed <= names or len(names) != 24:
        raise ValueError(f'Incomplete tool discovery: {sorted(names)}')
    cfg = call('etf_income_config', {})
    results = call('read_etf_income_results', {'limit': 1})
    catalog = call('market_catalog', {})
    stock = call('read_screener', {'universe': 'au_total_market', 'limit': 1})
    if cfg['code_version']['source_sha256'] != health['source_sha256']:
        raise ValueError('Configuration tool and health refer to different source versions')
    return {'deployed_and_read_verified': True, 'service_version': health['version'],
        'source_sha256': health['source_sha256'], 'app_root': health['app_root'], 'database': health['database'],
        'protocol_server': handshake['serverInfo'], 'tool_count': len(names),
        'income_schema': cfg['schema_version'], 'income_frame': results['source']['frame'],
        'income_rows': results['total_rows'], 'income_warnings': results['warnings'],
        'saved_backtest_cadence': cfg['cadence']['saved_backtest_rebalance_cadence'],
        'user_full_rebalance_preference': cfg['cadence']['conversation_context']['full_rebalance_cadence'],
        'stock_screener_date': stock['run_date'], 'latest_price_date': catalog['latest_price_date'],
        'generation_or_portfolio_writes_performed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://mt5tools:8766')
    parser.add_argument('--expected-root')
    parser.add_argument('--expected-database')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.url, args.expected_root, args.expected_database), indent=2))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
