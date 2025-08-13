import os
from fastapi import FastAPI, Request
import httpx
import asyncpg

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_USERNAME = "GH43L"

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = FastAPI()

# Conexión DB
@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.connect(DATABASE_URL)
    await app.state.db.execute("""
        CREATE TABLE IF NOT EXISTS vendedores (
            id BIGINT PRIMARY KEY,
            username TEXT,
            role TEXT CHECK (role IN ('pending','seller','rejected')) DEFAULT 'pending'
        )
    """)
    print("DB conectada y tabla lista 🚀")

    if TELEGRAM_TOKEN and WEBHOOK_URL and WEBHOOK_URL.startswith("https://"):
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{TELEGRAM_API}/setWebhook", json={
                "url": f"{WEBHOOK_URL}/webhook"
            })
            print("setWebhook:", resp.status_code, resp.text)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    message = data.get("message") or data.get("edited_message") or {}
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text") or ""
    username = message.get("from", {}).get("username", "")

    callback_query = data.get("callback_query")
    if callback_query:
        # Manejo de aprobación/rechazo
        cq_data = callback_query.get("data", "")
        admin_user = callback_query.get("from", {}).get("username", "").lower()
        if admin_user != ADMIN_USERNAME.lower():
            await answer_callback(callback_query, "No tienes permiso para esta acción.")
            return {"ok": True}

        if cq_data.startswith("approve:"):
            uid = int(cq_data.split(":")[1])
            await app.state.db.execute(
                "UPDATE vendedores SET role='seller' WHERE id=$1", uid
            )
            await send_message(uid, "🎉 ¡Tu solicitud ha sido aprobada! Ya puedes añadir productos.")
            await answer_callback(callback_query, "Solicitud aprobada ✅")
        elif cq_data.startswith("reject:"):
            uid = int(cq_data.split(":")[1])
            await app.state.db.execute(
                "UPDATE vendedores SET role='rejected' WHERE id=$1", uid
            )
            await send_message(uid, "❌ Tu solicitud ha sido rechazada por el administrador.")
            await answer_callback(callback_query, "Solicitud rechazada 🚫")
        return {"ok": True}

    if not chat_id:
        return {"ok": True}

    if text.startswith("/start"):
        await send_message(chat_id, "Hola 👋, usa /solicitar_vendedor si quieres ser vendedor.")
    elif text.startswith("/solicitar_vendedor"):
        role = await app.state.db.fetchval(
            "SELECT role FROM vendedores WHERE id=$1", chat_id
        )
        if role == "seller":
            await send_message(chat_id, "Ya eres vendedor ✅")
        elif role == "pending":
            await send_message(chat_id, "Tu solicitud ya está pendiente ⏳")
        else:
            await app.state.db.execute(
                "INSERT INTO vendedores (id, username, role) VALUES ($1, $2, 'pending') "
                "ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username, role='pending'",
                chat_id, username
            )
            await send_message(chat_id, "Solicitud enviada, el admin la revisará.")
            # Notificar al admin
            await send_admin_request(chat_id, username)
    else:
        await send_message(chat_id, f"Eco: {text}")

    return {"ok": True}

# ---- Utilidades Telegram ----
async def send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup
        })

async def send_admin_request(user_id: int, username: str):
    kb = {
        "inline_keyboard": [[
            {"text": "✅ Aprobar", "callback_data": f"approve:{user_id}"},
            {"text": "❌ Rechazar", "callback_data": f"reject:{user_id}"}
        ]]
    }
    await send_message(f"@{ADMIN_USERNAME}",
        f"Solicitud de vendedor:\n• ID: {user_id}\n• Usuario: @{username or 'sin_username'}",
        reply_markup=kb
    )

async def answer_callback(callback_query: dict, text: str):
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TELEGRAM_API}/answerCallbackQuery", json={
            "callback_query_id": callback_query["id"],
            "text": text,
            "show_alert": False
        })
