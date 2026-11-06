# Blockspace fee lanes: 7-day fee swings, backtest and onboarding

Data: 2,587 Solana mainnet blocks sampled from 2026-10-30 05:02 to 2026-11-06 05:07 UTC.
That is one block every 5 minutes (2,017 "grid" blocks), plus 29 runs of 20 consecutive blocks taken every 6 hours to measure block-to-block moves.
Vote transactions are excluded, which leaves about 375 transactions per block.
Landing cost of a transaction = priority fee + Jito tip.
The 5,000-lamport base fee per signature is fixed, so it is left out.
SOL is priced at $89.54 (CoinGecko, 2026-11-06).
Reproduce with `python3 scripts/collect_blocks.py --head 465986000` and then `python3 scripts/analyze.py 89.54`.

## 1. The market

| | per day | per year |
|---|---|---|
| Priority fees | 3,636 SOL | |
| Jito tips | 926 SOL | |
| Total landing spend | $408,000 | about $149M |

71% of non-vote transactions pay a priority fee and 4.8% tip Jito.
The sampled Jito figure (about $83k a day) is below DefiLlama's 24-hour figure from a week earlier ($139k).
Tips are heavy-tailed, so one block every 5 minutes undercounts them, and the total is a floor rather than an estimate.

Spend is concentrated.
The top 10 programs carry 77% of all landing spend.

## 2. Fee swings per program

In the table, "block p90/p10" compares a busy block with a quiet block, using the median cost per block.
"Hourly p90/p10" compares a busy hour with a quiet hour, after pooling each hour's transactions.
"Next block" is how much the median cost moves from one block to the very next (0.4 seconds later): the typical move, then the 90th-percentile move.

| Program | Share of spend | $/day | Median cost (lamports) | Block p90/p10 | Hourly p90/p10 | Next block, typical / p90 |
|---|---|---|---|---|---|---|
| Plain transfers | 26.4% | 108,000 | 200 | n/a (p10 = 0) | n/a | 5.3x / 126x |
| pump.fun | 12.3% | 50,100 | 20,000 | 145x | 6.3x | 3.1x / 31x |
| PumpSwap | 8.8% | 35,900 | 0 | n/a (p10 = 0) | n/a | 1.6x / 20x |
| term9Y.. (unidentified) | 7.6% | 31,100 | 100,000 | 100x | 27x | 2.0x / 94x |
| DFlow aggregator | 6.4% | 26,200 | 245,337 | 1,506x | 26x | 4.3x / 714x |
| FLASHX.. (unidentified) | 4.9% | 19,900 | 15,139 | 78x | 8.4x | 3.4x / 40x |
| Jupiter v6 | 4.3% | 17,500 | 2,679 | 85x | 4.9x | 3.5x / 44x |
| Lighthouse (wallet guard) | 3.5% | 14,200 | 100 | 1,390x | 162x | 1.0x / 82x |
| 6Vo324.. (unidentified) | 1.6% | 6,400 | 4,000 | 16x | 5.0x | 1.8x / 25x |
| MAyhSm.. (one payer) | 1.4% | 5,800 | 40,000 | 7x | 5.2x | 1.0x / 1.0x |

What this says:

- On the same program, the price of landing a typical transaction usually moves 2 to 5 times between one block and the next.
One move in ten is 20 to 700 times.
- Averaging over a full hour does not smooth it away.
A busy hour costs 5 to 27 times a quiet hour on the main trading programs.
- An app that sets one static priority fee is therefore either overpaying most of the time or failing to land at peaks.
That is the problem a fixed-price lane sells against.
- Some top-20 "programs" are single transactions that paid 0.06 to 0.165 SOL.
They are tail events, not markets, and the lane product ignores them.
- The plain-transfer and PumpSwap medians are near zero, because most of those transactions pay almost nothing and a minority pay a lot.

## 3. What a fixed-fee lane would have earned

### How the backtest works

- For each of the top 10 programs, all sampled transactions are pooled by hour.
- There are three tiers.
Standard pays that hour's median landing cost.
Fast pays the hour's 75th percentile, beating three competitors in four.
Priority pays the 90th percentile.
- The flat price for the hour is set in advance, with no look-ahead: a margin (1.0, 1.1 or 1.25) times the 75th percentile of the previous 24 hourly costs for that tier.
- Profit = flat price minus the cost actually paid that hour.
- The seven days give 148 to 149 tradable hours per program.

### Results at a 1.1 margin

"Price / cost" is how much more than spot the customer pays on average for a fixed price.
"Paid more" is the share of the program's real transactions that paid more than the lane's price that hour.
"Worst hour" is the worst hour's loss as a multiple of an average hour's profit.

| Program | Tier | Gross margin | Price / cost | Losing hours | Worst hour | Paid more | $/day if the lane had all the flow |
|---|---|---|---|---|---|---|---|
| pump.fun | fast | 52% | 2.08x | 24/149 | -2x | 15% | 12,500 |
| PumpSwap | fast | 35% | 1.54x | 7/149 | -2x | 14% | 4,700 |
| term9Y.. | fast | 30% | 1.42x | 5/148 | -3x | 7% | 13,700 |
| Jupiter v6 | fast | 33% | 1.48x | 40/149 | -5x | 19% | 1,900 |
| Plain transfers | fast | 31% | 1.46x | 30/149 | -5x | 20% | 3,300 |
| FLASHX.. | fast | 21% | 1.26x | 33/149 | -35x | 19% | 2,300 |
| DFlow aggregator | fast | 6% | 1.07x | 27/148 | -59x | 17% | 1,800 |
| term9Y.. | priority | -24% | 0.81x | 34/148 | loses overall | 6% | -15,000 |
| pump.fun | standard | 48% | 1.93x | 25/149 | -5x | 34% | 2,000 |
| Jupiter v6 | standard | 28% | 1.39x | 28/149 | -5x | 42% | 400 |

The full table, covering every program, tier and margin, is in `research/data/summary.json` and is printed by `analyze.py`.

### What it means

- A lane priced from yesterday's 75th percentile makes a gross margin of 20 to 50% on most program and tier pairs.
A few lose money: term9Y priority and DFlow fast.
- That margin comes from the customer paying 1.3 to 2 times the average spot cost.
The lane is insurance, and it has to be sold as insurance: a budgetable cost per user action, no fee-estimation work, a refund if the transaction misses.
It is not a discount on average fees.
- Even so, 14 to 20% of the real transactions on these programs paid more than the fast-lane price.
For a wallet or app whose users fall in that group, the lane is cheaper as well as predictable.
The "what you would have saved" calculator below finds those customers.
- The tail is the real risk.
Losing hours are 5 to 40 out of 149, and the worst hour can wipe out 35 to 60 average hours of profit (DFlow fast, FLASHX fast).
This is why the design needs an underwriting vault with capital, a hard cap on what we pay per transaction (Kora's `max_priority_fee_lamports`), and fee futures to lay off the tail.

### Revenue scenarios (assumptions are labelled)

If the fast lane at 1.1x had carried all the flow of the top 10 programs, gross profit would have been about $42,000 a day.
The standard lane would have made about $24,600 a day.
No lane gets all the flow, so the realistic numbers depend on the capture share, which is an assumption:

| Share of top-10 program flow on our lanes (assumed) | Gross profit/day | Per year |
|---|---|---|
| 0.5% | $210 | $77k |
| 2% | $840 | $307k |
| 10% | $4,200 | $1.5M |

- Fee futures are the risk tool, not the revenue line.
The hedgeable market is about $149M a year of landing spend.
Even with heavy hedging, trading fees at 5 to 10 basis points come to thousands of dollars a year, not millions, unless speculators adopt a "Solana activity index" contract.
- Selling the fee index as data is weak revenue.
Priority-fee estimates are free from Helius and the RPC.
The index's value is as the public "fee weather" page and as the settlement price for the lanes and futures.
- Bottom line: revenue is the lane spread.
It is a real but modest business at hackathon scale, from $300k a year at 2% capture to $1.5M at 10%.
It grows with Solana's fee spend and with how many apps sponsor their users' fees.

### Limits of this backtest

- One week is one regime.
A memecoin mania or an outage week would move both the margins and the tails.
- Paying the 75th-percentile fee buys position in the program's local fee market, not guaranteed inclusion.
Inclusion also depends on the leader's scheduler and the Jito auction.
Landing latency per tier has to be measured with real sends before an SLA is promised.
- Customers who paid huge fees may be bots buying top-of-block on purpose, and they will not move to a flat lane.
- Five of the top 10 programs are not yet identified by name.

## 4. Onboarding

The paying customer is an app or wallet that sponsors its users' fees, or wants a flat per-action cost.
Traders and liquidity providers are secondary.

### A. App or wallet buying a lane (the paying customer)

1. Paste a fee-payer address, or connect the app's wallet.
The site pulls that payer's last 7 days of transactions and detects which programs it calls.
2. It shows the app's own week: what it paid, how much that varied, and what each tier would have cost at a flat price, including how many of its transactions would have been cheaper.
This is the same backtest as above, run on that one payer.
3. The app picks a tier per program and a monthly budget, then prepays USDC into its lane account, an onchain escrow.
4. It gets an API key and a paymaster URL.
Integration is a fee-payer swap: the app's client calls our Kora-compatible endpoint (`signAndSendTransaction`) instead of signing with its own fee payer.
Kora's `fixed` pricing charges the flat USDC price per transaction, `usage_limit` holds the quota per key, and `max_priority_fee_lamports` caps our cost.
5. A dashboard shows landed rate, latency, the flat cost per transaction, savings against spot, and automatic refunds for transactions that miss the tier's target.

Time to first lane transaction: a few minutes for an app already using Kora, and one SDK call swap for one that is not.

### B. Underwriter vault (liquidity providers)

1. Deposit USDC into the lane vault.
2. The vault earns the lane spread and pays the losing hours.
The deposit screen shows the backtest's margin, losing hours and worst hour, so the risk is visible before depositing.
3. The vault caps its tail by buying fee futures and through the per-transaction price cap.
Withdrawals have a cooldown, so capital cannot leave right before a fee spike.

### C. Hedgers and traders on fee futures

1. Connect a wallet and deposit USDC.
2. Go long or short a per-program fee index (pump.fun fast, Jupiter fast, network-wide) for the next hour, day or week.
Settlement is the published index.
3. The natural longs are the vault and apps that self-insure.
The natural shorts are validators and searchers, whose income rises with fees.

### D. Top of funnel

- A public "fee weather" page: the live per-program index, the next-hour forecast and today's swing, built from this pipeline on a Cloudflare Worker cron.
- The "what would you have saved" calculator from step A1, shareable as a link per payer address.
- A Kora operator listing, so apps that already run a Kora node can point their fee strategy at our lanes.

## 5. Next steps

- Measure landing latency per tier with real sends.
This needs a small mainnet SOL budget and approval.
- Identify the five unnamed programs.
- Extend the collector to 30 days through a paid RPC (Helius key on file) to cover more than one regime.
- Prototype the calculator, since it is both the sales tool and the demo.
