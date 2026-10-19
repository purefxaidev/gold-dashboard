#!/usr/bin/env python3
"""PUREGOLD gold-news articles.

Workflow (run by the agent each news cycle):
  1) python3 news.py scan [--hours 12] [--max 15]
       Fetch free public RSS (Google News, FXStreet, Investing, MarketWatch, CNBC, Yahoo GC=F), keep gold-moving
       items, drop anything already in news.json (by URL or normalised title) or already skipped, and write
       the candidates to /workspace/news_candidates.json (not in the repo). Nothing in the repo changes.
  2) The analyst (agent) writes articles for the candidates worth covering into a JSON list file, schema:
       [{"cand": "<candidate key from scan>",          # or give url/source/published/headline_src yourself
         "impact": "bullish|bearish|neutral", "level": "high|medium|low",
         "title_th": "...", "article_th": ["para", "para", ...],   # 3-5 short paragraphs
         "title_en": "...", "article_en": ["para", ...],
         "summary_th": "2-3 sentences for the LINE card", "summary_en": "..."}]
     Facts must come only from the source headline/summary; direction must state uncertainty.
  3) python3 news.py add articles.json      -> merges into news.json (newest first, keep 50), prints new ids
       python3 news.py skip <cand-key> ...   -> mark candidates as not worth an article (stored in news.json "skipped")
  4) python3 news.py card <id>              -> prints the JSON for:  bash /workspace/line_flex.sh news_article '<json>'
       python3 news.py send <id>             -> builds the card and calls line_flex.sh (honours DRY_RUN / VALIDATE)
  5) publish.sh (or git add news.json && commit && push) to update news.html on GitHub Pages.
Never stores account data, keys or emails.
"""
import json, sys, os, re, hashlib, html, datetime, subprocess, urllib.request, email.utils
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "news.json")
CAND = "/workspace/news_candidates.json"
SITE = "https://purefxaidev.github.io/gold-dashboard/news.html"
BKK = ZoneInfo("Asia/Bangkok")
KEEP = 50
FEEDS = [
    ("FXStreet", "https://www.fxstreet.com/rss/news"),
    ("Investing.com", "https://www.investing.com/rss/news_11.rss"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("Yahoo Finance", "https://finance.yahoo.com/rss/headline?s=GC=F"),
    # Google News last: direct publisher links win when the same story appears twice
    ("Google News", "https://news.google.com/rss/search?q=gold+price+OR+XAUUSD+OR+%22gold+futures%22+when:1d&hl=en-US&gl=US&ceid=US:en"),
    ("Google News", "https://news.google.com/rss/search?q=Fed+OR+CPI+OR+%22nonfarm+payrolls%22+OR+%22Treasury+yields%22+dollar+when:1d&hl=en-US&gl=US&ceid=US:en"),
]
GOLD = re.compile(r"\b(gold|xau|bullion|precious metal|safe[- ]haven)\b", re.I)
MACRO = re.compile(r"\b(fed|fomc|powell|warsh|rate (cut|hike)|cpi|inflation|pce|nonfarm|payrolls|nfp|jobs report|treasury yields?|dollar index|dxy|"
                   r"tariff|hormuz|iran|central bank buying)\b", re.I)

def load():
    try: return json.load(open(DB, encoding="utf-8"))
    except Exception: return {"updated": None, "items": [], "skipped": []}
def save(db):
    db["items"] = sorted(db["items"], key=lambda x: x.get("published_ts", 0), reverse=True)[:KEEP]
    db["skipped"] = db.get("skipped", [])[-300:]
    db["updated"] = datetime.datetime.now(BKK).strftime("%Y-%m-%d %H:%M")
    tmp = DB + ".tmp"; json.dump(db, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, DB)
def norm(t): return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\s+-\s+[^-]+$", "", (t or "").lower())).strip()
def key(url, title): return hashlib.sha1((norm(title)[:90]).encode()).hexdigest()[:10]
def clean(t): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
def fetch(u):
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (PUREGOLD news scanner)"})
    return urllib.request.urlopen(r, timeout=20).read()
def ptime(s):
    try: return email.utils.parsedate_to_datetime(s).astimezone(BKK)
    except Exception:
        try: return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(BKK)
        except Exception: return None

def scan(hours=12, mx=15):
    db = load(); seen = {i.get("key") for i in db["items"]} | set(db.get("skipped", []))
    seen_urls = {i.get("url") for i in db["items"]}; now = datetime.datetime.now(BKK); out = {}; errs = []
    for src, u in FEEDS:
        try: root = ET.fromstring(fetch(u))
        except Exception as e: errs.append(f"{src}: {e.__class__.__name__}"); continue
        for it in root.iter("item"):
            title = clean(it.findtext("title")); link = (it.findtext("link") or "").strip(); desc = clean(it.findtext("description"))[:500]
            pub = ptime(it.findtext("pubDate") or "")
            if not title or not link.startswith("https://") or not pub or (now - pub).total_seconds() > hours * 3600: continue
            text = title + " " + desc
            gold = bool(GOLD.search(text)); macro = bool(MACRO.search(text))
            if not (gold or (macro and src != "Google News") or (macro and "Fed" in u)): continue
            source = src
            s = it.find("source")
            if s is not None and s.text: source = clean(s.text)
            if src == "Google News": title = re.sub(r"\s+-\s+[^-]+$", "", title); desc = ""   # GN description is only the title again
            k = key(link, title)
            if k in seen or link in seen_urls or k in out: continue
            out[k] = {"cand": k, "headline_src": title, "summary_src": desc, "source": source, "url": link,
                      "published": pub.strftime("%Y-%m-%d %H:%M"), "published_ts": int(pub.timestamp()), "gold": gold}
    c = sorted(out.values(), key=lambda x: (x["gold"], "news.google.com" not in x["url"], x["published_ts"]), reverse=True)[:mx]
    json.dump(c, open(CAND, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"candidates": len(c), "file": CAND, "feed_errors": errs}, ensure_ascii=False))
    for x in c: print(f'{x["cand"]} | {x["published"]} | {x["source"]} | {x["headline_src"]}')

REQ = ("impact", "title_th", "article_th", "title_en", "article_en")
def add(path):
    arts = json.load(open(path, encoding="utf-8")); arts = arts if isinstance(arts, list) else [arts]
    try: cands = {c["cand"]: c for c in json.load(open(CAND, encoding="utf-8"))}
    except Exception: cands = {}
    db = load(); have = {i["id"] for i in db["items"]}; new = []
    for a in arts:
        base = dict(cands.get(a.get("cand"), {})); base.update({k: v for k, v in a.items() if v not in (None, "")})
        miss = [k for k in REQ + ("url", "source", "published") if not base.get(k)]
        if miss: print("skip (missing " + ",".join(miss) + "):", a.get("cand") or a.get("title_en"), file=sys.stderr); continue
        if not str(base["url"]).startswith("https://"): print("skip non-https url", file=sys.stderr); continue
        imp = str(base["impact"]).lower(); imp = {"up": "bullish", "down": "bearish"}.get(imp, imp)
        if imp not in ("bullish", "bearish", "neutral"): imp = "neutral"
        k = base.get("cand") or key(base["url"], base.get("headline_src") or base["title_en"])
        pub = base.get("published"); ts = base.get("published_ts")
        if not ts:
            try: ts = int(datetime.datetime.strptime(pub, "%Y-%m-%d %H:%M").replace(tzinfo=BKK).timestamp())
            except Exception: ts = int(datetime.datetime.now(BKK).timestamp())
        nid = "n" + datetime.datetime.fromtimestamp(ts, BKK).strftime("%y%m%d%H%M") + "-" + k[:4]
        if nid in have or any(i.get("key") == k for i in db["items"]): print("dup:", nid, file=sys.stderr); continue
        para = lambda v: [clean(p) for p in (v if isinstance(v, list) else re.split(r"\n\s*\n", str(v))) if clean(p)][:6]
        item = {"id": nid, "key": k, "impact": imp, "level": str(base.get("level", "medium")).lower(),
                "title_th": clean(base["title_th"]), "title_en": clean(base["title_en"]),
                "article_th": para(base["article_th"]), "article_en": para(base["article_en"]),
                "summary_th": clean(base.get("summary_th") or " ".join(para(base["article_th"])[:1])),
                "summary_en": clean(base.get("summary_en") or " ".join(para(base["article_en"])[:1])),
                "headline_src": clean(base.get("headline_src") or ""), "source": clean(base["source"]), "url": base["url"],
                "published": pub, "published_ts": ts, "added": datetime.datetime.now(BKK).strftime("%Y-%m-%d %H:%M")}
        db["items"].append(item); have.add(nid); new.append(nid)
    save(db); print(json.dumps({"added": new, "total": len(db["items"])}))

def skip(keys):
    db = load(); db.setdefault("skipped", []).extend(k for k in keys if k not in db["skipped"]); save(db); print("skipped", len(keys))

def card(nid):
    db = load(); it = next((i for i in db["items"] if i["id"] == nid), None)
    if not it: sys.exit("no such id " + nid)
    return {"id": it["id"], "headline": it["title_th"], "summary": it["summary_th"], "impact": it["impact"], "level": it.get("level"),
            "source": it["source"], "url": it["url"], "article_url": f"{SITE}#{it['id']}", "time": it["published"] + " น. (เวลาไทย)"}

if __name__ == "__main__":
    a = sys.argv[1:] or ["help"]
    if a[0] == "scan":
        h = float(a[a.index("--hours") + 1]) if "--hours" in a else 12; m = int(a[a.index("--max") + 1]) if "--max" in a else 15; scan(h, m)
    elif a[0] == "add": add(a[1])
    elif a[0] == "skip": skip(a[1:])
    elif a[0] == "card": print(json.dumps(card(a[1]), ensure_ascii=False))
    elif a[0] == "send":
        sys.exit(subprocess.call(["bash", "/workspace/line_flex.sh", "news_article", json.dumps(card(a[1]), ensure_ascii=False)]))
    elif a[0] == "list":
        for i in load()["items"]: print(i["id"], i["impact"], i["published"], i["title_th"])
    else: print(__doc__)
