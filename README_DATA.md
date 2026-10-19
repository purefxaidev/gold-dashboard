# data.json field reference (PUREGOLD dashboard)

The site has a TH/EN switch (header toggle, `?lang=en|th`, saved in localStorage `gd_ui_lang`, default from the browser language).
Every text field can have an English twin with the suffix `_en` and the same shape. If an `_en` field is missing or empty, the English site shows the Thai text.
`build.py` strips emoji from every string, checks that each `_en` field has the same type as its Thai field, and blocks keys, emails and account fields.

| Thai field | English field | Type |
|---|---|---|
| updated | updated_en | string |
| price | price_en | string (the first number is used as the price) |
| bias | bias_en | string, "summary · detail · ..." |
| indicators | indicators_en | string |
| resistance / support | resistance_en / support_en | list of strings (the numbers come from the Thai field) |
| plans | plans_en | list of string lists, card title first |
| news | news_en | list of [summary, url], same order and count as news |
| note | note_en | string |
| ai_method | ai_method_en | string |
| ai_reasons | ai_reasons_en | list of [up/down/neutral, reason] |
| ev_method | ev_method_en | string |
| ev_plans[i].name / status | ev_plans[i].name_en / status_en | string |
| pnl.note | pnl.note_en | string (allowlisted) |
| auto_trade.interval | auto_trade.interval_en | string, e.g. "30 min" |

Language-neutral fields (numbers or codes, not translated): ai_up_pct, ai_down_pct, ev_plans entry/sl/tp/p_win/side, pnl numbers/trades/pending, auto_trade.enabled/lot.
The plan sentences in the "Recommendation now" card are built in both languages from ev_plans, so they need no extra fields.
Do not use emoji. Never include account numbers, tickets, balance or equity.

## Analysis fields (written by scripts, do not hand-edit)
Run order each check: `python3 mtf.py && python3 smc.py && python3 edge.py && python3 build.py` (publish.sh does this).
- `mtf` / `mtf_en`: XAUUSD trend per timeframe `[{tf, trend up|down|sideways, label, rsi, ema20, ema50}]`, `mtf_align` / `mtf_align_en` summary. Gold candles from Binance PAXGUSDT offset to gold-api.com spot, saved in `candles.json`.
- `markets` / `markets_en`: EURUSD GBPUSD USDJPY AUDUSD USDCHF USDCAD BTCUSD (Yahoo chart API): price, chg_pct, spark (48 x H1), tfs M15/H1/H4/D1 trend+rsi, bias, support, resistance, bias_label, setup (plain-language hint). Analysis only.
- `smc`: `{SYMBOL: {TF: {order_blocks, fvg, bos, choch, liquidity, zone, last_event, price}}}` from `smc.py`; `smc_notes` / `smc_notes_en`.
- `correlations`: `{H1|D1: {symbols, matrix, bars}}` (log returns, last 50 common bars), `correlations_notes` / `_en`.
- `edge`: from `edge.py` (best, worst, by_* groups, total, notes, notes_en). n < 10 or < 3 trading days = low confidence.

## Trade journal fields (history/trade_journal.jsonl), one JSON object per closed trade
Required: time_open, time_close (Bangkok "YYYY-MM-DD HH:MM"), symbol (e.g. XAUUSD), side, lot, entry, exit, sl, tp, result (win|loss|be), pnl_points, pnl_usc, by (AI|ผู้ใช้).
For the edge finder, record from now on: timeframe (M5|M15|H1|H4|D1 used for the decision), setup_type (OB retest | FVG | breakout | S/R bounce (buy the dip) | chase near high | other),
session (Asia | London | New York, by Bangkok hour: 05-14 Asia, 14-19 London, 19-05 New York), news_tag (short tag), mtf_align (e.g. "4/5 up"), smc_context (e.g. "H1 bullish OB, discount").
Optional: setup, news, lesson, close (manual|tp|sl). Never put ticket ids, account numbers, balance or equity in the journal.
