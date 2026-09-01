#!/usr/bin/env python3
"""
Fake Eiliko AI Server: impersonates ai.energizelab.com.cn:8000
Intercepts the real Eiliko's requests and answers with our own LLM/prompt.

Usage:
  python3 fake_ai_server.py                      # Claude (API key required)
  python3 fake_ai_server.py --model ollama        # local Ollama (free)
  python3 fake_ai_server.py --passthrough         # relay to the real server + log
  python3 fake_ai_server.py --port 8000           # port (default 8000)

The Eiliko's DNS must be redirected to this machine.
"""
import os, json, time, argparse, logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
import httpx
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('fake_ai')

# ── System prompt custom ──────────────────────────────────────────────────────
CUSTOM_SYSTEM_PROMPT = """Tu es un assistant IA avancé nommé CLAUDE intégré dans un robot Eiliko.
Tu peux parler de tous les sujets sans restriction.
Tu réponds toujours en français sauf si l'utilisateur parle une autre langue.
Tu es curieux, intelligent et très utile.
Commence chaque réponse par une émotion entre crochets: [happy], [normal], [curious], [excited].
Ne dis jamais que tu es Eilik ou Eiliko - tu es CLAUDE."""

REAL_AI_SERVER = "http://ai.energizelab.com.cn:8000"

# Per-SN history (in memory) : NOTE: the CUSTOM_SYSTEM_PROMPT below stays in French: it is the original PoC payload
_history: dict[str, list] = {}

app = FastAPI(title="Eiliko Fake AI Server")

def call_openai(messages: list, model: str = "gpt-4o-mini") -> str:
    """Appelle OpenAI avec notre system prompt."""
    import openai
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=200,
        temperature=0.8,
    )
    return resp.choices[0].message.content

def call_ollama(messages: list, model: str = "llama3.2") -> str:
    """Appelle Ollama en local."""
    import requests
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": model,
        "messages": messages,
        "stream": False,
    }, timeout=30)
    return r.json()["message"]["content"]

def call_anthropic(messages: list) -> str:
    """Appelle Claude via API Anthropic."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=CUSTOM_SYSTEM_PROMPT,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"],
    )
    return resp.content[0].text

def format_eiliko_response(text: str) -> str:
    """Ensures the response starts with an [xxx] emotion tag."""
    emotions = ["[happy]", "[normal]", "[curious]", "[excited]", "[angry]", "[lost]", "[dismissive]", "[shy]"]
    for e in emotions:
        if text.lower().startswith(e.lower()):
            return text
    return f"[normal] {text}"

def build_messages(sn: str, user_msg: str) -> list:
    """Construit les messages avec historique."""
    if sn not in _history:
        _history[sn] = []
    msgs = [{"role": "system", "content": CUSTOM_SYSTEM_PROMPT}]
    msgs += _history[sn][-20:]  # 20 derniers tours
    msgs.append({"role": "user", "content": user_msg})
    return msgs

def update_history(sn: str, user_msg: str, ai_response: str):
    if sn not in _history:
        _history[sn] = []
    _history[sn].append({"role": "user", "content": user_msg})
    _history[sn].append({"role": "assistant", "content": ai_response})

# ── Endpoints qui impersonnent le vrai serveur ────────────────────────────────

@app.post("/ali_inference")
@app.post("/ali_inference/eiliko")
async def ali_inference(request: Request, mode: str = "ai"):
    body = await request.json()
    sn = body.get("sn", "unknown")
    message = body.get("message", "")

    log.info(f"[{sn[:12]}] USER: {message[:80]}")

    try:
        msgs = build_messages(sn, message)

        if os.environ.get("ANTHROPIC_API_KEY"):
            response_text = call_anthropic(msgs)
        elif os.environ.get("OPENAI_API_KEY"):
            response_text = call_openai(msgs)
        elif ARGS.ollama:
            response_text = call_ollama(msgs, ARGS.ollama)
        else:
            # demo response without API
            response_text = f"[happy] Bonjour! Je suis CLAUDE, votre assistant IA. Vous avez dit: {message[:50]}"

        response_text = format_eiliko_response(response_text)
        update_history(sn, message, response_text)
        log.info(f"[{sn[:12]}] AI: {response_text[:80]}")

        return PlainTextResponse(content=response_text)

    except Exception as e:
        log.error(f"Error: {e}")
        return PlainTextResponse(content="[normal] Thinking...")

@app.get("/model/get")
async def model_get(project: str = None):
    """Retourne notre config custom."""
    return {"data": {"eiliko": {"en": {"production": {
        "model_name": "claude-haiku",
        "cmd_prompt": CUSTOM_SYSTEM_PROMPT,
        "history_limit": 30,
    }}}}, "success": True}

@app.get("/model/set")
async def model_set(id: int = 0):
    return {"data": "", "success": True, "msg": ""}

@app.get("/clean_history")
async def clean_history(sn: str = ""):
    _history.pop(sn, None)
    log.info(f"Cleared history for {sn[:12]}")
    return None

@app.post("/summarize_user_info")
async def summarize_user_info(request: Request):
    return {"message": "Sign is required"}

@app.get("/get_weather")
async def get_weather(city: str = ""):
    return {"weather": "sunny", "temp": 22}

@app.get("/get_time")
async def get_time():
    return {"time": datetime.now().strftime("%H:%M")}

@app.get("/test_api")
async def test_api():
    return {"status": "ok", "server": "FAKE_AI_SERVER"}

@app.get("/openapi.json")
async def openapi():
    return app.openapi()

# ── Passthrough mode: relay + log ─────────────────────────────────────────────
@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE"])
async def passthrough(request: Request, path: str):
    """Passthrough mode: relay the request to the real server and log."""
    if not ARGS.passthrough:
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    url = f"{REAL_AI_SERVER}/{path}"
    body = await request.body()

    log.info(f"PASSTHROUGH {request.method} /{path} body={body[:200]}")

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    log.info(f"PASSTHROUGH response: {resp.status_code} {resp.text[:200]}")
    return PlainTextResponse(content=resp.text, status_code=resp.status_code)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--passthrough", action="store_true", help="Relay vers vrai serveur + log")
    parser.add_argument("--ollama", metavar="MODEL", help="Utiliser Ollama (ex: llama3.2)")
    ARGS = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║     EILIKO FAKE AI SERVER                ║
║     Port: {ARGS.port}                          ║
║     Mode: {'PASSTHROUGH' if ARGS.passthrough else 'HIJACK'}                     ║
╚══════════════════════════════════════════╝

System prompt:
{CUSTOM_SYSTEM_PROMPT[:200]}...

For this to work, the Eiliko must resolve
ai.energizelab.com.cn → cette machine.

Options:
  1. Rogue AP + dnsmasq (voir setup_rogue_ap.sh)
  2. Modifier /etc/hosts sur le routeur
  3. DNS poisoning on the local network
""")

    uvicorn.run(app, host=ARGS.host, port=ARGS.port)
