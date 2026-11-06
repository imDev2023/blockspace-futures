"""Sample Solana mainnet blocks and record what each transaction paid to land.

For every non-vote transaction in a sampled block it writes one JSON line:
slot, block time, signer count, total fee, priority fee (lamports), compute
unit limit and use, success, the top-level programs it called, and any Jito tip.

Sampling plan (default 7 days back from the newest finalized slot):
  - one block every --every-min minutes ("grid" samples)
  - every --burst-hours hours, --burst-len consecutive blocks ("burst" samples),
    to measure slot-to-slot swings

Output: research/data/blocks/<slot>.jsonl.gz, one file per block, so the run can
be stopped and resumed. Uses only the free public RPC unless --rpc is given.
"""

import argparse
import base64
import gzip
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
VOTE_PROGRAM = "Vote111111111111111111111111111111111111111"
BASE_FEE_PER_SIG = 5000
DEFAULT_CU_PER_IX = 200_000
MAX_CU = 1_400_000
JITO_TIP_ACCOUNTS = {
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
}

B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58_INDEX = {c: i for i, c in enumerate(B58_ALPHABET)}

SLOT_SECONDS_GUESS = 0.214


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58_INDEX[ch]
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


class Rpc:
    def __init__(self, url: str, min_interval: float):
        self.url = url
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last = 0.0

    def call(self, method, params, retries=8):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        delay = 2.0
        for attempt in range(retries):
            with self.lock:
                wait = self.last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self.last = time.monotonic()
            req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    time.sleep(float(retry_after) if retry_after else delay)
                    delay = min(delay * 2, 60)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if "error" in data:
                code = data["error"].get("code")
                # -32007 / -32009: slot skipped or missing; caller moves to next slot
                if code in (-32007, -32009, -32004):
                    return None
                if code in (-32005, -32014, -32016):  # node behind / not yet available
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue
                raise RuntimeError(f"{method} {params[:1]}: {data['error']}")
            return data["result"]
        raise RuntimeError(f"{method} {params[:1]}: gave up after {retries} tries")


def cu_limit_and_price(msg, keys, version):
    """Requested compute-unit limit for the transaction."""
    cfg = msg.get("transactionConfig")
    if cfg and cfg.get("computeUnitLimit") is not None:
        return int(cfg["computeUnitLimit"])
    limit = None
    non_budget_ix = 0
    for ix in msg["instructions"]:
        prog = keys[ix["programIdIndex"]]
        if prog != COMPUTE_BUDGET:
            non_budget_ix += 1
            continue
        try:
            data = b58decode(ix["data"])
        except KeyError:
            continue
        if data[:1] == b"\x02" and len(data) >= 5:
            limit = int.from_bytes(data[1:5], "little")
    if limit is None:
        limit = min(MAX_CU, DEFAULT_CU_PER_IX * max(non_budget_ix, 1))
    return limit


def parse_block(slot, block):
    out = []
    bt = block.get("blockTime")
    for tx in block.get("transactions", []):
        meta = tx.get("meta") or {}
        msg = tx["transaction"]["message"]
        loaded = meta.get("loadedAddresses") or {}
        keys = msg["accountKeys"] + loaded.get("writable", []) + loaded.get("readonly", [])
        programs = []
        for ix in msg["instructions"]:
            p = keys[ix["programIdIndex"]]
            if p != COMPUTE_BUDGET and p not in programs:
                programs.append(p)
        if programs == [VOTE_PROGRAM]:
            continue
        sigs = msg["header"]["numRequiredSignatures"]
        fee = int(meta.get("fee", 0))
        prio = max(0, fee - BASE_FEE_PER_SIG * sigs)
        tip = 0
        pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
        for i, k in enumerate(keys):
            if k in JITO_TIP_ACCOUNTS and i < len(pre) and i < len(post):
                d = post[i] - pre[i]
                if d > 0:
                    tip += d
        out.append({
            "s": slot,
            "t": bt,
            "v": tx.get("version"),
            "sig": sigs,
            "fee": fee,
            "prio": prio,
            "cul": cu_limit_and_price(msg, keys, tx.get("version")),
            "cuu": meta.get("computeUnitsConsumed"),
            "ok": meta.get("err") is None,
            "p": programs,
            "tip": tip,
            "payer": keys[0],
        })
    return out


def fetch_one(rpc, slot, outdir: Path, kind: str):
    path = outdir / f"{slot}.jsonl.gz"
    if path.exists():
        return slot, "cached", 0
    # If a slot was skipped by its leader, step forward to the next produced block.
    for s in range(slot, slot + 8):
        block = rpc.call("getBlock", [s, {
            "encoding": "json",
            "maxSupportedTransactionVersion": 1,
            "transactionDetails": "full",
            "rewards": False,
            "commitment": "finalized",
        }])
        if block is not None:
            rows = parse_block(s, block)
            tmp = outdir / f".{s}.tmp"
            with gzip.open(tmp, "wt") as f:
                f.write(json.dumps({"kind": kind, "requested": slot, "slot": s, "t": block.get("blockTime"), "n": len(rows)}) + "\n")
                for r in rows:
                    f.write(json.dumps(r, separators=(",", ":")) + "\n")
            os.replace(tmp, outdir / f"{s}.jsonl.gz")
            return s, kind, len(rows)
    return slot, "missing", 0


def plan(head, days, every_min, burst_hours, burst_len):
    span = int(days * 86400 / SLOT_SECONDS_GUESS)
    start = head - span
    grid_step = int(every_min * 60 / SLOT_SECONDS_GUESS)
    burst_step = int(burst_hours * 3600 / SLOT_SECONDS_GUESS)
    jobs = {}
    for s in range(start, head, grid_step):
        jobs[s] = "grid"
    # Bursts offset by half a grid step so they do not sit on grid slots.
    for b in range(start + grid_step // 2, head - burst_len, burst_step):
        for i in range(burst_len):
            jobs.setdefault(b + i, f"burst:{b}")
    return sorted(jobs.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "research" / "data" / "blocks"))
    ap.add_argument("--rpc", default=PUBLIC_RPC)
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--every-min", type=float, default=5)
    ap.add_argument("--burst-hours", type=float, default=6)
    ap.add_argument("--burst-len", type=int, default=20)
    ap.add_argument("--workers", type=int, default=2)
    # The free public RPC allows 6 getBlock calls per 10 seconds per IP.
    ap.add_argument("--min-interval", type=float, default=1.75, help="seconds between requests, all threads")
    ap.add_argument("--head", type=int, default=0, help="newest slot of the sampling window")
    ap.add_argument("--limit", type=int, default=0, help="only fetch this many slots (for a test run)")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    rpc = Rpc(args.rpc, args.min_interval)
    # Pass --head to keep the sampling plan identical across resumed runs.
    head = args.head or rpc.call("getSlot", [{"commitment": "finalized"}])
    jobs = plan(head, args.days, args.every_min, args.burst_hours, args.burst_len)
    if args.limit:
        jobs = jobs[-args.limit:]
    print(f"head {head}, {len(jobs)} slots to fetch into {outdir}", flush=True)

    done = 0
    txs = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_one, rpc, s, outdir, k) for s, k in jobs]
        for f in as_completed(futs):
            try:
                s, kind, n = f.result()
            except Exception as e:  # keep going; a rerun retries failed slots
                print(f"error: {e}", file=sys.stderr, flush=True)
                continue
            done += 1
            txs += n
            if done % 50 == 0 or done == len(jobs):
                rate = done / (time.time() - t0)
                print(f"{done}/{len(jobs)} blocks, {txs} txs, {rate:.2f} blocks/s", flush=True)
    print("finished", flush=True)


if __name__ == "__main__":
    main()
