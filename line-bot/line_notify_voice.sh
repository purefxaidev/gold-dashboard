#!/bin/bash
# usage: line_notify_voice.sh "message"
# ข้อความ + เสียงไทย: Apps Script (action=tts) -> ffmpeg m4a -> GitHub Pages /audio/ -> LINE broadcast
# ล้มเมื่อไหร่ -> fallback line_notify.sh (ข้อความอย่างเดียว). ไม่พิมพ์ค่าลับ
MSG="$1"
DIR=/workspace
REPO=/workspace/gold-dashboard
BASE=https://purefxaidev.github.io/gold-dashboard/audio
fallback() { echo "voice alert failed: $1 -> text fallback" >&2; exec "$DIR/line_notify.sh" "$MSG"; }

[ -n "$LINE_ALERT_URL" ] && [ -n "$ALERT_SECRET" ] && [ -n "$LINE_CHANNEL_ACCESS_TOKEN" ] || fallback "env not set"
command -v ffmpeg >/dev/null || fallback "no ffmpeg"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
NAME="a$(date +%Y%m%d%H%M%S)-$RANDOM.m4a"

# 1) TTS -> PCM
python3 - "$MSG" > "$TMP/req.json" <<'PY' || fallback "req"
import json,os,sys; print(json.dumps({"action":"tts","secret":os.environ["ALERT_SECRET"],"text":sys.argv[1][:1500]}))
PY
curl -sL --max-time 60 "$LINE_ALERT_URL" -H 'Content-Type: application/json' -d @"$TMP/req.json" -o "$TMP/resp.json" || fallback "tts http"
RATE=$(python3 - "$TMP" <<'PY'
import json,sys,base64
d=sys.argv[1]; j=json.load(open(d+"/resp.json"))
if not j.get("ok"): sys.exit(1)
open(d+"/a.pcm","wb").write(base64.b64decode(j["pcmBase64"])); print(int(j.get("sampleRate",24000)))
PY
) || fallback "tts response"

# 2) m4a
ffmpeg -loglevel error -y -f s16le -ar "$RATE" -ac 1 -i "$TMP/a.pcm" -c:a aac -b:a 64k -ac 1 "$TMP/$NAME" || fallback "ffmpeg"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/$NAME" | python3 -c 'import sys;print(int(float(sys.stdin.read())*1000))') || fallback "ffprobe"

# 3) push to GitHub Pages (ลบไฟล์เก่ากว่า 1 วัน)
(
  set -e; cd "$REPO"; git pull -q --rebase || true
  mkdir -p audio; cp "$TMP/$NAME" audio/
  find audio -name '*.m4a' -mmin +1440 -exec git rm -q --ignore-unmatch {} \; -exec rm -f {} \;
  git add audio; git commit -qm "audio alert $NAME"; git push -q
) >/dev/null 2>&1 || fallback "git push"

# 4) รอ Pages
URL="$BASE/$NAME"; okp=0
for i in $(seq 1 18); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL")" = 200 ] && { okp=1; break; }; sleep 5
done
[ $okp = 1 ] || fallback "pages not ready"

# 5) LINE broadcast ข้อความ + เสียง
python3 - "$MSG" "$URL" "$DUR" <<'PY' | curl -s -X POST https://api.line.me/v2/bot/message/broadcast -H "Authorization: Bearer $LINE_CHANNEL_ACCESS_TOKEN" -H 'Content-Type: application/json' -d @- -o "$TMP/line.out" -w '%{http_code}' > "$TMP/code"
import json,sys
print(json.dumps({"messages":[{"type":"text","text":sys.argv[1][:4900]},
 {"type":"audio","originalContentUrl":sys.argv[2],"duration":int(sys.argv[3])}]}))
PY
[ "$(cat "$TMP/code")" = 200 ] || fallback "LINE $(cat "$TMP/code")"
echo "sent text+voice $URL (${DUR}ms)"
