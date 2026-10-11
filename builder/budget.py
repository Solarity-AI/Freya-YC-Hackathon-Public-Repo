"""Wall-clock budget for one build (docs/CONTRACTS.md F). Owner: agent 5.
Hard cap 26:00 (stop, export last published, exit 6), soft cap 20:00 (skip optional stages), 3 min reserve.

Deadlines are absolute (computed once from the start instant), so slow stages can never extend the budget.
The clock is injectable for tests.
"""
import time

HARD_S = 26 * 60
SOFT_S = 20 * 60
RESERVE_S = 3 * 60
OPTIONAL_STAGES = ("critic", "reextract", "twin")


class BudgetExceeded(Exception):
    """Raised by Budget.check() once the hard cap has passed."""


class Budget:
    def __init__(self, hard_s=HARD_S, soft_s=SOFT_S, reserve_s=RESERVE_S, start=None, clock=None):
        self.clock = clock or time.monotonic
        self.hard_s = float(hard_s)
        self.soft_s = float(min(soft_s, hard_s))
        self.reserve_s = float(max(0.0, reserve_s))
        self.start = float(self.clock() if start is None else start)
        self.hard_at = self.start + self.hard_s
        self.soft_at = self.start + self.soft_s
        self.skipped = []

    def elapsed(self):
        return self.clock() - self.start

    def remaining(self):
        """Seconds until the hard cap."""
        return self.hard_at - self.clock()

    def soft_remaining(self):
        return self.soft_at - self.clock()

    def past_soft(self):
        return self.clock() >= self.soft_at

    def past_hard(self):
        return self.clock() >= self.hard_at

    def call_timeout(self, cap_s):
        """min(cap_s, remaining() - reserve); <= 0 means do not start the call."""
        return min(float(cap_s), self.remaining() - self.reserve_s)

    def go(self, stage):
        """False for OPTIONAL_STAGES past the soft cap, and for anything past the hard cap."""
        if self.past_hard():
            ok = False
        elif stage in OPTIONAL_STAGES:
            ok = not self.past_soft()
        else:
            ok = True
        if not ok:
            self.skipped.append(stage)
        return ok

    def check(self, stage=""):
        """Raise BudgetExceeded past the hard cap (used between mandatory stages)."""
        if self.past_hard():
            raise BudgetExceeded("hard cap %.0fs passed at stage %r" % (self.hard_s, stage))

    def snapshot(self):
        return {"elapsed_s": round(self.elapsed(), 1), "remaining_s": round(self.remaining(), 1),
                "soft_remaining_s": round(self.soft_remaining(), 1), "skipped": list(self.skipped)}
