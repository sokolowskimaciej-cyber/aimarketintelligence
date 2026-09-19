"""
Export MT5 account performance to data/performance.json for aimarketintelligence.co.uk.

Setup (once, on the PC/VPS where MetaTrader 5 is installed and logged in):
    pip install MetaTrader5

Run manually:
    python tools/export_performance.py            # writes data/performance.json
    python tools/export_performance.py --push     # also commits & pushes to GitHub

Schedule (Windows Task Scheduler): run tools/run_export.bat hourly or daily.

All figures are percentages of account equity - no money amounts are published.
"""
import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("MetaTrader5 package missing - run: pip install MetaTrader5")

SITE_DIR = Path(__file__).resolve().parents[1]
OUT_FILE = SITE_DIR / "data" / "performance.json"
TERMINAL = r"C:\Fusion Markets MetaTrader 5\terminal64.exe"  # which MT5 install to read
TRACK_SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)  # live tracking starts here
TRADES_WINDOW_DAYS = 30
TRADES_MAX = 12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="git commit + push after export")
    args = ap.parse_args()

    # Attach to the running terminal first; fall back to launching the Fusion install
    if not mt5.initialize(timeout=60000) and not mt5.initialize(path=TERMINAL, timeout=90000):
        sys.exit(f"MT5 initialize failed: {mt5.last_error()}")

    acc = mt5.account_info()
    deals = mt5.history_deals_get(TRACK_SINCE, datetime.now(timezone.utc) + timedelta(days=1))
    mt5.shutdown()
    if acc is None or deals is None:
        sys.exit("Could not read account info / deal history from MT5")

    # Closed-trade P&L per deal (exits only), oldest first
    closed = [d for d in deals if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT, mt5.DEAL_ENTRY_OUT_BY)]
    closed.sort(key=lambda d: d.time)
    pnl = lambda d: d.profit + d.swap + d.commission

    total_pnl = sum(pnl(d) for d in closed)
    start_balance = acc.balance - total_pnl
    if start_balance <= 0:
        sys.exit("Derived starting balance is not positive - set TRACK_SINCE after your last deposit")

    # Daily equity curve, normalised to 100 at start
    daily = {}
    bal = start_balance
    for d in closed:
        bal += pnl(d)
        day = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d")
        daily[day] = round(bal / start_balance * 100, 2)
    equity = [[TRACK_SINCE.strftime("%Y-%m-%d"), 100.0]] + sorted(daily.items())

    # Stats
    values = [v for _, v in equity]
    peak, max_dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        max_dd = min(max_dd, (v - peak) / peak * 100)
    wins = [d for d in closed if pnl(d) > 0]
    gross_win = sum(pnl(d) for d in wins)
    gross_loss = -sum(pnl(d) for d in closed if pnl(d) < 0)
    stats = {
        "totalReturnPct": round((values[-1] - 100), 1),
        "maxDrawdownPct": round(max_dd, 1),
        "winRatePct": round(len(wins) / len(closed) * 100) if closed else 0,
        "profitFactor": round(gross_win / gross_loss, 2) if gross_loss > 0 else 0,
        "trades": len(closed),
    }

    # Monthly returns from the daily curve
    month_last = {}
    for day, v in sorted(daily.items()):
        month_last[day[:7]] = v
    monthly, prev = [], 100.0
    for ym in sorted(month_last):
        monthly.append([ym, round((month_last[ym] / prev - 1) * 100, 1)])
        prev = month_last[ym]

    # Closed trades in the last 30 days, as % of equity at the time
    cutoff = datetime.now(timezone.utc) - timedelta(days=TRADES_WINDOW_DAYS)
    recent = []
    bal = start_balance
    rows = []
    for d in closed:
        rows.append((d, bal))
        bal += pnl(d)
    for d, bal_before in rows[::-1]:
        if datetime.fromtimestamp(d.time, tz=timezone.utc) < cutoff or len(recent) >= TRADES_MAX:
            break
        side = "Sell" if d.type == mt5.DEAL_TYPE_SELL else "Buy"
        recent.append([
            datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d"),
            d.symbol, side, round(pnl(d) / bal_before * 100, 2),
        ])

    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start": TRACK_SINCE.strftime("%Y-%m-%d"),
        "equity": equity,
        "stats": stats,
        "monthly": monthly,
        "trades": recent,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT_FILE}: {stats}")

    if args.push:
        run = lambda *c: subprocess.run(c, cwd=SITE_DIR, check=True)
        run("git", "add", "data/performance.json")
        if subprocess.run(("git", "diff", "--cached", "--quiet"), cwd=SITE_DIR).returncode:
            run("git", "commit", "-m", "Update performance data")
            run("git", "push")
            print("Pushed to GitHub - site updates in ~1 minute")
        else:
            print("No changes to push")


if __name__ == "__main__":
    main()
