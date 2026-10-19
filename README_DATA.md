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
