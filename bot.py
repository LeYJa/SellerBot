import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import asyncio

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN", "AQUI_TU_TOKEN")
WEBHOOK_URL = f"https://sellerbot-ve8a.onrender.com/webhook/{TOKEN}"

# Inicializar Flask
app = Flask(__name__)

# Inicializar la aplicación de Telegram
application = Application.builder().token(TOKEN).build()

# =========================
# HANDLERS DE TU BOT
# =========================
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("¡Hola! Soy tu bot y estoy funcionando por webhook en Render 🎉")

async def echo(update: Update, context: CallbackContext):
    await update.message.reply_text(update.message.text)

# Añadir tus handlers aquí
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# =========================
# RUTA DEL WEBHOOK
# =========================
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "OK", 200

# =========================
# INICIO DE LA APP
# =========================
if __name__ == "__main__":
    # Configurar el webhook al iniciar
    asyncio.run(application.bot.set_webhook(url=WEBHOOK_URL))
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
