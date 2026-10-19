#!/bin/bash
# คิวคำสั่งจากเจ้าของบอท LINE -> ระบบเทรด
# usage: line_commands.sh fetch                      -> พิมพ์ JSON {"ok":true,"commands":[...]}
#        line_commands.sh ack <id> <ok|fail> "<ผล>"  -> แจ้งผล (บอทจะ push กลับไปหาเจ้าของ)
# env: LINE_ALERT_URL (Apps Script /exec หรือ Worker base URL), ALERT_SECRET, LINE_BACKEND=apps|worker (default apps)
# ไม่พิมพ์ค่าลับ
set -e
[ -n "$LINE_ALERT_URL" ] && [ -n "$ALERT_SECRET" ] || { echo '{"ok":false,"error":"LINE_ALERT_URL/ALERT_SECRET not set"}'; exit 1; }
BASE="${LINE_ALERT_URL%/}"; BACK="${LINE_BACKEND:-apps}"
case "$1" in
  fetch)
    if [ "$BACK" = worker ]; then BASE="${BASE%/tts}"; BASE="${BASE%/alert}"; URL="$BASE/commands"; else URL="$BASE?action=commands"; fi
    curl -sL --max-time 30 -G "$URL" --data-urlencode "secret=$ALERT_SECRET" ;;
  ack)
    [ -n "$2" ] || { echo "need id"; exit 1; }
    BODY=$(python3 -c 'import json,os,sys; print(json.dumps({"action":"ack","secret":os.environ["ALERT_SECRET"],"id":sys.argv[1],"ok":sys.argv[2]!="fail","result":sys.argv[3][:500]}))' "$2" "${3:-ok}" "${4:-}")
    if [ "$BACK" = worker ]; then BASE="${BASE%/tts}"; BASE="${BASE%/alert}"; URL="$BASE/ack"; else URL="$BASE"; fi
    printf '%s' "$BODY" | curl -sL --max-time 30 "$URL" -H 'Content-Type: application/json' -d @- ;;
  *) echo "usage: $0 fetch | ack <id> <ok|fail> \"<result>\""; exit 2 ;;
esac
echo
