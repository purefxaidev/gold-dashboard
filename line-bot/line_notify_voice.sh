#!/bin/bash
# usage: line_notify_voice.sh "message"
# ข้อความ + เสียงไทย (ฟรี): Gemini TTS (GEMINI_API_KEY บนเครื่อง หรือ Apps Script action=tts)
#   -> ffmpeg m4a -> GitHub Pages gold-dashboard/audio/ (เก็บ 20 ไฟล์ล่าสุด) -> LINE broadcast ข้อความ+เสียง
# ล้มขั้นไหน -> line_notify.sh (ข้อความอย่างเดียว). ไม่พิมพ์ค่าลับ
MSG="$1"
DIR=/workspace
REPO=/workspace/gold-dashboard
BASE=https://purefxaidev.github.io/gold-dashboard/audio
fallback() { echo "voice alert failed: $1 -> text fallback" >&2; exec "$DIR/line_notify.sh" "$MSG"; }

[ -n "$LINE_CHANNEL_ACCESS_TOKEN" ] || fallback "no LINE token"
[ -n "$GEMINI_API_KEY" ] || { [ -n "$LINE_ALERT_URL" ] && [ -n "$ALERT_SECRET" ]; } || fallback "no TTS source"
command -v ffmpeg >/dev/null || fallback "no ffmpeg"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
NAME="a$(date +%Y%m%d%H%M%S)-$RANDOM.m4a"

# 1) TTS -> PCM
cat > "$TMP/tts.py" <<'PY'
import json,os,sys,base64,re,urllib.request
msg,d=sys.argv[1],sys.argv[2]
def out(data,rate):
    open(d+"/a.pcm","wb").write(base64.b64decode(data)); print(int(rate)); sys.exit(0)
key=os.environ.get("GEMINI_API_KEY")
if key:
    speak=re.sub(r"https?://\S+","",re.sub(r"[*#_`>]","",msg))[:600]
    for model in os.environ.get("TTS_MODELS","gemini-3.8-flash-tts gemini-3.8-flash-lite-tts gemini-2.5-flash-preview-tts").split():
        try:
            body=json.dumps({"contents":[{"parts":[{"text":"อ่านด้วยน้ำเสียงนักวิเคราะห์ที่สุภาพ ชัดเจน: "+speak}]}],
              "generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}}}).encode()
            rq=urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"%model,body,
              {"Content-Type":"application/json","x-goog-api-key":key})
            inl=json.load(urllib.request.urlopen(rq,timeout=60))["candidates"][0]["content"]["parts"][0]["inlineData"]
            m=re.search(r"rate=(\d+)",inl.get("mimeType","")); out(inl["data"], m.group(1) if m else 24000)
        except SystemExit: raise
        except Exception as e: print("tts %s failed: %s"%(model,str(e)[:120]),file=sys.stderr)
url,sec=os.environ.get("LINE_ALERT_URL"),os.environ.get("ALERT_SECRET")
if url and sec:
    rq=urllib.request.Request(url,json.dumps({"action":"tts","secret":sec,"text":msg[:1500]}).encode(),{"Content-Type":"application/json"})
    j=json.load(urllib.request.urlopen(rq,timeout=60))
    if j.get("ok"): out(j["pcmBase64"],j.get("sampleRate",24000))
sys.exit(1)
PY
RATE=$(python3 "$TMP/tts.py" "$MSG" "$TMP") || fallback "tts"

# 2) m4a (AAC mono)
ffmpeg -loglevel error -y -f s16le -ar "$RATE" -ac 1 -i "$TMP/a.pcm" -c:a aac -b:a 64k -ac 1 "$TMP/$NAME" || fallback "ffmpeg"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/$NAME" | python3 -c 'import sys;print(int(float(sys.stdin.read())*1000))') || fallback "ffprobe"

# 3) push ขึ้น GitHub Pages (เก็บ 20 ไฟล์ล่าสุด)
(
  set -e; cd "$REPO"; git pull -q --rebase || true
  mkdir -p audio; cp "$TMP/$NAME" audio/
  ls -1t audio/*.m4a | tail -n +21 | while read -r f; do git rm -q --ignore-unmatch "$f" || true; rm -f "$f"; done
  git add -A audio; git commit -qm "audio alert $NAME"; git push -q
) >/dev/null 2>&1 || fallback "git push"

# 4) รอ Pages (<=90 วิ)
URL="$BASE/$NAME"; okp=0
for i in $(seq 1 18); do
  [ "$(curl -s -o /dev/null --max-time 8 -w '%{http_code}' "$URL")" = 200 ] && { okp=1; break; }; sleep 5
done
[ $okp = 1 ] || fallback "pages not ready"

# 5) LINE broadcast ข้อความ + เสียง
CODE=$(python3 -c 'import json,sys; print(json.dumps({"messages":[{"type":"text","text":sys.argv[1][:4900]},{"type":"audio","originalContentUrl":sys.argv[2],"duration":int(sys.argv[3])}]}))' "$MSG" "$URL" "$DUR" \
  | curl -s -X POST https://api.line.me/v2/bot/message/broadcast -H "Authorization: Bearer $LINE_CHANNEL_ACCESS_TOKEN" -H 'Content-Type: application/json' -d @- -o "$TMP/line.out" -w '%{http_code}')
[ "$CODE" = 200 ] || fallback "LINE $CODE"
echo "sent text+voice $URL (${DUR}ms)"
