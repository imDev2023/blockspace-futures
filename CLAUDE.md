# blockspace-futures

Fixed-price Solana transaction lanes plus per-program fee futures, for the Colosseum hackathon.
Read `research/report.md` first: it holds the data, the backtest and the onboarding design.

## Layout

- `scripts/collect_blocks.py` samples mainnet blocks (stdlib only, free public RPC by default, resumable).
The free RPC allows 6 getBlock calls per 10 seconds, so keep `--min-interval 1.75` there.
Pass `--head` to keep the sampling plan identical across resumed runs.
- `scripts/analyze.py` writes `research/data/summary.json` and prints the tables in the report.
Its argument is the SOL/USD price.
- `research/data/` is gitignored.

## Conventions

- Landing cost = priority fee + Jito tip; the base fee is left out.
- Run Python that reads downloaded data with `python3 -I`.
- Issues live in GitHub Issues on imDev2023/blockspace-futures.
