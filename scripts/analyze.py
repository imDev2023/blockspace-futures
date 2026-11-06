"""Analyse sampled Solana blocks: fee spend, per-program fee swings, and a
backtest of a fixed-fee lane.

Reads research/data/blocks/*.jsonl.gz written by collect_blocks.py and writes
research/data/summary.json plus the tables printed to stdout.

Definitions
- landing cost of a transaction = priority fee + Jito tip, in lamports
  (the 5,000-lamport base fee per signature is fixed, so it is left out)
- a transaction's program = the first top-level program that is not a
  utility program (System, Token, Associated Token, Memo, Compute Budget)
- block median cost for a program = median landing cost of that program's
  transactions in one sampled block; used as "what it cost to land a typical
  transaction on that program at that moment"
"""

import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKS = ROOT / "research" / "data" / "blocks"
OUT = ROOT / "research" / "data" / "summary.json"

LAMPORTS_PER_SOL = 1_000_000_000
SLOTS_PER_DAY = 86400 / 0.214

UTILITY = {
    "11111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
    "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo",
    "ComputeBudget111111111111111111111111111111",
}

NAMES = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump.fun",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "PumpSwap",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "Meteora DAMM v2",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora DAMM v1",
    "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": "Meteora DBC",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "Raydium LaunchLab",
    "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH": "Drift v2",
    "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": "Phoenix",
    "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe": "SolFi",
    "obriQD1zbpyLz95G5n7nJe6a4DPjpFwa5XYPoNm113y": "Obric v2",
    "ZERor4xhbUycZ6gb9ntrhqscUcZmAbQDjEAtCf4hbZY": "ZeroFi",
    "9H6tua7jkLhdm3w8BvgpTn5LZNU7g4ZynDmCiNN3q6Rp": "HumidiFi",
    "TessVdML9pBGgG9yGks7o4HewRaXVAMuoVj4x83GLQH": "Tessera V",
    "goonERTdGsjnkZqWuVjs73BZ3Pb9qoCUdBUL17BnS5j": "GoonFi",
    "pythWSnswVUd12oZpeFP8e9CVaEqJg25g1Vtc2biRsT": "Pyth push oracle",
    "rec5EKMGg6MxZYaMdyBfgwp4d5rB9T1VQH5pJv5LtFJ": "Pyth receiver",
    "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD": "Kamino Lend",
    "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA": "marginfi",
    "SBondMDrcV3K4kxZR1HNVT7osZxAHVHgYXL5Ze1oMUv": "Switchboard",
    "SW1TCH7qEPTdLsDHRgPuMQjbQxKdH2aBStViMFnt64f": "Switchboard on-demand",
    "BSfD6SHZigAfDWSjzD5Q41jw8LmKwtmjskPH9XW1mrRW": "Photon (bot)",
    "AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzMpgbMG6": "Axiom",
    "AxiomxSitiyXyPjKgJ9XSrdhsydtZsskZTEDam3PxKcC": "Axiom",
    "DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH": "DFlow aggregator",
    "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95": "Lighthouse (wallet guard)",
    "transfers": "plain transfers",
}


def name(p):
    return NAMES.get(p, p[:6] + "..")


def pct(xs, q):
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def load():
    blocks = []
    for f in sorted(BLOCKS.glob("*.jsonl.gz")):
        with gzip.open(f, "rt") as fh:
            head = json.loads(fh.readline())
            rows = [json.loads(l) for l in fh]
        blocks.append((head, rows))
    return blocks


def primary_program(r):
    for p in r["p"]:
        if p not in UTILITY:
            return p
    return "transfers"


def main():
    sol_usd = float(sys.argv[1]) if len(sys.argv) > 1 else 89.18
    blocks = load()
    grid = [(h, rows) for h, rows in blocks if h["kind"] == "grid"]
    bursts = defaultdict(list)
    for h, rows in blocks:
        if h["kind"].startswith("burst:"):
            bursts[h["kind"]].append((h, rows))
    if not grid:
        print("no grid blocks yet")
        return
    t_min = min(h["t"] for h, _ in grid)
    t_max = max(h["t"] for h, _ in grid)

    # 1. Network-wide spend
    prio_per_block = [sum(r["prio"] for r in rows) for _, rows in grid]
    tip_per_block = [sum(r["tip"] for r in rows) for _, rows in grid]
    tx_per_block = [len(rows) for _, rows in grid]
    avg_prio = statistics.mean(prio_per_block)
    avg_tip = statistics.mean(tip_per_block)
    daily_prio_sol = avg_prio * SLOTS_PER_DAY / LAMPORTS_PER_SOL
    daily_tip_sol = avg_tip * SLOTS_PER_DAY / LAMPORTS_PER_SOL
    network = {
        "grid_blocks": len(grid),
        "burst_runs": len(bursts),
        "from": t_min,
        "to": t_max,
        "avg_txs_per_block": statistics.mean(tx_per_block),
        "daily_priority_fees_sol": daily_prio_sol,
        "daily_jito_tips_sol": daily_tip_sol,
        "daily_total_usd": (daily_prio_sol + daily_tip_sol) * sol_usd,
        "sol_usd": sol_usd,
        "share_tx_paying_priority": sum(sum(1 for r in rows if r["prio"] > 0) for _, rows in grid) / max(1, sum(tx_per_block)),
        "share_tx_tipping": sum(sum(1 for r in rows if r["tip"] > 0) for _, rows in grid) / max(1, sum(tx_per_block)),
    }

    # 2. Per program spend and swings (grid samples)
    spend = defaultdict(int)
    count = defaultdict(int)
    payers = defaultdict(set)
    block_median = defaultdict(list)  # program -> [(t, median cost, n)]
    for h, rows in grid:
        per = defaultdict(list)
        for r in rows:
            p = primary_program(r)
            c = r["prio"] + r["tip"]
            spend[p] += c
            count[p] += 1
            payers[p].add(r["payer"])
            per[p].append(c)
        for p, cs in per.items():
            block_median[p].append((h["t"], statistics.median(cs), len(cs)))

    top = sorted(spend, key=lambda p: -spend[p])[:20]
    hourly_tx = defaultdict(lambda: defaultdict(list))  # program -> hour -> costs
    for h, rows in grid:
        for r in rows:
            hourly_tx[primary_program(r)][h["t"] // 3600].append(r["prio"] + r["tip"])
    total_spend = sum(spend.values())
    programs = []
    for p in top:
        meds = [m for _, m, _ in block_median[p]]
        hourly_med = [statistics.median(v) for v in hourly_tx[p].values() if len(v) >= 5]
        p10, p50, p90, p99 = (pct(meds, q) for q in (0.10, 0.50, 0.90, 0.99))
        programs.append({
            "program": p,
            "name": name(p),
            "share_of_spend": spend[p] / total_spend,
            "daily_spend_sol": spend[p] / len(grid) * SLOTS_PER_DAY / LAMPORTS_PER_SOL,
            "txs_sampled": count[p],
            "unique_payers": len(payers[p]),
            "blocks_seen": len(meds),
            "median_cost_lamports": p50,
            "p10": p10,
            "p90": p90,
            "p99": p99,
            "max": max(meds),
            "p90_over_p10": (p90 / p10) if p10 > 0 else None,
            "hourly_max_over_min": (max(hourly_med) / min(hourly_med)) if hourly_med and min(hourly_med) > 0 else None,
            "hourly_p90_over_p10": (pct(hourly_med, 0.9) / pct(hourly_med, 0.1)) if hourly_med and pct(hourly_med, 0.1) > 0 else None,
            "hours": len(hourly_med),
        })

    # 3. Block-to-block swings inside burst runs, for the top programs
    burst_swing = {}
    for p in top[:10]:
        changes = []
        for runs in bursts.values():
            runs.sort(key=lambda x: x[0]["slot"])
            prev = None
            for h, rows in runs:
                cs = [r["prio"] + r["tip"] for r in rows if primary_program(r) == p]
                cur = statistics.median(cs) if cs else None
                if prev and cur and prev > 0 and cur > 0:
                    changes.append(abs(math.log(cur / prev)))
                prev = cur
        if changes:
            burst_swing[p] = {
                "name": name(p),
                "pairs": len(changes),
                "median_abs_change_x": math.exp(statistics.median(changes)),
                "p90_abs_change_x": math.exp(pct(changes, 0.9)),
            }

    # 4. Backtest: fixed-fee lane per program, in three service tiers.
    # A tier is a percentile q of the landing costs paid in an hour:
    # standard (q=50) pays what a typical user paid, fast (q=75) beats three in
    # four competitors, priority (q=90) beats nine in ten. Every sampled
    # transaction of the program is pooled by hour; the realised cost of an
    # hour is that hour's q-percentile. The quote is fixed in advance:
    # margin x p75 of the previous 24 hourly q-percentiles. Revenue per
    # transaction = quote - realised cost, weighted by the hour's sampled count.
    TIERS = {"standard": 0.5, "fast": 0.75, "priority": 0.9}
    backtests = {}
    for p in top[:10]:
        hours = sorted(hourly_tx[p])
        cnt = {hr: len(cs) for hr, cs in hourly_tx[p].items()}
        for tier, q in TIERS.items():
            level = {hr: pct(cs, q) for hr, cs in hourly_tx[p].items()}
            for margin in (1.0, 1.1, 1.25):
                pnl = billed = cost = 0.0
                hour_pnl = {}
                n_tx = 0
                overpaid = 0  # sampled txs whose own spend exceeded the quote
                spot_spend = 0.0  # what those txs actually paid
                for hr in hours:
                    window = [level[x] for x in hours if hr - 24 <= x < hr]
                    if len(window) < 20:
                        continue
                    quote = margin * pct(window, 0.75)
                    realised, n = level[hr], cnt[hr]
                    pnl += (quote - realised) * n
                    billed += quote * n
                    cost += realised * n
                    hour_pnl[hr] = (quote - realised) * n
                    n_tx += n
                    overpaid += sum(1 for c in hourly_tx[p][hr] if c > quote)
                    spot_spend += sum(hourly_tx[p][hr])
                if not n_tx:
                    continue
                losing = [v for v in hour_pnl.values() if v < 0]
                backtests.setdefault(p, {"name": name(p)})[f"{tier} x{margin}"] = {
                    "tier_percentile": q,
                    "margin": margin,
                    "txs": n_tx,
                    "gross_margin_pct": 100 * pnl / billed if billed else None,
                    "avg_quote_lamports": billed / n_tx,
                    "avg_cost_lamports": cost / n_tx,
                    "profit_per_tx_lamports": pnl / n_tx,
                    "spot_mean_lamports": spot_spend / n_tx,
                    "share_txs_paid_more_than_quote": overpaid / n_tx,
                    "daily_txs": count[p] / len(grid) * SLOTS_PER_DAY,
                    "daily_profit_usd_if_all_flow": pnl / n_tx * count[p] / len(grid) * SLOTS_PER_DAY / LAMPORTS_PER_SOL * sol_usd,
                    "hours": len(hour_pnl),
                    "losing_hours": len(losing),
                    "worst_hour_vs_avg_hour": (min(hour_pnl.values()) / (pnl / len(hour_pnl))) if pnl else None,
                }

    summary = {"network": network, "programs": programs, "burst_swing": burst_swing, "backtests": backtests}
    OUT.write_text(json.dumps(summary, indent=2))

    # Print
    from datetime import datetime, timezone
    fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(f"window {fmt(t_min)} to {fmt(t_max)} UTC, {len(grid)} grid blocks, {len(bursts)} burst runs")
    n = network
    print(f"avg {n['avg_txs_per_block']:.0f} non-vote txs/block; {100*n['share_tx_paying_priority']:.0f}% pay priority, {100*n['share_tx_tipping']:.1f}% tip Jito")
    print(f"daily priority fees {n['daily_priority_fees_sol']:.0f} SOL, Jito tips {n['daily_jito_tips_sol']:.0f} SOL, total ${n['daily_total_usd']:,.0f}/day at ${sol_usd}")
    print()
    print("program | share | SOL/day | txs | payers | median | p10 | p90 | p99 | p90/p10 | hourly max/min")
    for r in programs:
        f = lambda x: f"{x:,.0f}"
        r9 = f"{r['p90_over_p10']:.0f}x" if r["p90_over_p10"] else "-"
        rh = f"{r['hourly_max_over_min']:.0f}x" if r["hourly_max_over_min"] else "-"
        print(f"{r['name']} | {100*r['share_of_spend']:.1f}% | {r['daily_spend_sol']:.1f} | {r['txs_sampled']} | {r['unique_payers']} | {f(r['median_cost_lamports'])} | {f(r['p10'])} | {f(r['p90'])} | {f(r['p99'])} | {r9} | {rh}")
    print()
    print("block-to-block (burst runs): median and p90 change factor")
    for p, b in burst_swing.items():
        print(f"{b['name']} | pairs {b['pairs']} | median {b['median_abs_change_x']:.2f}x | p90 {b['p90_abs_change_x']:.1f}x")
    print()
    print("fixed-fee lane backtest (tier q: cost = hour's q-percentile, quote = margin x trailing-24h p75 of hourly q-percentiles)")
    for p, b in backtests.items():
        for k, v in b.items():
            if k == "name":
                continue
            gm = f"{v['gross_margin_pct']:.0f}%" if v["gross_margin_pct"] is not None else "-"
            print(f"{b['name']} {k} | gross margin {gm} | quote {v['avg_quote_lamports']:,.0f} vs cost {v['avg_cost_lamports']:,.0f} (spot mean {v['spot_mean_lamports']:,.0f}) | paid more than quote {100*v['share_txs_paid_more_than_quote']:.0f}% | losing hours {v['losing_hours']}/{v['hours']} | ${v['daily_profit_usd_if_all_flow']:,.0f}/day if all flow")


if __name__ == "__main__":
    main()
