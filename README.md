# blockspace-futures

Fixed-price Solana transaction lanes, backed by an underwriting vault and per-program fee futures.
Built for the Colosseum hackathon.

An app or wallet pays one flat USDC price per transaction on a program, such as pump.fun or Jupiter.
We land the transaction through a Kora-compatible paymaster and take the spread between the flat price and the real fee.
The vault takes the fee risk, and fee futures on a published per-program index lay off its tail.

## Research

`research/report.md` covers 7 days of mainnet data: fee swings per program, a backtest of the lane margin, revenue scenarios and the onboarding flows.

```bash
python3 scripts/collect_blocks.py --head 465986000   # about 75 minutes on the free public RPC
python3 scripts/analyze.py 89.54                     # SOL/USD price
```

Raw block samples go to `research/data/` (gitignored, about 40 MB).
