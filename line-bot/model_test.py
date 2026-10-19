import os,json,urllib.request,urllib.error,asyncio,sys
K=os.environ.get("GEMINI_API_KEY")
if not K: print("NO_KEY"); sys.exit(0)
B="https://generativelanguage.googleapis.com/v1beta/"
def call(path,body=None):
    rq=urllib.request.Request(B+path,json.dumps(body).encode() if body else None,{"Content-Type":"application/json","x-goog-api-key":K})
    try: return 200,json.load(urllib.request.urlopen(rq,timeout=60))
    except urllib.error.HTTPError as e:
        try: m=json.load(e)["error"]; return e.code,m.get("status","")+": "+m.get("message","")[:110]
        except Exception: return e.code,""
    except Exception as e: return 0,str(e)[:110]
c,j=call("models?pageSize=200")
names=[m["name"] for m in j.get("models",[])] if c==200 else []
print("list models:",c,len(names)); print(" ".join(n for n in names if "gemini-3" in n or "live" in n or "tts" in n))
for m in ["gemini-3.8-flash","gemini-3.8-flash-lite","gemini-3.5-flash-lite","gemini-3.5-flash","gemini-2.5-flash","gemini-flash-latest"]:
    c,r=call(f"models/{m}:generateContent",{"contents":[{"parts":[{"text":"ตอบคำเดียว: สวัสดี"}]}],"generationConfig":{"maxOutputTokens":20}})
    print(m,c,"OK" if c==200 else r)
for m in ["gemini-3.8-flash-tts","gemini-3.8-flash-lite-tts","gemini-2.5-flash-preview-tts"]:
    c,r=call(f"models/{m}:generateContent",{"contents":[{"parts":[{"text":"สวัสดีครับ"}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Kore"}}}}})
    print(m,c,("OK "+r["candidates"][0]["content"]["parts"][0]["inlineData"]["mimeType"]) if c==200 else r)
async def live(m,extra):
    import websockets
    u="wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="+K
    try:
        async with websockets.connect(u,open_timeout=15) as ws:
            await ws.send(json.dumps({"setup":{"model":m,"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Sulafat"}}}},**extra}}))
            r=json.loads(await asyncio.wait_for(ws.recv(),15)); print(m,"LIVE","OK" if "setupComplete" in r else str(r)[:120])
    except Exception as e: print(m,"LIVE FAIL",str(e).replace(K,"***")[:160])
asyncio.run(live("models/gemini-3.8-live",{}))
asyncio.run(live("models/gemini-3.5-live-translate-preview",{"translationConfig":{"targetLanguageCode":"th","echoTargetLanguage":True}}))
