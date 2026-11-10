#!/usr/bin/env python3
"""Build PureGold market-desk JSON: calendar, COT, fear & greed, Thai vs world, briefs.

All figures come from public sources. If a source fails, the previous file is left
untouched so the site can keep showing last-good data with its as-of time.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BKK = timezone(timedelta(hours=7))
UA = "PureGoldDesk/1.0 (+https://dashboard.purefxai.store/)"
OZ_G = 31.1035
BAHT_G = 15.244
PURITY = 0.965
TH_M = "ม.ค. ก.พ. มี.ค. เม.ย. พ.ค. มิ.ย. ก.ค. ส.ค. ก.ย. ต.ค. พ.ย. ธ.ค.".split()
EN_M = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
COT_URL = (
    "https://publicreporting.cftc.gov/resource/72hh-3qpy.json?"
    + urllib.parse.urlencode({
        "$where": "cftc_contract_market_code='088691'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "52",
    })
)
COT_SOURCE_PAGE = "https://publicreporting.cftc.gov/resource/72hh-3qpy"
HSH_URL = "https://apicheckprice.huasengheng.com/api/values/getprice/"
YAHOO_THB = "https://query1.finance.yahoo.com/v8/finance/chart/THB=X?interval=1d&range=15d"
ER_API = "https://open.er-api.com/v6/latest/USD"
FRANKFURTER = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=THB"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
OR_MODELS = [
    "nvidia/nemotron-3.5-super-vl:free",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


def now_bkk() -> datetime:
    return datetime.now(BKK)


def iso_z(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_th(dt: datetime, with_time: bool = True) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    b = dt.astimezone(BKK)
    s = f"{b.day} {TH_M[b.month - 1]} {b.year}"
    if with_time:
        s += f" {b.hour:02d}:{b.minute:02d} น. (เวลาไทย)"
    return s


def fmt_en(dt: datetime, with_time: bool = True) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    b = dt.astimezone(BKK)
    s = f"{b.day} {EN_M[b.month - 1]} {b.year}"
    if with_time:
        s += f" {b.hour:02d}:{b.minute:02d} (Bangkok time)"
    return s


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    raw = str(s).strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        if re.match(r"\d{4}-\d{2}-\d{2}$", raw):
            return datetime.fromisoformat(raw).replace(tzinfo=BKK)
        if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", raw) and "T" not in raw:
            return datetime.fromisoformat(raw.replace(" ", "T")).replace(tzinfo=BKK)
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def http_json(url: str, timeout: int = 20, headers: dict | None = None) -> Any:
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def keep(path: Path, label: str, err: Exception) -> None:
    print(f"[insights] {label} failed ({err}); keeping last good file" if path.exists()
          else f"[insights] {label} failed ({err}); no prior file", file=sys.stderr)


def num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("฿", "").replace("$", "").strip()
    s = s.replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def first_num(s: Any) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(s or ""))
    return float(m.group().replace(",", "")) if m else None


# ---------------------------------------------------------------------------
# 1. Economic calendar
# ---------------------------------------------------------------------------

IMPACT_NOTES = [
    (r"core cpi", {
        "th": "เงินเฟ้อพื้นฐานของสหรัฐฯ หากสูงกว่าคาด ตลาดมักเลื่อนความหวังลดดอกเบี้ย และทองมักถูกกดดัน",
        "en": "US core inflation. A hotter-than-forecast print often delays rate-cut hopes and can weigh on gold.",
    }),
    (r"\bcpi\b", {
        "th": "ดัชนีราคาผู้บริโภคสหรัฐฯ เป็นข่าวที่ขยับทองได้แรง หากสูงกว่าคาด ดอลลาร์มักแข็งและทองย่อ",
        "en": "US consumer inflation, a high-impact gold event. A hot print often firms the dollar and softens gold.",
    }),
    (r"core pce|pce price", {
        "th": "ตัวชี้เงินเฟ้อที่เฟดให้น้ำหนัก หากสูงกว่าคาด ทองมักย่อตามความหวังดอกเบี้ย",
        "en": "The Fed's preferred inflation gauge. A hot print often cools gold as rate-cut odds fade.",
    }),
    (r"\bpce\b", {
        "th": "ดัชนี PCE ของสหรัฐฯ มีผลต่อมุมมองดอกเบี้ยของเฟด และมักขยับราคาทอง",
        "en": "US PCE inflation can shift Fed rate expectations and often moves gold.",
    }),
    (r"non-farm|nonfarm|payroll|nfp", {
        "th": "การจ้างงานนอกภาคเกษตรกรรม หากแข็งแกร่งมักหนุนดอลลาร์และกดทอง ในทางกลับกันตัวเลขอ่อนอาจหนุนทอง",
        "en": "Non-farm payrolls. A strong report often lifts the dollar and presses gold; a weak one can support gold.",
    }),
    (r"unemployment claims|jobless|initial claims", {
        "th": "ยื่นขอสวัสดิการว่างงานที่สูงขึ้นสะท้อนตลาดแรงงานอ่อน อาจหนุนทองในฐานะสินทรัพย์หลบความเสี่ยง",
        "en": "Rising jobless claims can signal a softer labor market and may support gold as a defensive asset.",
    }),
    (r"unemployment rate", {
        "th": "อัตราการว่างงานสหรัฐฯ หากสูงกว่าคาด ดอกเบี้ยมีโอกาสถูกปรับลงและทองอาจได้แรงหนุน",
        "en": "The US unemployment rate. A higher-than-expected reading can lift rate-cut odds and support gold.",
    }),
    (r"fomc|federal funds|interest rate decision|fed rate", {
        "th": "การประชุมหรือตัดสินใจดอกเบี้ยของเฟด และถ้อยแถลงประกอบ มักขยับทองได้รุนแรงในช่วงข่าว",
        "en": "FOMC rate decisions and the accompanying statement often move gold sharply around the release.",
    }),
    (r"powell", {
        "th": "ถ้อยแถลงประธานเฟดมีผลต่อความคาดหวังดอกเบี้ย และมักทำให้ทองผันผวนในระยะสั้น",
        "en": "Remarks by the Fed chair can reprice rate expectations and often add short-term volatility to gold.",
    }),
    (r"\bgdp\b", {
        "th": "จีดีพีสหรัฐฯ หากโตเกินคาดอาจหนุนดอลลาร์และกดทองในช่วงสั้น",
        "en": "US GDP. Stronger-than-forecast growth can support the dollar and cap gold in the short run.",
    }),
    (r"core ppi|\bppi\b", {
        "th": "ดัชนีราคาผู้ผลิตเป็นสัญญาณนำของเงินเฟ้อผู้บริโภค และอาจขยับความคาดหวังดอกเบี้ย",
        "en": "Producer prices can preview consumer inflation and shift rate expectations.",
    }),
    (r"fomc member|fed .*speaks|speaks", {
        "th": "ถ้อยแถลงกรรมการเฟดอาจขยับความคาดหวังดอกเบี้ยในระยะสั้น โดยเฉพาะหากโทนเข้มหรือผ่อนกว่าที่ตลาดคิด",
        "en": "Fed speakers can nudge near-term rate expectations, especially if the tone is firmer or easier than priced.",
    }),
]

TITLE_TH = {
    "cpi m/m": "ดัชนีราคาผู้บริโภค (เดือนต่อเดือน)",
    "cpi y/y": "ดัชนีราคาผู้บริโภค (ปีต่อปี)",
    "core cpi m/m": "ดัชนีราคาผู้บริโภคพื้นฐาน (เดือนต่อเดือน)",
    "core cpi y/y": "ดัชนีราคาผู้บริโภคพื้นฐาน (ปีต่อปี)",
    "pce price index m/m": "ดัชนี PCE (เดือนต่อเดือน)",
    "core pce price index m/m": "ดัชนี PCE พื้นฐาน (เดือนต่อเดือน)",
    "core pce price index y/y": "ดัชนี PCE พื้นฐาน (ปีต่อปี)",
    "non-farm employment change": "การจ้างงานนอกภาคเกษตรกรรม (NFP)",
    "unemployment rate": "อัตราการว่างงาน",
    "unemployment claims": "ยื่นขอสวัสดิการว่างงานรายสัปดาห์",
    "average hourly earnings m/m": "ค่าจ้างรายชั่วโมงเฉลี่ย (เดือนต่อเดือน)",
    "fomc statement": "แถลงการณ์ FOMC",
    "federal funds rate": "อัตราดอกเบี้ยนโยบายเฟด",
    "fomc press conference": "แถลงข่าวประธานเฟด",
    "preliminary gdp q/q": "จีดีพีเบื้องต้น (ไตรมาสต่อไตรมาส)",
    "advance gdp q/q": "จีดีพีรอบแรก (ไตรมาสต่อไตรมาส)",
    "final gdp q/q": "จีดีพีรอบสุดท้าย (ไตรมาสต่อไตรมาส)",
    "core ppi m/m": "ดัชนีราคาผู้ผลิตพื้นฐาน (เดือนต่อเดือน)",
    "ppi m/m": "ดัชนีราคาผู้ผลิต (เดือนต่อเดือน)",
}

KEYWORDS = re.compile(
    r"cpi|pce|nfp|non-farm|nonfarm|payroll|fomc|powell|gdp|ppi|"
    r"jobless|unemployment|claims|federal funds|interest rate|"
    r"fed |fomc member|speaks",
    re.I,
)


def impact_note(title: str) -> dict:
    t = title.lower()
    for pat, note in IMPACT_NOTES:
        if re.search(pat, t, re.I):
            return note
    return {
        "th": "ข่าวเศรษฐกิจสหรัฐฯ ที่อาจขยับดอลลาร์และความคาดหวังดอกเบี้ย จึงมีผลต่อทองคำ",
        "en": "A US economic release that can move the dollar and rate expectations, and therefore gold.",
    }


def title_th(title: str) -> str:
    key = re.sub(r"\s+", " ", title.strip().lower())
    if key in TITLE_TH:
        return TITLE_TH[key]
    m = re.match(r"fomc member (.+) speaks", key)
    if m:
        return f"กรรมการเฟด {m.group(1).title()} กล่าวสุนทรพจน์"
    if key.endswith(" speaks"):
        return title  # keep official English name, UI will show both
    return title


def keep_event(ev: dict) -> bool:
    if str(ev.get("country") or "").upper() not in {"USD", "US"}:
        return False
    impact = str(ev.get("impact") or "")
    if impact.lower() == "holiday":
        return False
    title = str(ev.get("title") or "")
    if impact in {"High", "Medium"} and KEYWORDS.search(title):
        return True
    if KEYWORDS.search(title):
        return True
    return False


def build_calendar() -> dict:
    raw = http_json(FF_URL, timeout=20)
    if not isinstance(raw, list):
        raise RuntimeError("ForexFactory calendar is not a list")
    events = []
    for ev in raw:
        if not keep_event(ev):
            continue
        dt = parse_iso(ev.get("date") or "")
        if not dt:
            continue
        impact = str(ev.get("impact") or "Low")
        title = str(ev.get("title") or "").strip()
        note = impact_note(title)
        # FF weekly JSON has no `actual` field today; keep the key so a later
        # schema change is picked up automatically.
        actual = ev.get("actual") if ev.get("actual") not in (None, "") else None
        events.append({
            "id": f"{dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M')}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}",
            "title": title,
            "title_th": title_th(title),
            "title_en": title,
            "country": "USD",
            "date": ev.get("date"),
            "date_utc": dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_bkk": dt.astimezone(BKK).strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "date_th": fmt_th(dt),
            "date_en": fmt_en(dt),
            "impact": impact.lower() if impact.lower() in {"high", "medium", "low"} else "low",
            "forecast": ev.get("forecast") or None,
            "previous": ev.get("previous") or None,
            "actual": actual,
            "note_th": note["th"],
            "note_en": note["en"],
        })
    events.sort(key=lambda x: x["date_utc"])
    # Prefer upcoming + recently released (48h)
    cutoff = now_bkk() - timedelta(hours=48)
    events = [e for e in events if parse_iso(e["date_utc"]) and parse_iso(e["date_utc"]) >= cutoff] or events[-20:]
    stamp = now_bkk()
    return {
        "source": "Forex Factory weekly calendar",
        "source_url": FF_URL,
        "source_note_th": "ปฏิทินข่าวสหรัฐฯ จาก Forex Factory สัปดาห์นี้ เฉพาะรายการที่มักกระทบทองคำ",
        "source_note_en": "This week's US calendar from Forex Factory, limited to releases that often move gold.",
        "updated_at": iso_z(),
        "updated_at_bkk": stamp.strftime("%Y-%m-%d %H:%M"),
        "updated_th": fmt_th(stamp),
        "updated_en": fmt_en(stamp),
        "timezone": "Asia/Bangkok",
        "actual_field": "The weekly JSON currently provides title, country, date, impact, forecast and previous. Actual is shown when the feed includes it.",
        "events": events,
    }


# ---------------------------------------------------------------------------
# 2. CFTC COT — managed money, COMEX gold 088691
# ---------------------------------------------------------------------------

def _cot_int(row: dict, key: str) -> int | None:
    v = num(row.get(key))
    return int(round(v)) if v is not None else None


def build_cot() -> dict:
    rows = http_json(COT_URL, timeout=25)
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("CFTC COT returned no gold rows")
    series = []
    for row in rows:
        dt = parse_iso(str(row.get("report_date_as_yyyy_mm_dd") or "").replace(".000", ""))
        if not dt:
            continue
        long_ = _cot_int(row, "m_money_positions_long_all")
        short_ = _cot_int(row, "m_money_positions_short_all")
        if long_ is None or short_ is None:
            continue
        net = long_ - short_
        series.append({
            "date": dt.date().isoformat(),
            "long": long_,
            "short": short_,
            "spread": _cot_int(row, "m_money_positions_spread"),
            "net": net,
            "open_interest": _cot_int(row, "open_interest_all"),
            "pct_long": num(row.get("pct_of_oi_m_money_long_all")),
            "pct_short": num(row.get("pct_of_oi_m_money_short_all")),
            "traders_long": _cot_int(row, "traders_m_money_long_all"),
            "traders_short": _cot_int(row, "traders_m_money_short_all"),
        })
    series.sort(key=lambda x: x["date"])
    if not series:
        raise RuntimeError("CFTC COT parsed no managed-money rows")
    latest = series[-1]
    prev = series[-2] if len(series) > 1 else None
    wow = (latest["net"] - prev["net"]) if prev else None
    as_of = datetime.fromisoformat(latest["date"]).replace(tzinfo=BKK)
    # CFTC typically publishes Friday for the prior Tuesday.
    stamp = now_bkk()
    return {
        "source": "CFTC Disaggregated Futures Only (publicreporting.cftc.gov)",
        "source_url": COT_SOURCE_PAGE,
        "dataset": "72hh-3qpy",
        "contract": "GOLD - COMMODITY EXCHANGE INC.",
        "contract_code": "088691",
        "basis_th": "รายงาน Disaggregated ฝั่งฟิวเจอร์สอย่างเดียว กองทุนบริหาร (Managed Money) สุทธิ = สถานะซื้อ − สถานะขาย ไม่นับสเปรด",
        "basis_en": "Disaggregated Futures Only report. Managed money net = long minus short, excluding spreads.",
        "publication_th": "สำนักงาน CFTC มักเผยแพร่ทุกวันศุกร์ สำหรับข้อมูล ณ วันอังคารก่อนหน้า จึงมีช่วงหน่วงประมาณ T+3 วันทำการ",
        "publication_en": "The CFTC typically publishes each Friday for the prior Tuesday, a lag of about T+3 business days.",
        "as_of": latest["date"],
        "as_of_th": fmt_th(as_of, with_time=False),
        "as_of_en": fmt_en(as_of, with_time=False),
        "updated_at": iso_z(),
        "updated_at_bkk": stamp.strftime("%Y-%m-%d %H:%M"),
        "long": latest["long"],
        "short": latest["short"],
        "spread": latest["spread"],
        "net": latest["net"],
        "wow": wow,
        "wow_side": "up" if (wow or 0) > 0 else ("down" if (wow or 0) < 0 else "flat"),
        "open_interest": latest["open_interest"],
        "pct_long": latest["pct_long"],
        "pct_short": latest["pct_short"],
        "traders_long": latest["traders_long"],
        "traders_short": latest["traders_short"],
        "prev_date": prev["date"] if prev else None,
        "prev_net": prev["net"] if prev else None,
        "series": series[-26:],
    }


# ---------------------------------------------------------------------------
# 3. Fear & Greed
# ---------------------------------------------------------------------------

def rsi_wilder(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    out[period] = 100.0 if avg_l == 0 else 100 - (100 / (1 + avg_g / avg_l))
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if avg_l == 0 else 100 - (100 / (1 + avg_g / avg_l))
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if not values:
        return out
    k = 2 / (period + 1)
    start = min(period - 1, len(values) - 1)
    seed = sum(values[: start + 1]) / (start + 1)
    out[start] = seed
    prev = seed
    for i in range(start + 1, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def scale_mid(value: float, low: float, high: float) -> float:
    """Map low→0, mid 0, high→100 around a center of 50."""
    if high == low:
        return 50.0
    return clamp(50.0 + 50.0 * value / max(abs(low), abs(high)))


def build_feargreed() -> dict:
    candles = load_json(ROOT / "candles.json") or {}
    d1 = (candles.get("candles") or {}).get("D1") or []
    if len(d1) < 70:
        raise RuntimeError("not enough D1 candles for fear & greed")
    # [t, o, h, l, c] t is seconds
    rows = []
    for b in d1:
        if not b or len(b) < 5:
            continue
        t, o, h, l, c = b[0], float(b[1]), float(b[2]), float(b[3]), float(b[4])
        if t < 1e12:
            t *= 1000
        rows.append({"t": int(t), "o": o, "h": h, "l": l, "c": c})
    closes = [r["c"] for r in rows]
    rsi = rsi_wilder(closes, 14)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)

    rets = [0.0]
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append(math.log(closes[i] / closes[i - 1]))
        else:
            rets.append(0.0)

    spdr = load_json(ROOT / "spdr.json") or {}
    spdr_map = {x["date"]: x for x in (spdr.get("series") or []) if x.get("date")}

    def spdr_flow(day: str, lookback: int = 5) -> float | None:
        keys = sorted(d for d in spdr_map if d <= day)
        if len(keys) < lookback + 1:
            return None
        a, b = keys[-(lookback + 1)], keys[-1]
        return num(spdr_map[b].get("tonnes")) - num(spdr_map[a].get("tonnes"))

    history = []
    for i in range(60, len(rows)):
        day = datetime.fromtimestamp(rows[i]["t"] / 1000, tz=timezone.utc).astimezone(BKK).date().isoformat()
        comps: dict[str, float] = {}
        if rsi[i] is not None:
            comps["rsi"] = clamp(rsi[i])
        # Distance from MAs: ±3% maps to 0..100
        dists = []
        px = closes[i]
        if ema20[i]:
            dists.append((px / ema20[i] - 1) / 0.03)
        if ema50[i]:
            dists.append((px / ema50[i] - 1) / 0.03)
        if dists:
            comps["ma"] = clamp(50 + 50 * (sum(dists) / len(dists)))
        # Realized vol 14d vs 60d; high vol → fear
        w14 = rets[i - 13: i + 1]
        w60 = rets[i - 59: i + 1]
        if len(w14) == 14 and len(w60) == 60:
            rv14 = statistics.pstdev(w14) * math.sqrt(252)
            rv60 = statistics.pstdev(w60) * math.sqrt(252)
            if rv60 > 0:
                ratio = rv14 / rv60
                # 0.5 → 100 (calm/greed), 1.0 → 50, 1.8 → 0 (stress/fear)
                comps["volatility"] = clamp(50 - 50 * (ratio - 1.0) / 0.8)
        flow = spdr_flow(day, 5)
        if flow is not None:
            comps["spdr"] = clamp(50 + 50 * (flow / 5.0))
        # Momentum 5d (±3%) and 20d (±6%)
        moms = []
        if i >= 5 and closes[i - 5] > 0:
            moms.append((closes[i] / closes[i - 5] - 1) / 0.03)
        if i >= 20 and closes[i - 20] > 0:
            moms.append((closes[i] / closes[i - 20] - 1) / 0.06)
        if moms:
            comps["momentum"] = clamp(50 + 50 * (sum(moms) / len(moms)))
        if len(comps) < 3:
            continue
        score = round(sum(comps.values()) / len(comps), 1)
        history.append({
            "date": day,
            "score": score,
            "components": {k: round(v, 1) for k, v in comps.items()},
        })
    if not history:
        raise RuntimeError("fear & greed produced no history")

    last = history[-1]
    score = last["score"]
    if score <= 24:
        label_th, label_en, zone = "กลัวสุดขีด", "Extreme Fear", "extreme-fear"
    elif score <= 44:
        label_th, label_en, zone = "กลัว", "Fear", "fear"
    elif score <= 55:
        label_th, label_en, zone = "กลาง ๆ", "Neutral", "neutral"
    elif score <= 74:
        label_th, label_en, zone = "โลภ", "Greed", "greed"
    else:
        label_th, label_en, zone = "โลภสุดขีด", "Extreme Greed", "extreme-greed"

    weights_th = (
        "ดัชนี 0–100 เท่ากับค่าเฉลี่ยอย่างง่ายขององค์ประกอบที่มีข้อมูลในวันนั้น "
        "(น้ำหนักเท่ากัน): "
        "1) RSI รายวัน 14 วัน (ใช้ค่า RSI โดยตรง) "
        "2) ระยะห่างจาก EMA20 และ EMA50 รายวัน โดย ±3% เทียบเท่า 0 หรือ 100 "
        "3) ความผันผวนที่เกิดขึ้นจริง 14 วัน เทียบกับ 60 วัน (ความผันผวนสูง = กลัวมากกว่า) "
        "4) การเปลี่ยนแปลงถือครอง SPDR ย้อนหลัง 5 วันทำการ (±5 ตัน เทียบเท่า 0 หรือ 100) "
        "5) โมเมนตัมราคา 5 วัน (±3%) และ 20 วัน (±6%). "
        "โซน: 0–24 กลัวสุดขีด, 25–44 กลัว, 45–55 กลาง ๆ, 56–74 โลภ, 75–100 โลภสุดขีด. "
        "เป็นดัชนีภายในของ PureGold จากข้อมูลสาธารณะ ไม่ใช่ดัชนี CNN Fear & Greed และไม่ใช่คำแนะนำการลงทุน."
    )
    weights_en = (
        "The 0–100 index is a simple average of whichever components are available that day "
        "(equal weights): "
        "1) 14-day daily RSI (used as-is); "
        "2) distance from the daily EMA20 and EMA50, with ±3% mapped to 0 or 100; "
        "3) 14-day realized volatility versus the 60-day level (higher vol scores as more fear); "
        "4) the 5-session change in SPDR holdings (±5 tonnes maps to 0 or 100); "
        "5) 5-day (±3%) and 20-day (±6%) price momentum. "
        "Zones: 0–24 extreme fear, 25–44 fear, 45–55 neutral, 56–74 greed, 75–100 extreme greed. "
        "This is a PureGold composite from public inputs, not the CNN Fear & Greed Index, and not investment advice."
    )
    stamp = now_bkk()
    as_of = last["date"]
    payload = {
        "source": "PureGold composite (RSI, moving averages, realized volatility, SPDR flows, momentum)",
        "as_of": as_of,
        "as_of_th": fmt_th(datetime.fromisoformat(as_of).replace(tzinfo=BKK), with_time=False),
        "as_of_en": fmt_en(datetime.fromisoformat(as_of).replace(tzinfo=BKK), with_time=False),
        "updated_at": iso_z(),
        "updated_at_bkk": stamp.strftime("%Y-%m-%d %H:%M"),
        "score": score,
        "label_th": label_th,
        "label_en": label_en,
        "zone": zone,
        "components": last["components"],
        "component_labels_th": {
            "rsi": "RSI รายวัน 14 วัน",
            "ma": "ระยะห่างจากเส้นเฉลี่ย",
            "volatility": "ความผันผวน (กลับด้าน)",
            "spdr": "เงินไหลเข้า–ออก SPDR 5 วัน",
            "momentum": "โมเมนตัมราคา",
        },
        "component_labels_en": {
            "rsi": "14-day daily RSI",
            "ma": "Distance from moving averages",
            "volatility": "Realized volatility (inverted)",
            "spdr": "SPDR 5-session flow",
            "momentum": "Price momentum",
        },
        "formula_th": weights_th,
        "formula_en": weights_en,
        "history": [{"date": h["date"], "score": h["score"]} for h in history[-180:]],
    }

    log = ROOT / "history" / "feargreed.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    prev_lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    if not prev_lines or f"\"date\": \"{as_of}\"" not in prev_lines[-1]:
        # replace same-day line if present
        kept = [ln for ln in prev_lines if f"\"date\": \"{as_of}\"" not in ln]
        kept.append(json.dumps({"date": as_of, "score": score, "zone": zone, "components": last["components"]}, ensure_ascii=False))
        log.write_text("\n".join(kept[-400:]) + "\n", encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# 4. Thai vs world gold
# ---------------------------------------------------------------------------

def fetch_usdthb() -> dict:
    errors = []
    # Yahoo first — more timely than the daily open.er-api snapshot
    try:
        j = http_json(YAHOO_THB, timeout=15)
        r = (j.get("chart") or {}).get("result") or []
        if not r:
            raise RuntimeError("empty yahoo chart")
        meta = r[0].get("meta") or {}
        px = num(meta.get("regularMarketPrice"))
        ts = r[0].get("timestamp") or []
        cl = ((r[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        hist = []
        for t, c in zip(ts, cl):
            if c is None:
                continue
            day = datetime.fromtimestamp(int(t), tz=timezone.utc).date().isoformat()
            hist.append({"date": day, "close": round(float(c), 4)})
        if px is None and hist:
            px = hist[-1]["close"]
        prev = hist[-2]["close"] if len(hist) >= 2 else None
        if px is None:
            raise RuntimeError("yahoo THB missing price")
        t_upd = meta.get("regularMarketTime")
        upd = datetime.fromtimestamp(int(t_upd), tz=timezone.utc) if t_upd else datetime.now(timezone.utc)
        return {
            "rate": round(float(px), 4),
            "prev": round(float(prev), 4) if prev is not None else None,
            "source": "Yahoo Finance THB=X",
            "source_url": "https://finance.yahoo.com/quote/THB=X/",
            "as_of": iso_z(upd),
            "as_of_th": fmt_th(upd),
            "as_of_en": fmt_en(upd),
            "history": hist[-10:],
        }
    except Exception as e:
        errors.append(f"yahoo:{e}")
    try:
        j = http_json(ER_API, timeout=12)
        px = num((j.get("rates") or {}).get("THB"))
        if px is None:
            raise RuntimeError("no THB")
        upd = parse_iso(j.get("time_last_update_utc") or "") or datetime.now(timezone.utc)
        return {
            "rate": round(float(px), 4),
            "prev": None,
            "source": "open.er-api.com (ExchangeRate-API)",
            "source_url": ER_API,
            "as_of": iso_z(upd),
            "as_of_th": fmt_th(upd),
            "as_of_en": fmt_en(upd),
            "history": [],
        }
    except Exception as e:
        errors.append(f"er-api:{e}")
    try:
        j = http_json(FRANKFURTER, timeout=12)
        px = num((j.get("rates") or {}).get("THB"))
        if px is None:
            raise RuntimeError("no THB")
        d = j.get("date") or date.today().isoformat()
        upd = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        return {
            "rate": round(float(px), 4),
            "prev": None,
            "source": "Frankfurter (ECB reference)",
            "source_url": FRANKFURTER,
            "as_of": iso_z(upd),
            "as_of_th": fmt_th(upd, with_time=False),
            "as_of_en": fmt_en(upd, with_time=False),
            "history": [],
        }
    except Exception as e:
        errors.append(f"frankfurter:{e}")
    raise RuntimeError("USDTHB failed: " + " | ".join(errors))


def _hsh_row(rows: list, gold_type: str) -> dict | None:
    for r in rows:
        if str(r.get("GoldType") or "").upper() == gold_type and str(r.get("GoldCode") or "").startswith("96"):
            return r
    return None


def theoretical_thb(xau: float, usdthb: float) -> float:
    # User-specified formula: XAUUSD × USDTHB × 15.244g × 0.965 / 31.1035
    return xau * usdthb * BAHT_G * PURITY / OZ_G


def build_compare() -> dict:
    fx = fetch_usdthb()
    hsh = http_json(HSH_URL, timeout=15)
    if not isinstance(hsh, list) or not hsh:
        raise RuntimeError("Hua Seng Heng price feed empty")
    bar = _hsh_row(hsh, "HSH") or _hsh_row(hsh, "REF")
    jewel = _hsh_row(hsh, "JEWEL")
    ref = _hsh_row(hsh, "REF")
    if not bar:
        raise RuntimeError("Hua Seng Heng 96.5% bar row missing")
    buy = num(bar.get("Buy"))
    sell = num(bar.get("Sell"))
    mid = (buy + sell) / 2 if buy is not None and sell is not None else (sell or buy)
    if mid is None:
        raise RuntimeError("Thai bar price missing")

    spot = load_json(ROOT / "spot.json") or {}
    data = load_json(ROOT / "data.json") or {}
    xau = num(spot.get("price")) or num(data.get("price_num")) or first_num(data.get("price"))
    if xau is None:
        raise RuntimeError("no XAUUSD spot for compare")
    usdthb = fx["rate"]
    theo = theoretical_thb(xau, usdthb)
    premium_sell = (sell - theo) if sell is not None else None
    premium_mid = mid - theo
    premium_pct = (premium_mid / theo * 100) if theo else None

    prev_fx = fx.get("prev")
    thb_effect = None
    if prev_fx:
        theo_prev_fx = theoretical_thb(xau, prev_fx)
        thb_effect = theo - theo_prev_fx  # THB per baht-weight due to FX, gold held constant

    def pack_row(r: dict | None) -> dict | None:
        if not r:
            return None
        return {
            "type": r.get("GoldType"),
            "purity": r.get("GoldCode"),
            "buy": num(r.get("Buy")),
            "sell": num(r.get("Sell")),
            "buy_change": num(r.get("BuyChange")),
            "sell_change": num(r.get("SellChange")),
            "time": r.get("TimeUpdate") or r.get("StrTimeUpdate"),
            "time_th": r.get("StrTimeUpdate"),
        }

    thai_upd = parse_iso(bar.get("TimeUpdate") or "") or now_bkk()
    stamp = now_bkk()
    return {
        "formula": "XAUUSD × USDTHB × 15.244 × 0.965 / 31.1035",
        "formula_th": "ราคาทฤษฎีบาทละ (ทองแท่ง 96.5%) = ราคา XAUUSD × อัตรา USDTHB × 15.244 กรัม × 0.965 ÷ 31.1035 กรัมต่อออนซ์",
        "formula_en": "Theoretical 96.5% bar price per baht-weight = XAUUSD × USDTHB × 15.244 g × 0.965 / 31.1035 g per troy ounce.",
        "grams_per_baht": BAHT_G,
        "purity": PURITY,
        "oz_grams": OZ_G,
        "xauusd": round(xau, 3),
        "xauusd_source": spot.get("src") or spot.get("src_label_en") or "spot.json",
        "usdthb": usdthb,
        "usdthb_prev": prev_fx,
        "usdthb_source": fx["source"],
        "usdthb_source_url": fx["source_url"],
        "usdthb_as_of": fx["as_of"],
        "usdthb_as_of_th": fx["as_of_th"],
        "usdthb_as_of_en": fx["as_of_en"],
        "theoretical": round(theo, 2),
        "thai_buy": buy,
        "thai_sell": sell,
        "thai_mid": round(mid, 2),
        "thai_source": "ฮั่วเซ่งเฮง (apicheckprice.huasengheng.com)",
        "thai_source_en": "Hua Seng Heng (apicheckprice.huasengheng.com)",
        "thai_source_url": "https://www.huasengheng.com/",
        "thai_as_of_th": bar.get("StrTimeUpdate") or fmt_th(thai_upd),
        "thai_as_of_en": fmt_en(thai_upd),
        "premium_sell": round(premium_sell, 2) if premium_sell is not None else None,
        "premium_mid": round(premium_mid, 2),
        "premium_pct": round(premium_pct, 3) if premium_pct is not None else None,
        "premium_side": "premium" if premium_mid > 15 else ("discount" if premium_mid < -15 else "fair"),
        "thb_effect": round(thb_effect, 2) if thb_effect is not None else None,
        "thb_effect_th": (
            None if thb_effect is None else
            (f"ค่าเงินบาท{'อ่อน' if thb_effect > 0 else 'แข็ง'} ทำให้ราคาทฤษฎีทองไทย "
             f"{'สูงขึ้น' if thb_effect > 0 else 'ลดลง'} {abs(thb_effect):,.2f} บาท/บาททอง "
             f"แม้ราคา XAUUSD จะเท่าเดิม (เทียบ USDTHB วันก่อนหน้า {prev_fx:.4f})")
        ),
        "thb_effect_en": (
            None if thb_effect is None else
            (f"The baht {'weakened' if thb_effect > 0 else 'strengthened'}, moving the theoretical Thai price "
             f"{'up' if thb_effect > 0 else 'down'} by {abs(thb_effect):,.2f} THB per baht-weight "
             f"even if XAUUSD is unchanged (versus the prior USDTHB close of {prev_fx:.4f}).")
        ),
        "bar": pack_row(bar),
        "ref": pack_row(ref),
        "jewel": pack_row(jewel),
        "updated_at": iso_z(),
        "updated_at_bkk": stamp.strftime("%Y-%m-%d %H:%M"),
        "updated_th": fmt_th(stamp),
        "updated_en": fmt_en(stamp),
    }


# ---------------------------------------------------------------------------
# 5. Morning / evening brief
# ---------------------------------------------------------------------------

def _chg_phrase(n: float | None, unit: str, lang: str) -> str:
    if n is None:
        return "—"
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    body = f"{abs(n):,.2f}"
    if lang == "th":
        side = "เพิ่มขึ้น" if n > 0 else ("ลดลง" if n < 0 else "ไม่เปลี่ยนแปลง")
        return f"{side} {sign}{body} {unit}" if n else f"{side} {body} {unit}"
    side = "up" if n > 0 else ("down" if n < 0 else "unchanged")
    return f"{side} {sign}{body} {unit}"


def template_brief(kind: str, facts: dict) -> dict:
    px = facts.get("price")
    chg = facts.get("change")
    pct = facts.get("change_pct")
    src = facts.get("price_source_th") if True else ""
    s1, r1 = facts.get("support"), facts.get("resistance")
    spdr_line_th = facts.get("spdr_th")
    spdr_line_en = facts.get("spdr_en")
    ev_th, ev_en = facts.get("event_th"), facts.get("event_en")
    fg_th, fg_en = facts.get("fg_th"), facts.get("fg_en")
    cot_th, cot_en = facts.get("cot_th"), facts.get("cot_en")
    bias_th, bias_en = facts.get("bias_th"), facts.get("bias_en")
    stamp_th, stamp_en = facts.get("session_th"), facts.get("session_en")
    cmp_th, cmp_en = facts.get("compare_th"), facts.get("compare_en")

    chg_th = "—"
    chg_en = "—"
    if chg is not None and pct is not None:
        if chg > 0:
            chg_th = f"บวก {chg:,.2f} ดอลลาร์ ({pct:+.2f}%)"
            chg_en = f"up {chg:,.2f} ({pct:+.2f}%)"
        elif chg < 0:
            chg_th = f"ลบ {abs(chg):,.2f} ดอลลาร์ ({pct:+.2f}%)"
            chg_en = f"down {abs(chg):,.2f} ({pct:+.2f}%)"
        else:
            chg_th = "ทรงตัว (0.00%)"
            chg_en = "unchanged (0.00%)"

    head_th = "สรุปตลาดเช้า" if kind == "morning" else "สรุปตลาดเย็น"
    head_en = "Morning market brief" if kind == "morning" else "Evening market brief"
    th = (
        f"{head_th} {stamp_th}. ราคาทองโลก XAUUSD อยู่ที่ {px:,.2f} ดอลลาร์ต่อออนซ์ ({chg_th}) "
        f"แหล่งราคา {facts.get('price_source_th')}. มุมมองระบบ: {bias_th}. "
        f"แนวรับใกล้สุดประมาณ {facts.get('support')} และแนวต้านใกล้สุดประมาณ {facts.get('resistance')}. "
        f"{spdr_line_th} {cot_th} {fg_th} {cmp_th} {ev_th} "
        "ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน."
    )
    en = (
        f"{head_en}, {stamp_en}. Spot XAUUSD is at {px:,.2f} an ounce ({chg_en}), "
        f"source {facts.get('price_source_en')}. System view: {bias_en}. "
        f"Nearest support is around {facts.get('support_en') or s1} and nearest resistance around {facts.get('resistance_en') or r1}. "
        f"{spdr_line_en} {cot_en} {fg_en} {cmp_en} {ev_en} "
        "For education only — not investment advice."
    )
    th = re.sub(r"\s{2,}", " ", th).strip()
    en = re.sub(r"\s{2,}", " ", en).strip()
    return {"th": th, "en": en, "via": "template"}


def collect_facts(kind: str, cal, cot, fg, cmp) -> dict:
    spot = load_json(ROOT / "spot.json") or {}
    data = load_json(ROOT / "data.json") or {}
    spdr = load_json(ROOT / "spdr.json") or {}
    px = num(spot.get("price")) or num(data.get("price_num")) or first_num(data.get("price"))
    candles = load_json(ROOT / "candles.json") or {}
    d1 = (candles.get("candles") or {}).get("D1") or []
    change = change_pct = None
    if px is not None and len(d1) >= 2:
        prev = float(d1[-2][4])
        # If last bar is today, previous close is d1[-2]; if last is still yesterday, use that close
        last_c = float(d1[-1][4])
        last_t = d1[-1][0] * (1000 if d1[-1][0] < 1e12 else 1)
        last_day = datetime.fromtimestamp(last_t / 1000, tz=timezone.utc).astimezone(BKK).date()
        today = now_bkk().date()
        ref = prev if last_day == today else last_c
        if last_day == today:
            ref = prev
        else:
            ref = last_c
        change = round(px - ref, 2)
        change_pct = round((px / ref - 1) * 100, 2) if ref else None
    support = (data.get("support") or ["—"])[0]
    resistance = (data.get("resistance") or ["—"])[0]
    support_en = (data.get("support_en") or data.get("support") or ["—"])[0]
    resistance_en = (data.get("resistance_en") or data.get("resistance") or ["—"])[0]
    bias_th = str(data.get("bias") or "—")
    bias_en = str(data.get("bias_en") or bias_th)
    # shorten bias for the brief
    if " · " in bias_th:
        bias_th_short = bias_th.split(" · ")[0] + " · " + " · ".join(bias_th.split(" · ")[1:3])
    else:
        bias_th_short = bias_th
    if " · " in bias_en:
        bias_en_short = " · ".join(bias_en.split(" · ")[:3])
    else:
        bias_en_short = bias_en

    spdr_th = spdr_en = ""
    if spdr and spdr.get("tonnes") is not None:
        ch = num(spdr.get("change")) or 0
        side_th = "ซื้อเข้า" if ch > 0 else ("ขายออก" if ch < 0 else "ไม่เปลี่ยนแปลง")
        side_en = "bought" if ch > 0 else ("sold" if ch < 0 else "unchanged")
        spdr_th = (
            f"กองทุน SPDR Gold Trust ถือครอง {spdr['tonnes']:,.2f} ตัน ณ {spdr.get('as_of_th') or spdr.get('as_of')} "
            f"{side_th} {abs(ch):,.2f} ตัน ในรอบข้อมูลล่าสุด (ประกาศแบบ T+1)."
        )
        spdr_en = (
            f"SPDR Gold Trust held {spdr['tonnes']:,.2f} tonnes as of {spdr.get('as_of_en') or spdr.get('as_of')}, "
            f"{side_en} {abs(ch):,.2f} tonnes in the latest reported session (published T+1)."
        )

    cot_th = cot_en = ""
    if cot and cot.get("net") is not None:
        wow = cot.get("wow")
        wow_th = "" if wow is None else f" เปลี่ยนแปลงรายสัปดาห์ {format(wow, "+,")} สัญญา"
        wow_en = "" if wow is None else f", week-on-week {format(wow, "+,")} contracts"
        cot_th = f"กองทุนบริหาร (CFTC Managed Money) สุทธิ {cot['net']:,} สัญญา ณ {cot.get('as_of_th')}.{wow_th}."
        cot_en = f"CFTC managed money net is {cot['net']:,} contracts as of {cot.get('as_of_en')}{wow_en}."

    fg_th = fg_en = ""
    if fg and fg.get("score") is not None:
        fg_th = f"ดัชนีความกลัวและความโลภของทองอยู่ที่ {fg['score']:.0f} ({fg.get('label_th')}) ณ {fg.get('as_of_th')}."
        fg_en = f"The gold fear-and-greed composite is {fg['score']:.0f} ({fg.get('label_en')}) as of {fg.get('as_of_en')}."

    ev_th = ev_en = ""
    upcoming = []
    if cal:
        now = now_bkk()
        for e in cal.get("events") or []:
            dt = parse_iso(e.get("date_utc") or "")
            if dt and dt >= now - timedelta(minutes=15):
                upcoming.append((dt, e))
        upcoming.sort(key=lambda x: x[0])
        # prefer high impact
        high = [x for x in upcoming if x[1].get("impact") == "high"]
        pick = (high or upcoming)[:2]
        if pick:
            bits_th, bits_en = [], []
            for dt, e in pick:
                bits_th.append(f"{e.get('title_th') or e.get('title')} วันที่ {e.get('date_th')} (ผลกระทบ {e.get('impact')})")
                bits_en.append(f"{e.get('title_en') or e.get('title')} at {e.get('date_en')} ({e.get('impact')} impact)")
            ev_th = "ปฏิทินข่าวถัดไป: " + "; ".join(bits_th) + "."
            ev_en = "Upcoming calendar: " + "; ".join(bits_en) + "."
        else:
            ev_th = "ช่วงนี้ยังไม่มีข่าวสหรัฐฯ แรงในปฏิทินที่กรองไว้."
            ev_en = "No further high-impact US gold events remain on the filtered calendar."

    cmp_th = cmp_en = ""
    if cmp and cmp.get("theoretical") is not None and cmp.get("thai_sell") is not None:
        prem = cmp.get("premium_sell") or 0
        side = "พรีเมียม" if prem > 15 else ("ส่วนลด" if prem < -15 else "ใกล้เคียงค่าทฤษฎี")
        cmp_th = (
            f"ทองแท่งไทย 96.5% ขาย {cmp['thai_sell']:,.0f} บาทต่อบาททอง เทียบค่าทฤษฎี {cmp['theoretical']:,.0f} บาท "
            f"({side} {prem:+,.0f} บาท) อัตรา USDTHB {cmp.get('usdthb')}."
        )
        side_en = "a premium of" if prem > 15 else ("a discount of" if prem < -15 else "close to theory, difference")
        cmp_en = (
            f"Thai 96.5% bar gold is offered at {cmp['thai_sell']:,.0f} THB per baht-weight versus a theoretical "
            f"{cmp['theoretical']:,.0f} THB ({side_en} {prem:+,.0f} THB), with USDTHB at {cmp.get('usdthb')}."
        )

    stamp = now_bkk()
    return {
        "kind": kind,
        "price": px,
        "change": change,
        "change_pct": change_pct,
        "price_source_th": spot.get("src_label_th") or "สปอต FX",
        "price_source_en": spot.get("src_label_en") or "FX spot",
        "support": support,
        "resistance": resistance,
        "support_en": support_en,
        "resistance_en": resistance_en,
        "bias_th": bias_th_short,
        "bias_en": bias_en_short,
        "spdr_th": spdr_th,
        "spdr_en": spdr_en,
        "cot_th": cot_th,
        "cot_en": cot_en,
        "fg_th": fg_th,
        "fg_en": fg_en,
        "event_th": ev_th,
        "event_en": ev_en,
        "compare_th": cmp_th,
        "compare_en": cmp_en,
        "session_th": fmt_th(stamp),
        "session_en": fmt_en(stamp),
        "accuracy": (data.get("accuracy") or {}),
    }


def phrase_with_openrouter(kind: str, facts: dict, fallback: dict) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY")
    if not key:
        return fallback
    payload_facts = {
        k: facts[k] for k in facts
        if k in {
            "kind", "price", "change", "change_pct", "price_source_th", "price_source_en",
            "support", "resistance", "bias_th", "bias_en", "spdr_th", "spdr_en",
            "cot_th", "cot_en", "fg_th", "fg_en", "event_th", "event_en",
            "compare_th", "compare_en", "session_th", "session_en",
        }
    }
    sys_msg = (
        "You write a concise gold-market brief for PureGold by PureFxAi. "
        "Return ONLY compact JSON with keys th and en. "
        "Use only the provided facts. Do not invent prices, dates, flows, or events. "
        "4 to 6 short professional sentences per language. No hype, no emoji, "
        "never the Thai word อลังการ. End with a one-line education-only disclaimer. "
        "Times are already in Asia/Bangkok."
    )
    body = {
        "models": OR_MODELS,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": json.dumps(payload_facts, ensure_ascii=False)},
        ],
        "temperature": 0.25,
        "max_tokens": 700,
    }
    # some routers don't support `models` array — try first model, then fallbacks
    last_err = None
    for model in OR_MODELS:
        try:
            req_body = dict(body)
            req_body.pop("models", None)
            req_body["model"] = model
            data = json.dumps(req_body).encode("utf-8")
            req = urllib.request.Request(
                OPENROUTER,
                data=data,
                method="POST",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "User-Agent": UA,
                    "HTTP-Referer": "https://dashboard.purefxai.store/",
                    "X-Title": "PureGold brief",
                },
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                resp = json.loads(r.read().decode("utf-8"))
            text = (((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            if not text:
                raise RuntimeError("empty content")
            m = re.search(r"\{.*\}", text, re.S)
            obj = json.loads(m.group() if m else text)
            th, en = (obj.get("th") or "").strip(), (obj.get("en") or "").strip()
            if len(th) < 40 or len(en) < 40:
                raise RuntimeError("brief too short")
            # Reject if the model dropped the live price entirely
            if facts.get("price") and f"{facts['price']:.0f}" not in th and f"{facts['price']:,.0f}" not in th:
                # still accept if formatted differently
                if str(int(facts["price"])) not in th:
                    raise RuntimeError("model omitted the spot price")
            return {"th": th, "en": en, "via": f"openrouter:{model}"}
        except Exception as e:
            last_err = e
            continue
    print(f"[insights] openrouter brief skipped ({last_err})", file=sys.stderr)
    return fallback


def build_brief(cal, cot, fg, cmp) -> dict:
    path = ROOT / "brief.json"
    prev = load_json(path) or {"briefs": {}}
    briefs = prev.get("briefs") or {}
    today = now_bkk().date().isoformat()
    hour = now_bkk().hour
    wanted = []
    if hour >= 8:
        wanted.append("morning")
    if hour >= 20:
        wanted.append("evening")
    # Always refresh the latest due slot (so a 10-minute cadence can tighten numbers
    # in the same session window, but do not invent a future session).
    changed = False
    for kind in wanted:
        key = f"{today}-{kind}"
        existing = briefs.get(key)
        # Refresh if missing, or same session and older than 50 minutes, or forced.
        stale = True
        if existing and existing.get("generated_at"):
            gen = parse_iso(existing["generated_at"])
            if gen and (now_bkk() - gen.astimezone(BKK)) < timedelta(minutes=50) and not os.environ.get("BRIEF_FORCE"):
                stale = False
        if not stale:
            continue
        facts = collect_facts(kind, cal, cot, fg, cmp)
        if facts.get("price") is None:
            print("[insights] brief skipped: no price", file=sys.stderr)
            continue
        templ = template_brief(kind, facts)
        text = phrase_with_openrouter(kind, facts, templ)
        entry = {
            "id": key,
            "date": today,
            "session": kind,
            "session_th": "เช้า" if kind == "morning" else "เย็น",
            "session_en": "Morning" if kind == "morning" else "Evening",
            "generated_at": iso_z(),
            "generated_at_bkk": now_bkk().strftime("%Y-%m-%d %H:%M"),
            "generated_th": fmt_th(now_bkk()),
            "generated_en": fmt_en(now_bkk()),
            "price": facts["price"],
            "change": facts["change"],
            "change_pct": facts["change_pct"],
            "text_th": text["th"],
            "text_en": text["en"],
            "via": text.get("via") or "template",
        }
        briefs[key] = entry
        changed = True

    # Drop entries older than 14 days
    cutoff = (now_bkk().date() - timedelta(days=14)).isoformat()
    briefs = {k: v for k, v in briefs.items() if str(v.get("date") or "") >= cutoff}
    # Pointers
    morning = briefs.get(f"{today}-morning") or prev.get("morning")
    evening = briefs.get(f"{today}-evening") or prev.get("evening")
    # latest = most recent generated
    ordered = sorted(briefs.values(), key=lambda x: x.get("generated_at") or "", reverse=True)
    latest = ordered[0] if ordered else None
    stamp = now_bkk()
    out = {
        "timezone": "Asia/Bangkok",
        "schedule_th": "สร้างอัตโนมัติเวลา 08:00 น. และ 20:00 น. เวลาไทย จากข้อมูลจริงบนแดชบอร์ด",
        "schedule_en": "Generated automatically at 08:00 and 20:00 Asia/Bangkok from live desk data.",
        "updated_at": iso_z(),
        "updated_at_bkk": stamp.strftime("%Y-%m-%d %H:%M"),
        "morning": morning if morning and morning.get("date") == today else morning,
        "evening": evening if evening and evening.get("date") == today else evening,
        "latest": latest,
        "briefs": briefs,
    }
    if not changed and path.exists() and prev.get("briefs"):
        # still refresh pointers / timestamps lightly without wiping text
        prev.update({
            "updated_at": out["updated_at"],
            "updated_at_bkk": out["updated_at_bkk"],
            "morning": out["morning"],
            "evening": out["evening"],
            "latest": out["latest"],
            "briefs": briefs,
        })
        return prev
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run_one(name: str, path: Path, fn):
    try:
        data = fn()
        write_json(path, data)
        print(f"[insights] wrote {path.name}")
        return data
    except Exception as e:
        keep(path, name, e)
        return load_json(path)


def main() -> int:
    cal = run_one("calendar", ROOT / "events.json", build_calendar)
    cot = run_one("cot", ROOT / "cot.json", build_cot)
    fg = run_one("feargreed", ROOT / "feargreed.json", build_feargreed)
    cmp = run_one("compare", ROOT / "compare.json", build_compare)

    def _brief():
        return build_brief(cal, cot, fg, cmp)

    run_one("brief", ROOT / "brief.json", _brief)
    return 0


if __name__ == "__main__":
    sys.exit(main())
