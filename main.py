# main.py
from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # ej: https://sellerbot.onrender.com
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# --------- Utilidades de precio ----------
def euros_to_cents(txt: str) -> int | None:
    t = txt.strip().lower().replace("€", "").replace(",", ".")
    try:
        value = float(t)
    except ValueError:
        return None
    return int(round(value * 100))

def cents_to_euros(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c//100},{c%100:02d} €"

# --------- Healthcheck ----------
@app.get("/")
async def root():
    return {"status": "ok"}

# --------- Webhook ----------
@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    message = data.get("message") or data.get("edited_message") or {}
    chat = message.get("chat", {}) or {}
    chat_id = chat.get("id")
    text = message.get("text") or ""

    if not chat_id:
        return {"ok": True}

    reply = None

    # Comandos básicos
    if text.startswith("/start"):
        reply = (
            "Bienvenido 👋\n"
            "De momento estoy vivo y escuchando vía webhook en Render.\n"
            "• /ping → Pong\n"
            "• /precio 2,50 → Normaliza un precio"
        )
    elif text.startswith("/ping"):
        reply = "Pong 🏓"
    elif text.startswith("/precio "):
        raw = text.split(" ", 1)[1]
        cents = euros_to_cents(raw)
        reply = "Formato inválido (ej: 2, 2.50, 2,50, 2€)" if cents is None else f"{cents_to_euros(cents)}"
    else:
        reply = f"Eco: {text}"

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": reply
        })

    return {"ok": True}

# --------- Registrar webhook al arrancar ----------
@app.on_event("startup")
async def set_webhook():
    if not TELEGRAM_TOKEN:
        print("Falta TELEGRAM_TOKEN")
        return
    if not WEBHOOK_URL or WEBHOOK_URL.startswith("http://") or "example.com" in WEBHOOK_URL:
        print("WEBHOOK_URL no configurada aún; omitiendo setWebhook.")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TELEGRAM_API}/setWebhook", json={
            "url": f"{WEBHOOK_URL}/webhook"
        })
        print("setWebhook:", resp.status_code, resp.text)
