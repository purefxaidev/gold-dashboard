#!/usr/bin/env python3
"""Verify 0.9.13 alert copy on live H1 data plus synthetic reversal/sideways/breakout."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import trade_plan as tp

KLINES = Path("/workspace/puregold-whitepaper/assets/xau-klines.json")
PLAN = Path("/workspace/gold-dashboard/trade_plan.json")


try:
    import pytest

    @pytest.fixture
    def plan():
        return json.loads(PLAN.read_text())
except ImportError:  # script mode
    pass


def assert_in(needle, hay, label):
    if needle not in hay:
        raise AssertionError(f"{label}: missing {needle!r} in {hay!r}")


def test_live():
    plan = json.loads(PLAN.read_text())
    klines = json.loads(KLINES.read_text()) if KLINES.exists() else {}
    # Recompute flags from current files
    plan = tp.attach_live_flags(plan, {}, (json.loads((ROOT / "events.json").read_text()) if (ROOT / "events.json").exists() else {}), prev_plan=plan, klines_doc=klines)
    px = plan.get("spot") or 0
    th = tp.format_alert_text(plan, px, "th")["short"]
    assert_in("ราคาล่าสุด $", th, "live lead")
    assert_in("ตอนนี้", th, "live stance")
    assert_in("เพราะ", th, "live because")
    if "Demand Zone" not in th and "Supply Zone" not in th and "ไซด์เวย์" not in th:
        raise AssertionError("live alert must name a zone or the sideways range: " + th)
    print("LIVE:", th)


def test_reversal_demand(plan):
    # Deterministic: three closed H1 bars falling into the plan's Demand Zone, then a bullish close in it.
    lo, hi = sorted((float(plan["demand_zone"]["low"]), float(plan["demand_zone"]["high"])))
    closed = [(1, hi + 30, hi + 32, hi + 18, hi + 20), (2, hi + 20, hi + 21, hi + 8, hi + 10), (3, hi + 10, hi + 11, hi + 1, hi + 2), (4, 0, 0, 0, 0)]
    bar = {"open": lo + 1, "high": hi + 3, "low": lo - 1, "close": hi - 0.5, "bullish": True, "open_ts": 1}
    rev = tp.detect_reversal(bar, closed[-4:-1], plan["demand_zone"], plan["supply_zone"])
    assert rev and rev["confirmed"]
    assert_in("นี่คือจุดกลับตัว", rev["note_th"], "reversal phrase")
    assert_in("Demand Zone", rev["note_th"], "demand zone")
    assert_in("BUY", rev["note_th"], "BUY")
    fake = dict(plan)
    fake["h1"] = {"confirmed": True, "reversal": rev, "sideways": {"active": False}, "breakout": {"confirmed": False}}
    fake["news"] = {"blackout": False}
    fake["alert"] = tp.build_alert(fake)
    text = tp.format_alert_text(fake, bar["close"], "th")["short"]
    assert text.startswith("ราคาล่าสุด $")
    assert_in("นี่คือจุดกลับตัว", text, "lead+reversal")
    assert_in("ตอนนี้ BUY", text, "stance BUY")
    print("REV:", text)


def test_attach_live_flags_null_prev_fields(plan):
    # Regression: a previous plan may carry h1.reversal / h1 / breakout as null.
    prev = dict(plan)
    prev["h1"] = {"confirmed": False, "reversal": None, "sideways": None, "breakout": None}
    out = tp.attach_live_flags(dict(plan), {}, {}, prev_plan=prev, klines_doc=json.loads(KLINES.read_text()) if KLINES.exists() else {})
    assert "h1" in out
    prev["h1"] = None
    tp.attach_live_flags(dict(plan), {}, {}, prev_plan=prev, klines_doc={})


def test_sideways_and_breakout():
    syn = []
    price = 3884.0
    for i in range(8):
        syn.append((1_000_000 + i * 3600, price, price + 2.0, price - 2.0, price + (0.4 if i % 2 == 0 else -0.3)))
        price = syn[-1][4]
    sw = tp.detect_sideways(syn)
    assert sw.get("active"), sw
    assert_in("กราฟไซด์เวย์ ราคาระหว่าง", sw["note_th"], "sideways rule")
    assert_in("ไม่มีทิศชัด แนะนำรอดูแท่ง H1 ปิดออกจากช่วงก่อนเข้า", sw["note_th"], "wait rule")
    locked = sw
    last = list(syn[-1])
    last[2] = last[4] + 20
    last[4] = last[4] + 18
    syn[-1] = tuple(last)
    br = tp.detect_sideways(syn, locked)
    assert br.get("breakout", {}).get("confirmed"), br
    assert br["breakout"]["direction"] == "up"
    assert_in("ปิดยืนยันเบรกออกจากช่วงไซด์เวย์", br["breakout"]["note_th"], "breakout")
    print("SW:", sw["note_th"])
    print("BO:", br["breakout"]["note_th"])


if __name__ == "__main__":
    plan = json.loads(PLAN.read_text())
    test_live()
    test_reversal_demand(plan)
    test_attach_live_flags_null_prev_fields(plan)
    test_sideways_and_breakout()
    print("ALL TESTS PASSED")
