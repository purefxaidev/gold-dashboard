#!/usr/bin/env python3
"""Fetch official SPDR Gold Trust (GLD) daily holdings and write spdr.json.

Source: SPDR Gold Shares historical archive (XLSX)
  https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en

Daily change is the difference in official tonnes held versus the previous
US trading session (positive = gold added / creations, negative = gold
removed / redemptions). Period totals use the last session on or before
the start of each window. Times in this file are Asia/Bangkok unless a
field is explicitly a US session date (as_of).

If the official file cannot be downloaded, the last good spdr.json is kept.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

BKK = ZoneInfo("Asia/Bangkok")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "spdr.json"

ARCHIVE_URL = (
    "https://api.spdrgoldshares.com/api/v1/historical-archive"
    "?product=gld&exchange=NYSE&lang=en"
)
SOURCE_PAGE = "https://www.spdrgoldshares.com/usa/gld/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/octet-stream,*/*",
    "Origin": "https://www.spdrgoldshares.com",
    "Referer": "https://www.spdrgoldshares.com/usa/gld/",
}

TH_MONTHS = "ม.ค. ก.พ. มี.ค. เม.ย. พ.ค. มิ.ย. ก.ค. ส.ค. ก.ย. ต.ค. พ.ย. ธ.ค.".split()
EN_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
SHEET = "US GLD Historical Archive"
SERIES_DAYS = 370
OZ_PER_TONNE = 32150.75  # troy ounces per metric tonne, as used for approx. flow value
ARCHIVE_COLUMNS_NOTE = (
    "The official US GLD Historical Archive no longer includes an LBMA Gold Price column. "
    "A Disclaimer sheet in the same workbook states the LBMA Gold Price was removed at the "
    "request of ICE Benchmark Administration."
)


def now_bkk() -> dt.datetime:
    return dt.datetime.now(BKK)


def fmt_th_date(d: dt.date) -> str:
    return f"{d.day} {TH_MONTHS[d.month - 1]} {d.year}"


def fmt_en_date(d: dt.date) -> str:
    return f"{d.day} {EN_MONTHS[d.month - 1]} {d.year}"


def r2(n: float) -> float:
    return round(float(n) + 0.0, 2)


def parse_date(v) -> dt.date | None:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()
    if not s or "holiday" in s.lower():
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def download_archive() -> bytes:
    req = urllib.request.Request(ARCHIVE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=45) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        data = r.read()
        if "pdf" in ctype or data[:4] == b"%PDF":
            raise RuntimeError(f"archive returned PDF, not XLSX (content-type={ctype!r})")
        if data[:2] != b"PK":
            raise RuntimeError(f"archive is not an XLSX zip (content-type={ctype!r}, start={data[:40]!r})")
        return data


def col_idx(header: list[str], *names: str) -> int | None:
    for n in names:
        if n in header:
            return header.index(n)
    return None


def cell(raw, idx) -> float | None:
    if idx is None or idx >= len(raw):
        return None
    v = raw[idx]
    return float(v) if is_num(v) else None


def implied_gold_usd(row: dict) -> float | None:
    """Gold price implied by official NAV fields. Not an LBMA PM print and not an execution price."""
    nav = row.get("nav_total")
    oz = row.get("ounces")
    if nav and oz:
        return round(nav / oz, 3)
    nav_sh = row.get("nav_per_share")
    oz_sh = row.get("oz_per_share")
    if nav_sh and oz_sh:
        return round(nav_sh / oz_sh, 3)
    return None


def flow_value_usd(change_tonnes: float | None, price: float | None) -> float | None:
    if change_tonnes is None or price is None:
        return None
    return round(float(change_tonnes) * OZ_PER_TONNE * float(price), 0)


def parse_rows(blob: bytes) -> list[dict]:
    bio = io.BytesIO(blob)
    wb = load_workbook(bio, data_only=True, read_only=True)
    if SHEET not in wb.sheetnames:
        wb.close()
        raise RuntimeError(f"missing sheet {SHEET!r}; have {wb.sheetnames}")
    ws = wb[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise RuntimeError("empty archive sheet")
    header = [str(c or "").strip() for c in rows[0]]
    i_date = col_idx(header, "Date")
    i_tonnes = col_idx(header, "Tonnes of Gold")
    if i_date is None or i_tonnes is None:
        raise RuntimeError(f"unexpected columns: {header}")
    # Official workbook no longer has an LBMA Gold Price / London Fix column
    # (Disclaimer sheet: removed at the request of ICE Benchmark Administration).
    lbma_names = [h for h in header if "lbma" in h.lower() or "london fix" in h.lower() or h.lower() in ("gold price", "gold price pm")]
    i_oz = col_idx(header, "Total Ounces of Gold in the Trust")
    i_nav = col_idx(header, "Total Net Asset Value in the Trust")
    i_nav_sh = col_idx(header, "NAV/Share at 10:30am NYT", "NAV/Share")
    i_oz_sh = col_idx(header, "Ounces of Gold per Share")
    i_close = col_idx(header, "Closing Price")
    out: list[dict] = []
    for raw in rows[1:]:
        if not raw:
            continue
        day = parse_date(raw[i_date] if i_date < len(raw) else None)
        tonnes = raw[i_tonnes] if i_tonnes < len(raw) else None
        if day is None or not is_num(tonnes) or tonnes <= 0:
            continue
        rec = {
            "day": day,
            "tonnes": float(tonnes),
            "ounces": cell(raw, i_oz),
            "nav_total": cell(raw, i_nav),
            "nav_per_share": cell(raw, i_nav_sh),
            "oz_per_share": cell(raw, i_oz_sh),
            "gld_close": cell(raw, i_close),
        }
        rec["implied_gold_usd"] = implied_gold_usd(rec)
        out.append(rec)
    out.sort(key=lambda x: x["day"])
    if len(out) < 20:
        raise RuntimeError(f"too few trading sessions parsed: {len(out)}")
    return out


def on_or_before(series: list[dict], target: dt.date):
    for rec in reversed(series):
        if rec["day"] <= target:
            return rec
    return None


def side_of(change: float) -> str:
    if change > 0.0005:
        return "buy"
    if change < -0.0005:
        return "sell"
    return "flat"


def period(series, as_of: dt.date, tonnes: float, days: int | None, ytd: bool = False) -> dict:
    if ytd:
        target = dt.date(as_of.year - 1, 12, 31)
        key_days = None
    else:
        target = as_of - dt.timedelta(days=days or 0)
        key_days = days
    ref = on_or_before(series, target)
    if ref is None:
        raise RuntimeError(f"no reference session on or before {target.isoformat()}")
    chg = r2(tonnes - ref["tonnes"])
    item = {
        "from": ref["day"].isoformat(),
        "from_tonnes": r2(ref["tonnes"]),
        "change": chg,
        "side": side_of(chg),
    }
    if key_days is not None:
        item["days"] = key_days
    return item


def session_point(rec: dict, change: float | None) -> dict:
    px = rec.get("implied_gold_usd")
    pt = {
        "date": rec["day"].isoformat(),
        "tonnes": r2(rec["tonnes"]),
        "change": change,
        "implied_gold_usd": px,
        "nav_per_share": rec.get("nav_per_share"),
        "nav_total": rec.get("nav_total"),
        "gld_close": rec.get("gld_close"),
        "flow_value_usd": flow_value_usd(change, px) if change is not None else None,
    }
    return pt


def build_payload(series, fetched_at: dt.datetime) -> dict:
    last, prev = series[-1], series[-2]
    as_of, tonnes, oz = last["day"], last["tonnes"], last.get("ounces")
    prev_date, prev_tonnes = prev["day"], prev["tonnes"]
    change = r2(tonnes - prev_tonnes)
    start = as_of - dt.timedelta(days=SERIES_DAYS)
    daily = []
    prev_t = None
    window = [row for row in series if row["day"] >= start - dt.timedelta(days=14)]
    if len(window) < 2:
        window = series[-260:]
    for rec in window:
        t = rec["tonnes"]
        chg = None if prev_t is None else r2(t - prev_t)
        if rec["day"] >= start:
            daily.append(session_point(rec, chg))
        prev_t = t
    if daily and daily[0]["change"] is None:
        idx = next(i for i, row in enumerate(series) if row["day"] == dt.date.fromisoformat(daily[0]["date"]))
        if idx > 0:
            chg = r2(series[idx]["tonnes"] - series[idx - 1]["tonnes"])
            daily[0]["change"] = chg
            daily[0]["flow_value_usd"] = flow_value_usd(chg, daily[0].get("implied_gold_usd"))
    implied = last.get("implied_gold_usd")
    payload = {
        "ticker": "GLD",
        "name": "SPDR Gold Trust",
        "unit": "tonnes",
        "source": "SPDR Gold Shares official historical archive",
        "source_url": SOURCE_PAGE,
        "archive_url": ARCHIVE_URL,
        "as_of": as_of.isoformat(),
        "as_of_th": fmt_th_date(as_of),
        "as_of_en": fmt_en_date(as_of),
        "as_of_label_th": f"{fmt_th_date(as_of)} (รอบการซื้อขายสหรัฐฯ)",
        "as_of_label_en": f"{fmt_en_date(as_of)} (US trading session)",
        "updated_at": fetched_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at_bkk": fetched_at.astimezone(BKK).strftime("%Y-%m-%d %H:%M"),
        "cached": False,
        "tonnes": r2(tonnes),
        "ounces": None if oz is None else r2(oz),
        "prev_date": prev_date.isoformat(),
        "prev_tonnes": r2(prev_tonnes),
        "change": change,
        "change_pct": r2((change / prev_tonnes) * 100) if prev_tonnes else 0.0,
        "side": side_of(change),
        "gld_close": last.get("gld_close"),
        "oz_per_share": last.get("oz_per_share"),
        "nav_per_share": last.get("nav_per_share"),
        "nav_total": last.get("nav_total"),
        "lbma_pm": None,
        "lbma_pm_available": False,
        "lbma_pm_note_th": (
            "คลังข้อมูลทางการของ SPDR (US GLD Historical Archive) ได้ถอดคอลัมน์ LBMA Gold Price ออกตามคำขอของ "
            "ICE Benchmark Administration จึงไม่มีตัวเลข LBMA PM ในไฟล์ทางการ"
        ),
        "lbma_pm_note_en": ARCHIVE_COLUMNS_NOTE,
        "implied_gold_usd": implied,
        "implied_gold_method": "total_nav_div_total_ounces",
        "implied_gold_label_th": "ราคาทองคำโดยนัยจาก NAV ของกองทุน (ไม่ใช่ราคาซื้อจริง)",
        "implied_gold_label_en": "Gold price implied from the Trust NAV (not an execution price)",
        "implied_gold_note_th": (
            "คำนวณจากมูลค่าสินทรัพย์สุทธิรวม ÷ จำนวนออนซ์ในคลังข้อมูลทางการของวันซื้อขายนั้น "
            "ไม่ใช่ราคาที่กองทุนซื้อหรือขายจริง และไม่ใช่ตัวเลข LBMA Gold Price PM โดยตรง "
            "เพราะคอลัมน์นั้นถูกถอดออกจากไฟล์ทางการ"
        ),
        "implied_gold_note_en": (
            "Derived from official Total Net Asset Value divided by Total Ounces of Gold in the Trust "
            "on that trade date. This is not the Trust's execution price, and it is not a direct LBMA Gold Price PM print "
            "(that column was removed from the official archive)."
        ),
        "flow_value_usd": flow_value_usd(change, implied),
        "flow_value_method": "change_tonnes * 32150.75 oz * implied_gold_usd",
        "oz_per_tonne": OZ_PER_TONNE,
        "periods": {
            "1W": period(series, as_of, tonnes, 7),
            "1M": period(series, as_of, tonnes, 30),
            "3M": period(series, as_of, tonnes, 90),
            "YTD": period(series, as_of, tonnes, None, ytd=True),
            "1Y": period(series, as_of, tonnes, 365),
        },
        "series": daily,
        "basis": "trade_date",
        "basis_th": "ปริมาณตามวันที่ซื้อขาย (trade date) ไม่ใช่วันชำระราคา",
        "basis_en": "Holdings are on a trade-date basis, not settlement date.",
        "publication_th": "คลังข้อมูลทางการมักเผยแพร่เช้าวันถัดไปตามเวลานิวยอร์ก จึงไม่ใช่ตัวเลขสดของวันนี้ รายการแท่งทองเป็นฐานวันชำระ (T+1) ส่วนตัวเลขนี้เป็นวันซื้อขาย",
        "publication_en": "The official archive is typically published the next morning New York time, so this is not a live same-day figure. The bar list is settlement-date (T+1); this print is trade-date.",
        "note_th": (
            "การเปลี่ยนแปลงรายวันของปริมาณทองคำที่กองทุน SPDR Gold Trust (GLD) ถือครอง มีหน่วยเป็นตัน "
            "ค่าบวกหมายถึงทองถูกซื้อเข้าหรือสร้างหน่วยใหม่ ค่าลบหมายถึงทองถูกขายออกหรือไถ่ถอน "
            "วันที่อ้างอิงคือวันที่ซื้อขายล่าสุดในคลังข้อมูลทางการ (trade date) ซึ่งมักเผยแพร่เช้าวันถัดไปตามเวลานิวยอร์ก ไม่ใช่ตัวเลขสด"
        ),
        "note_en": (
            "Daily change in official tonnes of gold held by SPDR Gold Trust (GLD). "
            "Positive = gold added (creations / buying). Negative = gold removed (redemptions / selling). "
            "The as-of date is the last official trade date, typically published the next morning New York time, not a live figure."
        ),
    }
    return payload


def core_fingerprint(payload: dict) -> dict:
    return {
        "as_of": payload.get("as_of"),
        "tonnes": payload.get("tonnes"),
        "change": payload.get("change"),
        "implied_gold_usd": payload.get("implied_gold_usd"),
        "nav_per_share": payload.get("nav_per_share"),
        "periods": payload.get("periods"),
        "series": payload.get("series"),
    }


def write_json(payload: dict) -> None:
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUT)


def keep_cache(reason: str) -> int:
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = None
        if isinstance(prev, dict) and prev.get("tonnes"):
            print(f"spdr.py: {reason}; keeping last good data as of {prev.get('as_of')}", file=sys.stderr)
            return 0
    print(f"spdr.py: {reason}; no cached spdr.json to keep", file=sys.stderr)
    return 0


def main() -> int:
    try:
        blob = download_archive()
        series = parse_rows(blob)
        payload = build_payload(series, now_bkk())
    except Exception as e:
        return keep_cache(f"fetch/parse failed ({e})")

    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            if core_fingerprint(old) == core_fingerprint(payload):
                print(
                    f"spdr.py: unchanged {payload['as_of']} {payload['tonnes']} t "
                    f"({payload['side']} {payload['change']:+.2f})"
                )
                return 0
        except Exception:
            pass
    write_json(payload)
    print(
        f"spdr.py: {payload['as_of']} {payload['tonnes']} t "
        f"{payload['side']} {payload['change']:+.2f} t "
        f"YTD {payload['periods']['YTD']['change']:+.2f} t "
        f"({len(payload['series'])} daily points)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
