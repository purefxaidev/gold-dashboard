#!/usr/bin/env python3
"""Send PureGold Web Push from the box loop. Subscriptions live on the box;
the public GitHub Pages site cannot accept POSTs, so a collector URL is still required
to ingest iPhone subscriptions into subscriptions.json."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

BKK = ZoneInfo("Asia/Bangkok")
SECRETS = Path(os.environ.get("PG_VAPID_FILE", "/home/box/secrets/vapid.json"))
SUBS = Path(os.environ.get("PG_PUSH_SUBS", "/workspace/puregold-push/subscriptions.json"))
STATE = Path(os.environ.get("PG_PUSH_STATE", "/workspace/puregold-push/last_send.json"))


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def payload_for(plan: dict, hist: dict | None) -> dict | None:
    if not plan:
        return None
    news = plan.get("news") or {}
    h1 = plan.get("h1") or {}
    side = plan.get("side") or "wait"
    title = "PureGold"
    body = None
    url = "https://gold.purefxai.store/#levels"
    if news.get("blackout") and not (h1.get("confirmed")):
        body = news.get("label_th") or "ช่วงข่าวแรง งดเข้า"
        if news.get("detail_th"):
            body = body + " — " + news["detail_th"]
    hist = hist or {}
    opened = hist.get("open") or {}
    last = opened.get("last_event")  # optional
    # Prefer explicit plan flags if present
    status = (plan.get("status") or {}) if isinstance(plan.get("status"), dict) else {}
    if body:
        return {"title": title, "body": body, "url": url, "lang": "th", "kind": "news"}
    return None


def status_key(plan: dict, hist: dict | None) -> str:
    news = (plan or {}).get("news") or {}
    h1 = (plan or {}).get("h1") or {}
    open_item = (hist or {}).get("open") or {}
    closed = (hist or {}).get("closed") or []
    last_closed = closed[-1] if closed else {}
    return "|".join([
        str((plan or {}).get("side") or ""),
        str((plan or {}).get("entry") or ""),
        str((plan or {}).get("updated") or ""),
        "news" if news.get("blackout") else "",
        "h1" if h1.get("confirmed") else "",
        str(open_item.get("reached") or ""),
        str(last_closed.get("plan_id") or "") + ":" + str(last_closed.get("outcome") or ""),
    ])


def build_event_payload(plan: dict, hist: dict | None, prev_key: str) -> dict | None:
    """Emit a user-facing payload when the plan or history advances."""
    news = (plan or {}).get("news") or {}
    h1 = (plan or {}).get("h1") or {}
    open_item = (hist or {}).get("open") or {}
    closed = (hist or {}).get("closed") or []
    last_closed = closed[-1] if closed else {}
    url = "https://gold.purefxai.store/#levels"
    reached = open_item.get("reached") or []
    furthest = reached[-1] if reached else None

    body = None
    kind = "plan"
    if last_closed and last_closed.get("outcome") in {"sl", "cancelled", "expired", "tp3"}:
        outcome = last_closed.get("outcome")
        if outcome == "sl":
            body = "ชนจุดตัดขาดทุน (SL)"
        elif outcome == "cancelled":
            reason = last_closed.get("reason_th") or last_closed.get("reason") or ""
            body = "แผนถูกยกเลิก" + ((" — " + reason) if reason else "")
        elif outcome == "tp3":
            body = "ชน TP3"
        elif outcome == "expired":
            body = None  # skip expired noise unless we want it
    if not body and furthest in {"tp1", "tp2", "tp3"}:
        if furthest == "tp1":
            body = "ชน TP1 — เลื่อน SL มาจุดเข้า"
        else:
            body = "ชน " + furthest.upper()
    if not body and news.get("blackout") and not h1.get("confirmed"):
        body = (news.get("label_th") or "ช่วงข่าวแรง งดเข้า")
        if news.get("detail_th"):
            body = body + " — " + news["detail_th"]
        kind = "news"
    if not body and h1.get("confirmed") and (plan or {}).get("side") in {"buy", "sell"}:
        hm = h1.get("as_of_hm") or ""
        body = h1.get("note_th") or ("แท่ง H1 ปิดยืนยันแล้ว" + ((" " + hm) if hm else ""))
        kind = "confirm"
    if not body:
        return None
    return {"title": "PureGold", "body": body, "url": url, "lang": "th", "kind": kind}


def send_all(payload: dict) -> tuple[int, int]:
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("pywebpush missing; pip install pywebpush", file=sys.stderr)
        return 0, 0
    secrets = load(SECRETS) or {}
    pem = secrets.get("private_pem")
    subj = secrets.get("subject") or "mailto:hello@purefxai.store"
    if not pem:
        print("no VAPID private key", file=sys.stderr)
        return 0, 0
    subs = load(SUBS) or []
    if isinstance(subs, dict):
        subs = subs.get("subscriptions") or []
    ok = fail = 0
    kept = []
    body = json.dumps(payload, ensure_ascii=False)
    for item in subs:
        sub = item.get("subscription") if isinstance(item, dict) and "subscription" in item else item
        if not sub or not sub.get("endpoint"):
            continue
        try:
            webpush(
                subscription_info=sub,
                data=body,
                vapid_private_key=pem,
                vapid_claims={"sub": subj},
            )
            ok += 1
            kept.append(item)
        except Exception as exc:
            fail += 1
            msg = str(exc)
            # Drop gone subscriptions
            if "410" in msg or "404" in msg or "Gone" in msg:
                continue
            kept.append(item)
            print("push fail:", msg[:200], file=sys.stderr)
    SUBS.parent.mkdir(parents=True, exist_ok=True)
    SUBS.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n")
    return ok, fail


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    plan_path = Path("trade_plan.json")
    hist_path = Path("plan_history.json")
    force = False
    i = 0
    while i < len(argv):
        if argv[i] == "--plan":
            plan_path = Path(argv[i + 1]); i += 2; continue
        if argv[i] == "--history":
            hist_path = Path(argv[i + 1]); i += 2; continue
        if argv[i] == "--force":
            force = True; i += 1; continue
        i += 1
    plan = load(plan_path) or {}
    hist = load(hist_path) or {}
    key = status_key(plan, hist)
    prev = load(STATE) or {}
    if not force and prev.get("key") == key:
        print("no push change")
        return 0
    payload = build_event_payload(plan, hist, prev.get("key") or "")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"key": key, "at": datetime.now(BKK).isoformat(), "payload": payload}, ensure_ascii=False, indent=2) + "\n")
    if not payload:
        print("status advanced but no user-facing push")
        return 0
    ok, fail = send_all(payload)
    print(f"pushed ok={ok} fail={fail} body={payload.get('body')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
