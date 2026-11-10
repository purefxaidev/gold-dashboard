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


def parse_rows(blob: bytes) -> list[tuple[dt.date, float, float | None]]:
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
    try:
        i_date = header.index("Date")
        i_tonnes = header.index("Tonnes of Gold")
    except ValueError as e:
        raise RuntimeError(f"unexpected columns: {header}") from e
    i_oz = header.index("Total Ounces of Gold in the Trust") if "Total Ounces of Gold in the Trust" in header else None
    out: list[tuple[dt.date, float, float | None]] = []
    for raw in rows[1:]:
        if not raw:
            continue
        day = parse_date(raw[i_date] if i_date < len(raw) else None)
        tonnes = raw[i_tonnes] if i_tonnes < len(raw) else None
        if day is None or not is_num(tonnes) or tonnes <= 0:
            continue
        oz = None
        if i_oz is not None and i_oz < len(raw) and is_num(raw[i_oz]):
            oz = float(raw[i_oz])
        out.append((day, float(tonnes), oz))
    out.sort(key=lambda x: x[0])
    if len(out) < 20:
        raise RuntimeError(f"too few trading sessions parsed: {len(out)}")
    return out


def on_or_before(series: list[tuple[dt.date, float, float | None]], target: dt.date):
    for day, tonnes, oz in reversed(series):
        if day <= target:
            return day, tonnes, oz
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
    chg = r2(tonnes - ref[1])
    item = {
        "from": ref[0].isoformat(),
        "from_tonnes": r2(ref[1]),
        "change": chg,
        "side": side_of(chg),
    }
    if key_days is not None:
        item["days"] = key_days
    return item


def build_payload(series, fetched_at: dt.datetime) -> dict:
    as_of, tonnes, oz = series[-1]
    prev_date, prev_tonnes, _ = series[-2]
    change = r2(tonnes - prev_tonnes)
    start = as_of - dt.timedelta(days=SERIES_DAYS)
    daily = []
    prev_t = None
    # include one extra prior point so the first visible change is correct
    window = [row for row in series if row[0] >= start - dt.timedelta(days=14)]
    if len(window) < 2:
        window = series[-260:]
    for day, t, _oz in window:
        chg = None if prev_t is None else r2(t - prev_t)
        if day >= start:
            daily.append({"date": day.isoformat(), "tonnes": r2(t), "change": chg})
        prev_t = t
    # ensure first change is filled from the session immediately before the window
    if daily and daily[0]["change"] is None:
        before = on_or_before(series, daily[0]["date"])
        # find previous session
        idx = next(i for i, row in enumerate(series) if row[0] == dt.date.fromisoformat(daily[0]["date"]))
        if idx > 0:
            daily[0]["change"] = r2(series[idx][1] - series[idx - 1][1])
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
        "periods": {
            "1W": period(series, as_of, tonnes, 7),
            "1M": period(series, as_of, tonnes, 30),
            "3M": period(series, as_of, tonnes, 90),
            "YTD": period(series, as_of, tonnes, None, ytd=True),
            "1Y": period(series, as_of, tonnes, 365),
        },
        "series": daily,
        "note_th": (
            "การเปลี่ยนแปลงรายวันของปริมาณทองคำที่กองทุน SPDR Gold Trust (GLD) ถือครอง มีหน่วยเป็นตัน "
            "ค่าบวกหมายถึงทองถูกซื้อเข้าหรือสร้างหน่วยใหม่ ค่าลบหมายถึงทองถูกขายออกหรือไถ่ถอน "
            "วันที่อ้างอิงคือรอบการซื้อขายล่าสุดที่กองทุนเผยแพร่ ไม่ใช่ตัวเลขสด"
        ),
        "note_en": (
            "Daily change in official tonnes of gold held by SPDR Gold Trust (GLD). "
            "Positive = gold added (creations / buying). Negative = gold removed (redemptions / selling). "
            "The as-of date is the Trust's last published US trading session, not a live figure."
        ),
    }
    return payload


def core_fingerprint(payload: dict) -> dict:
    return {
        "as_of": payload.get("as_of"),
        "tonnes": payload.get("tonnes"),
        "change": payload.get("change"),
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
