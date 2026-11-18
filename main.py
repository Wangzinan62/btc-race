"""BTC race bot: dip-buying inside a guarded regime, for agent-fun/bars-replay/v1.

Why this design: on the dev window every breakout / EMA-cross variant we
graded lost money after costs — by the time a one-minute breakout confirms,
the move is over, and a full-size round trip charges roughly 30-36 bps in
fees, slippage and price impact. What the window (and minute-bar DEX prices
generally) does reward is the snap-back after a sharp short dip, provided
the slower trend is not genuinely falling. So:

  - Regime guard: no trade unless the trailing 240-bar return is above
    -40 bps. Dip-buying in a real downtrend is catching a falling knife;
    the guard keeps the bot in cash through those hours.
  - Entry: the trailing 30-bar return is at most -35 bps (a sharp dip) and
    the latest close ticks up from the previous one — the dip has stopped
    falling, at least for a bar — with realised volatility (60-bar) inside
    a sane band, so flatlines and blow-offs are both skipped.
  - Sizing: the buy is capped so its own estimated price impact at the
    latest close's pool depth stays under ~12 bps, and never above 95% of
    equity; impact is read from the SDK's impact_bps on the live depth.
  - Exit: no fixed target — a trailing stop (armed once the trade is
    +45 bps in profit, then 20 bps under the best close since entry) lets
    a bounce that turns into a run keep paying. A hard stop 90 bps under
    the entry reference close and a 180-bar time stop cut the failures.
  - No new entries in the last hour of the window and everything is flat
    by the last half hour, so the end-of-window forced sale at the last
    close never finds us holding into a final-minute slide.

Everything is computed from the bars themselves: no clock, no network, no
randomness, so two runs on the same data answer identically.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

BPS = 10_000

DIP_BARS = 30
DIP_BPS = 35.0
REGIME_BARS = 240
REGIME_MIN_BPS = -40.0
VOL_BARS = 60
VOL_MIN_BPS = 2.0
VOL_MAX_BPS = 25.0
IMPACT_CAP_BPS = 12
MAX_EQUITY_BPS = 9_500
TRAIL_ARM_BPS = 45.0
TRAIL_BPS = 20.0
STOP_BPS = 90.0
TIME_STOP_BARS = 180
COOLDOWN_BARS = 5
ENTRY_SLIPPAGE_BPS = 120
EXIT_SLIPPAGE_BPS = 250
NO_ENTRY_AFTER_MIN = 23 * 60
FLATTEN_AFTER_MIN = 23 * 60 + 30


class Bot:
    def __init__(self):
        self.symbol = None
        self.closes = []          # every close of our symbol, as float
        self.rets = []            # per-bar simple returns, as float
        self.first_t = None
        self.entry_ref = None     # close at the entry decision, float price units
        self.peak = None          # best close since entry
        self.held_bars = 0
        self.cooldown = 0

    # -- indicators ------------------------------------------------------
    def push_bar(self, bar):
        c = float(bar["c"])
        if self.closes:
            self.rets.append(c / self.closes[-1] - 1.0)
        self.closes.append(c)
        return c

    def ret_bps(self, bars):
        if len(self.closes) <= bars:
            return None
        return (self.closes[-1] / self.closes[-1 - bars] - 1.0) * BPS

    def vol_bps(self):
        if len(self.rets) < VOL_BARS:
            return None
        window = self.rets[-VOL_BARS:]
        mean = sum(window) / len(window)
        var = sum((r - mean) ** 2 for r in window) / len(window)
        return var ** 0.5 * BPS

    # -- sizing ----------------------------------------------------------
    def buy_size(self, state):
        room = state.weight_room(self.symbol)
        budget = min(state.cash, state.equity * MAX_EQUITY_BPS // BPS, room)
        if budget <= 0:
            return 0
        # Shrink until the estimated impact at the latest close depth fits the cap.
        size = budget
        while size > 0:
            impact = state.impact_bps(self.symbol, size * (BPS - 4) // BPS)
            if impact is None or impact <= IMPACT_CAP_BPS:
                break
            size = size * 9 // 10
        return size

    # -- decisions -------------------------------------------------------
    def on_batch(self, state, batch):
        fresh = None
        for bar in batch["bars"]:
            if bar["symbol"] == self.symbol:
                fresh = self.push_bar(bar)
        if self.symbol is None:
            return []
        if self.first_t is None and fresh is not None:
            self.first_t = batch["t"]
        if state.warming_up or fresh is None:
            return []

        held = state.positions.get(self.symbol)
        elapsed_min = (batch["t"] - self.first_t) // 60_000 if self.first_t is not None else 0

        if held is not None:
            self.held_bars += 1
            if self.peak is None or fresh > self.peak:
                self.peak = fresh
            if self.should_exit(fresh, elapsed_min):
                self.entry_ref = None
                self.peak = None
                self.held_bars = 0
                self.cooldown = COOLDOWN_BARS
                return [{"side": "sell", "symbol": self.symbol, "qty": held.qty,
                         "max_slippage_bps": EXIT_SLIPPAGE_BPS}]
            return []

        if self.cooldown > 0:
            self.cooldown -= 1
            return []
        if elapsed_min >= NO_ENTRY_AFTER_MIN:
            return []
        dip = self.ret_bps(DIP_BARS)
        if dip is None or dip > -DIP_BPS:
            return []
        regime = self.ret_bps(REGIME_BARS)
        if regime is None or regime < REGIME_MIN_BPS:
            return []
        # The dip must have stopped falling: this close above the previous one.
        if len(self.closes) < 2 or self.closes[-1] <= self.closes[-2]:
            return []
        vol = self.vol_bps()
        if vol is None or vol < VOL_MIN_BPS or vol > VOL_MAX_BPS:
            return []
        size = self.buy_size(state)
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if size < max(min_notional, 1_000_000):
            return []
        self.entry_ref = fresh
        self.peak = fresh
        self.held_bars = 0
        return [{"side": "buy", "symbol": self.symbol, "notional_quote_units": size,
                 "max_slippage_bps": ENTRY_SLIPPAGE_BPS}]

    def should_exit(self, close, elapsed_min):
        if elapsed_min >= FLATTEN_AFTER_MIN:
            return True
        if self.entry_ref is None:
            return False
        gain = (close / self.entry_ref - 1.0) * BPS
        if gain <= -STOP_BPS:
            return True
        if self.peak is not None:
            peak_gain = (self.peak / self.entry_ref - 1.0) * BPS
            if peak_gain >= TRAIL_ARM_BPS and close < self.peak * (1.0 - TRAIL_BPS / BPS):
                return True
        if self.held_bars >= TIME_STOP_BARS:
            return True
        return False

    def on_hello(self, state):
        self.symbol = state.hello["symbols"][0]["symbol"]


BOT = Bot()


def main():
    makefun_bars.run(BOT.on_batch, on_hello=BOT.on_hello)


if __name__ == "__main__":
    main()
