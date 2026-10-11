"""builder.budget with an injected clock (agent 5)."""
import pytest

from builder.budget import Budget, BudgetExceeded, HARD_S, SOFT_S, RESERVE_S


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_contract_defaults():
    assert (HARD_S, SOFT_S, RESERVE_S) == (1560, 1200, 180)
    assert HARD_S < 30 * 60


def test_absolute_deadlines():
    c = Clock()
    b = Budget(clock=c)
    assert b.elapsed() == 0 and b.remaining() == 1560
    c.t += 100
    assert b.elapsed() == 100 and b.remaining() == 1460 and b.soft_remaining() == 1100


def test_call_timeout_caps_and_reserve():
    c = Clock()
    b = Budget(clock=c)
    assert b.call_timeout(300) == 300
    c.t += 1560 - 180 - 100              # 100 s left before the reserve
    assert b.call_timeout(300) == pytest.approx(100)
    c.t += 150
    assert b.call_timeout(300) <= 0


def test_go_optional_vs_mandatory():
    c = Clock()
    b = Budget(clock=c)
    assert b.go("critic") and b.go("twin") and b.go("deploy")
    c.t += 1200                          # soft cap
    assert not b.go("critic") and not b.go("reextract") and not b.go("twin")
    assert b.go("deploy") and b.go("compile")
    c.t += 360                           # hard cap
    assert not b.go("deploy")
    assert b.snapshot()["skipped"] == ["critic", "reextract", "twin", "deploy"]


def test_check_raises_past_hard():
    c = Clock()
    b = Budget(hard_s=10, soft_s=5, reserve_s=1, clock=c)
    b.check("x")
    c.t += 10
    with pytest.raises(BudgetExceeded):
        b.check("x")
    assert b.past_hard() and b.past_soft()


def test_soft_never_after_hard_and_start_override():
    c = Clock(50)
    b = Budget(hard_s=10, soft_s=99, reserve_s=0, start=40, clock=c)
    assert b.soft_s == 10 and b.elapsed() == 10 and b.past_hard()


def test_real_clock_smoke():
    b = Budget()
    assert 0 <= b.elapsed() < 5 and b.remaining() > 1500
