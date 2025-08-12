# bot.py
import os
import logging
from datetime import datetime

import database as db

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# conversation states
NAME, PRICE, STOCK = range(3)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # obligatorio
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")        # ejemplo: https://mi-app.onrender.com
PORT = int(os.environ.get("PORT", "5000"))         # Render define PORT automáticamente

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN no definido en variables de entorno.")

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola! Soy el bot expositor.\n"
        "Si quieres darte de alta como vendedor usa /alta\n"
        "Si eres el administrador, inicia y ejecuta /me_admin para registrarte como admin."
    )

async def me_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.set_setting("admin_id", str(user.id))
    await update.message.reply_text(f"Registrado como administrador (id={user.id}).")

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        admin = db.get_setting("admin_id")
        uid = update.effective_user.id
        if admin and str(admin) == str(uid):
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("Acceso denegado. Sólo el administrador puede usar este comando.")
    return wrapper

async def alta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    db.add_vendor(username, user.id)
    admin_id = db.get_setting("admin_id")
    await update.message.reply_text("Solicitud enviada. En espera de aprobación del administrador.")
    if admin_id:
        await context.bot.send_message(int(admin_id),
            f"Nuevo vendedor en espera: @{username}\nUsa /aprobar {username} o /rechazar {username}")

@admin_required
async def aprobar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /aprobar <username>")
        return
    username = args[0].lstrip("@")
    v = db.get_vendor_by_username(username)
    if not v:
        await update.message.reply_text("Vendedor no encontrado.")
        return
    db.set_vendor_status(username, "aprobado")
    await update.message.reply_text(f"@{username} aprobado.")
    if v["user_id"]:
        await context.bot.send_message(int(v["user_id"]), "Tu cuenta ha sido aprobada. Ya puedes añadir productos con /add")

@admin_required
async def rechazar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /rechazar <username>")
        return
    username = args[0].lstrip("@")
    v = db.get_vendor_by_username(username)
    if not v:
        await update.message.reply_text("Vendedor no encontrado.")
        return
    db.set_vendor_status(username, "rechazado")
    await update.message.reply_text(f"@{username} rechazado.")
    if v["user_id"]:
        await context.bot.send_message(int(v["user_id"]), "Tu solicitud ha sido rechazada.")

# ---------------- add product (conversación) ----------------
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    vendor = db.get_vendor_by_username(username)
    admin_id = db.get_setting("admin_id")
    is_admin = (admin_id and str(admin_id) == str(user.id))
    if not vendor and not is_admin:
        await update.message.reply_text("No estás registrado como vendedor. Usa /alta para solicitarlo.")
        return ConversationHandler.END
    if vendor and vendor["status"] != "aprobado" and not is_admin:
        await update.message.reply_text("Tu cuenta no está aprobada aún.")
        return ConversationHandler.END
    await update.message.reply_text("Introduce el nombre del producto:")
    return NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["prod_name"] = update.message.text.strip()
    await update.message.reply_text("Introduce el precio (ej: 12.50):")
    return PRICE

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        price = float(text)
    except ValueError:
        await update.message.reply_text("Precio inválido. Introduce un número (ej: 12.50):")
        return PRICE
    context.user_data["prod_price"] = price
    await update.message.reply_text("Introduce el stock (número entero):")
    return STOCK

async def add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        stock = int(text)
    except ValueError:
        await update.message.reply_text("Stock inválido. Introduce un número entero:")
        return STOCK
    context.user_data["prod_stock"] = stock
    user = update.effective_user
    username = user.username or f"user_{user.id}"
    vendor = db.get_vendor_by_username(username)
    admin_id = db.get_setting("admin_id")
    is_admin = (admin_id and str(admin_id) == str(user.id))
    vendor_id = None
    if vendor:
        vendor_id = vendor["id"]
    elif is_admin:
        db.add_vendor(username, user.id)
        db.set_vendor_status(username, "aprobado")
        v = db.get_vendor_by_username(username)
        vendor_id = v["id"]
    prod_id = db.add_product(vendor_id, context.user_data["prod_name"], context.user_data["prod_price"], context.user_data["prod_stock"])
    await update.message.reply_text(f"Producto añadido con id {prod_id}.")
    return ConversationHandler.END

# ---------------- catálogo / búsqueda ----------------
async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prods = db.get_all_products()
    if not prods:
        await update.message.reply_text("No hay productos en el catálogo.")
        return
    lines = []
    for p in prods:
        lines.append(f'ID:{p["id"]} | @{p["username"] or "anon"} | {p["name"]} | {p["price"]}€ | stock:{p["stock"]}')
    await update.message.reply_text("\n".join(lines))

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /buscar <texto>")
        return
    q = " ".join(context.args).lower()
    prods = db.search_products(q)
    if not prods:
        await update.message.reply_text("No se han encontrado productos.")
        return
    lines = [f'ID:{p["id"]} | @{p["username"] or "anon"} | {p["name"]} | {p["price"]}€ | stock:{p["stock"]}' for p in prods]
    await update.message.reply_text("\n".join(lines))

# -------------- editar / eliminar --------------
async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /del <product_id>")
        return
    try:
        pid = int(context.args[0])
    except:
        await update.message.reply_text("ID inválido.")
        return
    prod = db.get_product_by_id(pid)
    if not prod:
        await update.message.reply_text("Producto no encontrado.")
        return
    user = update.effective_user
    admin_id = db.get_setting("admin_id")
    is_admin = (admin_id and str(admin_id) == str(user.id))
    owner_vendor = None
    if prod["vendor_id"]:
        v = db.get_vendor_by_id(prod["vendor_id"])
        owner_vendor = v["username"] if v else None
    if not is_admin and owner_vendor != (user.username or f"user_{user.id}"):
        await update.message.reply_text("No tienes permiso para borrar este producto.")
        return
    db.delete_product(pid)
    await update.message.reply_text("Producto eliminado.")

async def edit_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /edit_stock <product_id> <nuevo_stock>")
        return
    try:
        pid = int(context.args[0]); new_stock = int(context.args[1])
    except:
        await update.message.reply_text("Argumentos inválidos.")
        return
    prod = db.get_product_by_id(pid)
    if not prod:
        await update.message.reply_text("Producto no encontrado.")
        return
    user = update.effective_user
    admin_id = db.get_setting("admin_id")
    is_admin = (admin_id and str(admin_id) == str(user.id))
    owner_vendor = None
    if prod["vendor_id"]:
        v = db.get_vendor_by_id(prod["vendor_id"])
        owner_vendor = v["username"] if v else None
    if not is_admin and owner_vendor != (user.username or f"user_{user.id}"):
        await update.message.reply_text("No tienes permiso para editar este producto.")
        return
    db.update_stock(pid, new_stock)
    await update.message.reply_text("Stock actualizado.")

async def edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /edit_price <product_id> <nuevo_precio>")
        return
    try:
        pid = int(context.args[0]); new_price = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("Argumentos inválidos.")
        return
    prod = db.get_product_by_id(pid)
    if not prod:
        await update.message.reply_text("Producto no encontrado.")
        return
    user = update.effective_user
    admin_id = db.get_setting("admin_id")
    is_admin = (admin_id and str(admin_id) == str(user.id))
    owner_vendor = None
    if prod["vendor_id"]:
        v = db.get_vendor_by_id(prod["vendor_id"])
        owner_vendor = v["username"] if v else None
    if not is_admin and owner_vendor != (user.username or f"user_{user.id}"):
        await update.message.reply_text("No tienes permiso para editar este producto.")
        return
    db.update_price(pid, new_price)
    await update.message.reply_text("Precio actualizado.")

@admin_required
async def baja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /baja <username>")
        return
    username = context.args[0].lstrip("@")
    v = db.get_vendor_by_username(username)
    if not v:
        await update.message.reply_text("Vendedor no encontrado.")
        return
    db.set_vendor_status(username, "baja")
    await update.message.reply_text(f"@{username} dado de baja.")

# ---------------- main ----------------
def main():
    db.init_db()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("me_admin", me_admin))
    application.add_handler(CommandHandler("alta", alta))
    application.add_handler(CommandHandler("aprobar", aprobar))
    application.add_handler(CommandHandler("rechazar", rechazar))
    application.add_handler(CommandHandler("catalogo", catalogo))
    application.add_handler(CommandHandler("buscar", buscar))
    application.add_handler(CommandHandler("del", delete_product))
    application.add_handler(CommandHandler("edit_stock", edit_stock))
    application.add_handler(CommandHandler("edit_price", edit_price))
    application.add_handler(CommandHandler("baja", baja))

    # conversation for /add
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_stock)],
        },
        fallbacks=[]
    )
    application.add_handler(conv_handler)

# webhook setup (v20+ compatible)
webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
logger.info("Starting webhook on %s", webhook_url)
application.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=webhook_url
)

if __name__ == "__main__":
    main()
