# bot_market.py
# Telegram bot para alta de vendedores y alta de productos
# Requisitos: python-telegram-bot >= 21, Python 3.10+

import os
import shlex
import sqlite3
import logging
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, ConversationHandler, MessageHandler, filters
)

# ========= CONFIG =========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PON_AQUI_TU_TOKEN")
ADMIN_USERNAME = "GH43L"  # sin @
ADMIN_USER_ID = None      # opcional: pon aquí tu ID numérico si lo sabes (ej. 123456789)

DB_PATH = os.getenv("DB_PATH", "market.db")

# ========= LOGGING =========
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ========= DB =========
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    role TEXT CHECK (role IN ('pending','seller','buyer','rejected')) DEFAULT 'buyer',
    created_at TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    stock INTEGER NOT NULL,
    created_at TEXT,
    FOREIGN KEY (seller_id) REFERENCES users(user_id)
)
""")
conn.commit()

# ========= HELPERS =========
def is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    if ADMIN_USER_ID is not None and user.id == ADMIN_USER_ID:
        return True
    # Fallback por username
    if user.username and user.username.lower() == ADMIN_USERNAME.lower():
        return True
    return False

def get_role(user_id: int) -> str:
    cur = conn.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else "buyer"

def upsert_user(user_id: int, username: str | None, role: str | None = None):
    cur = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    exists = cur.fetchone() is not None
    now = datetime.utcnow().isoformat()
    if exists:
        if role:
            conn.execute(
                "UPDATE users SET username = ?, role = ? WHERE user_id = ?",
                (username, role, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id),
            )
    else:
        conn.execute(
            "INSERT INTO users (user_id, username, role, created_at) VALUES (?,?,?,?)",
            (user_id, username, role or "buyer", now),
        )
    conn.commit()

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup | None = None):
    # Intento 1: ADMIN_USER_ID
    if ADMIN_USER_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=text, reply_markup=keyboard)
            return
        except Exception as e:
            logger.warning(f"No se pudo notificar por ID: {e}")
    # Intento 2: por username (requires deep-link o chat previo)
    if ADMIN_USERNAME:
        # No existe envío directo por username sin chat_id; como fallback, log
        logger.info(f"[ADMIN @{ADMIN_USERNAME}] {text}")

def parse_price(text: str) -> float | None:
    try:
        # admite "1,20" o "1.20"
        norm = text.replace(",", ".")
        value = float(norm)
        return value if value >= 0 else None
    except ValueError:
        return None

def parse_stock(text: str) -> int | None:
    try:
        value = int(text)
        return value if value >= 0 else None
    except ValueError:
        return None

# ========= HANDLERS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username)
    await update.message.reply_text(
        "¡Hola! Soy tu bot de mercado.\n\n"
        "Comandos disponibles:\n"
        "• /solicitar_vendedor – pedir alta como vendedor\n"
        "• /producto \"Nombre\" Precio Stock – alta rápida de producto (si eres vendedor)\n"
        "• /producto_nuevo – asistente paso a paso\n"
        "• /cancel – cancelar el asistente"
    )
    # Si el que escribe es el admin por username, podemos registrar su ID para la sesión
    global ADMIN_USER_ID
    if is_admin(update) and ADMIN_USER_ID is None:
        ADMIN_USER_ID = user.id
        logger.info(f"ADMIN_USER_ID configurado a {ADMIN_USER_ID}")

async def solicitar_vendedor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = get_role(user.id)
    if role == "seller":
        await update.message.reply_text("Ya eres vendedor. Puedes usar /producto o /producto_nuevo.")
        return
    if role == "pending":
        await update.message.reply_text("Tu solicitud ya está pendiente. El administrador la revisará pronto.")
        return

    upsert_user(user.id, user.username, role="pending")
    await update.message.reply_text("Solicitud enviada. Te avisaremos cuando se revise.")

    # Notificar al admin con botones
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aprobar", callback_data=f"approve:{user.id}"),
            InlineKeyboardButton("❌ Rechazar", callback_data=f"reject:{user.id}")
        ]
    ])
    text = (
        "Nueva solicitud de vendedor:\n"
        f"• ID: {user.id}\n"
        f"• Usuario: @{user.username if user.username else 'sin_username'}"
    )
    await notify_admin(context, text, keyboard)

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    action, _, uid_str = data.partition(":")
    try:
        target_id = int(uid_str)
    except ValueError:
        await query.edit_message_text("Dato inválido.")
        return

    if not is_admin(update):
        await query.edit_message_text("Solo el administrador puede realizar esta acción.")
        return

    cur = conn.execute("SELECT username, role FROM users WHERE user_id = ?", (target_id,))
    row = cur.fetchone()
    if not row:
        await query.edit_message_text("El usuario ya no existe en la base de datos.")
        return
    username, role = row

    if action == "approve":
        conn.execute("UPDATE users SET role = 'seller' WHERE user_id = ?", (target_id,))
        conn.commit()
        await query.edit_message_text(
            f"Solicitud aprobada: @{username if username else target_id} ahora es vendedor."
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 ¡Tu solicitud ha sido aprobada! Ya puedes usar /producto o /producto_nuevo para añadir productos."
            )
        except Exception as e:
            logger.warning(f"No se pudo notificar al usuario {target_id}: {e}")

    elif action == "reject":
        conn.execute("UPDATE users SET role = 'rejected' WHERE user_id = ?", (target_id,))
        conn.commit()
        await query.edit_message_text(
            f"Solicitud rechazada: @{username if username else target_id}."
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="Tu solicitud ha sido rechazada. Si crees que es un error, contacta con el administrador."
            )
        except Exception as e:
            logger.warning(f"No se pudo notificar al usuario {target_id}: {e}")
    else:
        await query.edit_message_text("Acción no reconocida.")

# ----- /producto (rápido) -----
async def producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if get_role(user.id) != "seller":
        await update.message.reply_text("Necesitas ser vendedor para añadir productos. Usa /solicitar_vendedor.")
        return

    text = update.message.text or ""
    # eliminar el prefijo del comando
    parts = shlex.split(text.replace("/producto", "", 1).strip())
    if len(parts) < 3:
        await update.message.reply_text(
            "Formato: /producto \"Nombre del producto\" Precio Stock\n"
            "Ejemplo: /producto \"Chicle menta\" 1,20 300"
        )
        return

    name = " ".join(parts[:-2]) if len(parts) > 3 else parts[0]
    price_str = parts[-2]
    stock_str = parts[-1]

    price = parse_price(price_str)
    stock = parse_stock(stock_str)
    if price is None:
        await update.message.reply_text("Precio inválido. Usa formato 1,20 o 1.20 y un valor no negativo.")
        return
    if stock is None:
        await update.message.reply_text("Stock inválido. Debe ser un entero no negativo.")
        return

    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO products (seller_id, name, price, stock, created_at) VALUES (?,?,?,?,?)",
        (user.id, name, price, stock, now)
    )
    conn.commit()
    await update.message.reply_text(f"Producto añadido: {name} — precio {price:.2f} — stock {stock}")

# ----- /producto_nuevo (asistente) -----
PNOMBRE, PPRECIO, PSTOCK = range(3)

async def producto_nuevo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if get_role(user.id) != "seller":
        await update.message.reply_text("Necesitas ser vendedor para añadir productos. Usa /solicitar_vendedor.")
        return ConversationHandler.END

    await update.message.reply_text("Vamos a crear un producto.\nDime el nombre del producto:")
    context.user_data["new_product"] = {}
    return PNOMBRE

async def producto_nuevo_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("El nombre no puede estar vacío. Escribe el nombre:")
        return PNOMBRE
    context.user_data["new_product"]["name"] = name
    await update.message.reply_text("Perfecto. ¿Cuál es el precio? (ej. 1,20 o 1.20)")
    return PPRECIO

async def producto_nuevo_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = parse_price(update.message.text or "")
    if price is None:
        await update.message.reply_text("Precio inválido. Prueba de nuevo (ej. 1,20):")
        return PPRECIO
    context.user_data["new_product"]["price"] = price
    await update.message.reply_text("Anotado. ¿Stock inicial? (entero)")
    return PSTOCK

async def producto_nuevo_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stock = parse_stock(update.message.text or "")
    if stock is None:
        await update.message.reply_text("Stock inválido. Escribe un entero no negativo:")
        return PSTOCK

    user = update.effective_user
    data = context.user_data.get("new_product", {})
    name = data.get("name")
    price = data.get("price")

    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO products (seller_id, name, price, stock, created_at) VALUES (?,?,?,?,?)",
        (user.id, name, price, stock, now)
    )
    conn.commit()

    await update.message.reply_text(
        f"Producto creado:\n"
        f"• Nombre: {name}\n"
        f"• Precio: {price:.2f}\n"
        f"• Stock: {stock}"
    )
    context.user_data.pop("new_product", None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_product", None)
    await update.message.reply_text("Asistente cancelado.")
    return ConversationHandler.END

# ========= MAIN =========
def main():
    if not BOT_TOKEN or BOT_TOKEN == "PON_AQUI_TU_TOKEN":
        raise RuntimeError("Configura TELEGRAM_BOT_TOKEN en el entorno o en BOT_TOKEN.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("solicitar_vendedor", solicitar_vendedor))
    app.add_handler(CallbackQueryHandler(handle_review, pattern="^(approve|reject):"))

    app.add_handler(CommandHandler("producto", producto))

    conv = ConversationHandler(
        entry_points=[CommandHandler("producto_nuevo", producto_nuevo_start)],
        states={
            PNOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_nuevo_nombre)],
            PPRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_nuevo_precio)],
            PSTOCK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, producto_nuevo_stock)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="producto_nuevo_conv",
        persistent=False,
    )
    app.add_handler(conv)

    logger.info("Bot arrancando…")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
