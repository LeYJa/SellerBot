# main.py
import os
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # p.ej. https://sellerbot.onrender.com
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    message = data.get("message") or data.get("edited_message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = message.get("text") or ""

    if not chat_id:
        return {"ok": True}

    # Respuestas mínimas
    if text.startswith("/start"):
        reply = "¡Hola! Estoy vivo en Render vía webhook. Escribe algo y te hago eco."
    else:
        reply = f"Eco: {text}"

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": reply
        })

    return {"ok": True}

@app.on_event("startup")
async def set_webhook():
    if not TELEGRAM_TOKEN:
        print("Falta TELEGRAM_TOKEN; no se puede registrar webhook.")
        return
    if not WEBHOOK_URL or "example.com" in WEBHOOK_URL or WEBHOOK_URL.startswith("http://"):
        print("WEBHOOK_URL no configurada aún; omitiendo setWebhook.")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TELEGRAM_API}/setWebhook", json={
            "url": f"{WEBHOOK_URL}/webhook"
        })
        print("setWebhook:", resp.status_code, resp.text)
