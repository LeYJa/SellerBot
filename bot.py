import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ----------------------------
# CONFIGURACIÓN
# ----------------------------
ADMIN_USERNAME = "@GH43L"
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Ej: https://tu-app.onrender.com
PORT = int(os.getenv("PORT", 8443))

vendedores_aprobados = set()
solicitudes_vendedor = set()
articulos = []  # {"vendedor": str, "nombre": str, "precio": float, "stock": int}

# ----------------------------
# LOGGING
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------
# FUNCIONES DEL BOT
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenido al expositor.\n"
        "Usa /solicitarvendedor para registrarte como vendedor.\n"
        "Usa /listado para ver los artículos disponibles."
    )

async def solicitar_vendedor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if not user:
        await update.message.reply_text("⚠️ Necesitas un nombre de usuario en Telegram para registrarte.")
        return
    if user in vendedores_aprobados:
        await update.message.reply_text("✅ Ya estás registrado como vendedor.")
    else:
        solicitudes_vendedor.add(user)
        await update.message.reply_text("📨 Tu solicitud ha sido enviada al administrador.")
        await context.bot.send_message(
            chat_id=ADMIN_USERNAME,
            text=f"📢 Nueva solicitud de vendedor: @{user}\nUsa /aprobar {user} o /rechazar {user}"
        )

async def aprobar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if f"@{update.message.from_user.username}" != ADMIN_USERNAME:
        return await update.message.reply_text("❌ No tienes permiso para hacer esto.")
    if not context.args:
        return await update.message.reply_text("Uso: /aprobar usuario")
    usuario = context.args[0]
    solicitudes_vendedor.discard(usuario)
    vendedores_aprobados.add(usuario)
    await update.message.reply_text(f"✅ Vendedor @{usuario} aprobado.")

async def rechazar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if f"@{update.message.from_user.username}" != ADMIN_USERNAME:
        return await update.message.reply_text("❌ No tienes permiso para hacer esto.")
    if not context.args:
        return await update.message.reply_text("Uso: /rechazar usuario")
    usuario = context.args[0]
    solicitudes_vendedor.discard(usuario)
    await update.message.reply_text(f"🚫 Solicitud de @{usuario} rechazada.")

async def anadir_articulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in vendedores_aprobados:
        return await update.message.reply_text("❌ No estás autorizado como vendedor.")
    if len(context.args) < 3:
        return await update.message.reply_text("Uso: /anadirarticulo nombre precio stock")
    try:
        nombre = context.args[0]
        precio = float(context.args[1])
        stock = int(context.args[2])
    except ValueError:
        return await update.message.reply_text("⚠️ Precio y stock deben ser números.")
    articulos.append({"vendedor": user, "nombre": nombre, "precio": precio, "stock": stock})
    await update.message.reply_text(f"✅ Artículo '{nombre}' añadido.")

async def listado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not articulos:
        return await update.message.reply_text("📭 No hay artículos disponibles.")
    texto = "📋 *Artículos disponibles:*\n"
    for art in articulos:
        texto += f"- {art['nombre']} | 💰 {art['precio']}€ | 📦 Stock: {art['stock']} | 🛒 @{art['vendedor']}\n"
    await update.message.reply_text(texto, parse_mode="Markdown")

async def eliminar_articulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if f"@{update.message.from_user.username}" != ADMIN_USERNAME:
        return await update.message.reply_text("❌ No tienes permiso para hacer esto.")
    if not context.args:
        return await update.message.reply_text("Uso: /eliminararticulo nombre")
    nombre = context.args[0]
    global articulos
    articulos = [a for a in articulos if a["nombre"] != nombre]
    await update.message.reply_text(f"🗑️ Artículo '{nombre}' eliminado.")

async def bajavendedor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if f"@{update.message.from_user.username}" != ADMIN_USERNAME:
        return await update.message.reply_text("❌ No tienes permiso para hacer esto.")
    if not context.args:
        return await update.message.reply_text("Uso: /bajavendedor usuario")
    usuario = context.args[0]
    vendedores_aprobados.discard(usuario)
    await update.message.reply_text(f"🚷 Vendedor @{usuario} dado de baja.")

async def echo_todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde a cualquier mensaje no comando, para testear el webhook."""
    logger.info(f"Mensaje recibido: {update.message.text}")
    await update.message.reply_text("✅ Recibí tu mensaje.")

# ----------------------------
# MAIN
# ----------------------------
def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("solicitarvendedor", solicitar_vendedor))
    application.add_handler(CommandHandler("aprobar", aprobar))
    application.add_handler(CommandHandler("rechazar", rechazar))
    application.add_handler(CommandHandler("anadirarticulo", anadir_articulo))  # sin ñ
    application.add_handler(CommandHandler("listado", listado))
    application.add_handler(CommandHandler("eliminararticulo", eliminar_articulo))
    application.add_handler(CommandHandler("bajavendedor", bajavendedor))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_todo))

    webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
    logger.info(f"Iniciando webhook en {webhook_url}")
    application.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=webhook_url)

if __name__ == "__main__":
    main()
