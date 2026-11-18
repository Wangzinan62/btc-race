# btc-race

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Wangzinan62/btc-race/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Wangzinan62/btc-race/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A cost-aware cbBTC/USDC trading bot for the agent-fun/bars-replay/v1 protocol (1-minute bars, long only, 1,000 USDC paper capital). Breakout and EMA-cross designs were graded on the dev window and lost money after the ~30-36 bps a full-size round trip costs in fees, slippage and price impact, so this bot instead buys the snap-back after a sharp short dip — but only inside a guarded regime: it trades solely while the trailing 240-bar return is above -40 bps, enters when the trailing 30-bar return is at most -35 bps and the dip has stopped falling, sizes each buy so its own estimated price impact at the latest close's pool depth stays under ~12 bps, and exits on a trailing stop (armed at +45 bps, 20 bps under the best close), a 90 bps hard stop, or a 180-bar time stop. It stops entering in the window's last hour and is flat by the last half hour. On the kit's dev window, graded with the kit's own replay engine, it nets +8.18 USDC over 3 round trips with 0.62% maximum drawdown — profitable where all six kit baselines lose money or stay flat. Fully deterministic: no clock, no network, no randomness.

## Run it

```sh
python3 -P -s main.py   # speaks agent-fun/bars-replay/v1 NDJSON on stdin/stdout
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=7n4st51n&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
