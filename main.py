from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    chat_id = data.get("message", {}).get("chat", {}).get("id")
    text = data.get("message", {}).get("text")

    if chat_id and text:
        reply = f"Hola 👋, dijiste: {text}"
        async with httpx.AsyncClient() as client:
            await client.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": reply
            })

    return {"ok": True}

@app.on_event("startup")
async def set_webhook():
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/setWebhook", json={
            "url": f"{WEBHOOK_URL}/webhook"
        })    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c//100},{c%100:02d} €"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
          user_id INTEGER PRIMARY KEY,
          username TEXT,
          role TEXT CHECK(role IN ('admin','seller','buyer')) NOT NULL DEFAULT 'buyer'
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          seller_id INTEGER NOT NULL,
          name TEXT NOT NULL,
          price_cents INTEGER NOT NULL,
          stock INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(seller_id) REFERENCES users(user_id)
        )""")
        await db.commit()

async def get_user(db, user_id: int) -> Optional[Dict[str, Any]]:
    cur = await db.execute("SELECT user_id, username, role FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    if row:
        return {"user_id": row[0], "username": row[1], "role": row[2]}
    return None

async def ensure_user(update: Update) -> Dict[str, Any]:
    uid = update.effective_user.id
    uname = update.effective_user.username
    async with aiosqlite.connect(DB_PATH) as db:
        u = await get_user(db, uid)
        if not u:
            role = "buyer"
            if ADMIN_USER_ID and str(uid) == str(ADMIN_USER_ID):
                role = "admin"
            await db.execute("INSERT INTO users(user_id, username, role) VALUES(?,?,?)", (uid, uname, role))
            await db.commit()
            u = {"user_id": uid, "username": uname, "role": role}
        else:
            # actualizar username por si cambia
            if u["username"] != uname:
                await db.execute("UPDATE users SET username=? WHERE user_id=?", (uname, uid))
                await db.commit()
                u["username"] = uname
        return u

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await ensure_user(update)
    if u["role"] == "admin":
        text = "Hola admin. Puedes aprobar vendedores desde las solicitudes. Usa /catalogo para ver el escaparate."
    elif u["role"] == "seller":
        text = "Hola vendedor. Usa /producto_nuevo o /producto para añadir. /mis_productos para editar. /catalogo para ver."
    else:
        text = "Bienvenido. Puedes ver el catálogo con /catalogo. Si quieres vender, usa /solicitar_vendedor."
    await update.message.reply_text(text)

async def solicitar_vendedor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    applicant = await ensure_user(update)
    if applicant["role"] == "seller":
        await update.message.reply_text("Ya eres vendedor.")
        return
    if str(applicant["user_id"]) == str(ADMIN_USER_ID):
        await update.message.reply_text("Eres admin; ya puedes vender si lo necesitas.")
        return
    # Notificar al admin
    if not ADMIN_USER_ID:
        await update.message.reply_text("No hay admin configurado. Pide al admin que establezca ADMIN_USER_ID.")
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aprobar", callback_data=f"approve:{applicant['user_id']}"),
        InlineKeyboardButton("❌ Rechazar", callback_data=f"reject:{applicant['user_id']}")
    ]])
    msg = f"Solicitud de vendedor:\n• ID: {applicant['user_id']}\n• Usuario: @{applicant['username'] or 'sin_username'}"
    try:
        await context.bot.send_message(chat_id=int(ADMIN_USER_ID), text=msg, reply_markup=kb)
        await update.message.reply_text("Solicitud enviada al admin. Te avisaremos.")
    except Exception:
        await update.message.reply_text("No pude notificar al admin. Avísale manualmente con tu ID.")

async def on_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, user_id_str = data.split(":")
    uid = int(user_id_str)
    async with aiosqlite.connect(DB_PATH) as db:
        if action == "approve":
            await db.execute("UPDATE users SET role='seller' WHERE user_id=?", (uid,))
            await db.commit()
            await query.edit_message_text(f"✅ Aprobado como vendedor: {uid}")
            try:
                await context.bot.send_message(chat_id=uid, text="¡Ya eres vendedor! Usa /producto_nuevo o /producto y /mis_productos.")
            except Exception:
                pass
        elif action == "reject":
            await db.execute("UPDATE users SET role='buyer' WHERE user_id=?", (uid,))
            await db.commit()
            await query.edit_message_text(f"❌ Rechazada solicitud de: {uid}")
            try:
                await context.bot.send_message(chat_id=uid, text="Tu solicitud de vendedor ha sido rechazada.")
            except Exception:
                pass

def seller_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = await ensure_user(update)
        if u["role"] != "seller" and u["role"] != "admin":
            await update.effective_message.reply_text("Necesitas ser vendedor. Usa /solicitar_vendedor.")
            return
        return await func(update, context)
    return wrapper

@seller_only
async def mis_productos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id, name, price_cents, stock FROM products WHERE seller_id=? ORDER BY id DESC", (uid,))
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("No tienes productos. Usa /producto o /producto_nuevo.")
        return
    lines = []
    buttons = []
    for pid, name, price, stock in rows:
        lines.append(f"• [{pid}] {name} — {cents_to_euros(price)} — {stock} ud")
        buttons.append([
            InlineKeyboardButton(f"💶 Precio ({pid})", callback_data=f"editprice:{pid}"),
            InlineKeyboardButton(f"📦 Stock ({pid})", callback_data=f"editstock:{pid}")
        ])
    await update.message.reply_text("\n".join(lines))
    await update.message.reply_text("Editar:", reply_markup=InlineKeyboardMarkup(buttons))

async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
        SELECT u.username, p.name, p.price_cents, p.stock
        FROM products p
        JOIN users u ON u.user_id = p.seller_id
        WHERE p.stock > 0
        ORDER BY u.username, p.name
        """)
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Aún no hay productos.")
        return
    by_seller: Dict[str, list[str]] = {}
    for uname, name, price, stock in rows:
        seller = f"@{uname}" if uname else "Vendedor"
        by_seller.setdefault(seller, []).append(f"- {name} — {cents_to_euros(price)} — {stock} ud")
    parts = []
    for seller, items in by_seller.items():
        parts.append(f"{seller}:\n" + "\n".join(items))
    await update.message.reply_text("\n\n".join(parts))

# Alta rápida: /producto "Nombre" 2,50 100
@seller_only
async def producto_rapido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    m = re.match(r'^/producto\s+"([^"]+)"\s+([0-9.,€]+)\s+(\d+)\s*$', text)
    if not m:
        await update.message.reply_text('Formato: /producto "Nombre con espacios" 2,50 100')
        return
    name, price_txt, stock_txt = m.group(1), m.group(2), m.group(3)
    cents = euros_to_cents(price_txt)
    if cents is None:
        await update.message.reply_text("Precio inválido. Usa formatos como 2, 2.50, 2,50, 2€.")
        return
    stock = int(stock_txt)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products(seller_id, name, price_cents, stock, created_at) VALUES(?,?,?,?,?)",
            (update.effective_user.id, name.strip(), cents, stock, datetime.utcnow().isoformat())
        )
        await db.commit()
    await update.message.reply_text(f"Producto creado: {name} — {cents_to_euros(cents)} — {stock} ud")

# Asistente paso a paso
@seller_only
async def producto_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Nombre del producto:")
    context.user_data["new_product"] = {}
    return NAME

async def pn_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("El nombre no puede estar vacío. Prueba de nuevo:")
        return NAME
    context.user_data["new_product"]["name"] = name
    await update.message.reply_text("Precio (ej: 2,50):")
    return PRICE

async def pn_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cents = euros_to_cents(update.message.text)
    if cents is None:
        await update.message.reply_text("Precio inválido. Ejemplos: 1, 1.00, 1,25, 1€")
        return PRICE
    context.user_data["new_product"]["price_cents"] = cents
    await update.message.reply_text("Stock (entero):")
    return STOCK

async def pn_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock = int(update.message.text)
        if stock < 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("Stock inválido. Debe ser entero >= 0.")
        return STOCK
    uid = update.effective_user.id
    data = context.user_data.get("new_product", {})
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products(seller_id, name, price_cents, stock, created_at) VALUES(?,?,?,?,?)",
            (uid, data["name"], data["price_cents"], stock, datetime.utcnow().isoformat())
        )
        await db.commit()
    await update.message.reply_text(
        f"Creado: {data['name']} — {cents_to_euros(data['price_cents'])} — {stock} ud"
    )
    context.user_data["new_product"] = {}
    return ConversationHandler.END

async def pn_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"] = {}
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END

# Edición precio/stock
async def on_edit_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("editprice:"):
        pid = int(data.split(":")[1])
        context.user_data["edit_pid"] = pid
        await query.edit_message_text(f"Nuevo precio para producto {pid} (ej: 2,50):")
        context.user_data["edit_mode"] = "price"
    elif data.startswith("editstock:"):
        pid = int(data.split(":")[1])
        context.user_data["edit_pid"] = pid
        await query.edit_message_text(f"Nuevo stock para producto {pid} (entero):")
        context.user_data["edit_mode"] = "stock"

async def on_text_after_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("edit_mode")
    pid = context.user_data.get("edit_pid")
    if not mode or not pid:
        return
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        # verificar propiedad
        cur = await db.execute("SELECT seller_id, name FROM products WHERE id=?", (pid,))
        row = await cur.fetchone()
        if not row:
            await update.message.reply_text("Producto no encontrado.")
        elif row[0] != uid:
            await update.message.reply_text("No puedes editar este producto.")
        else:
            if mode == "price":
                cents = euros_to_cents(update.message.text)
                if cents is None:
                    await update.message.reply_text("Precio inválido. Intenta de nuevo (ej: 2,50).")
                    return
                await db.execute("UPDATE products SET price_cents=? WHERE id=?", (cents, pid))
                await db.commit()
                await update.message.reply_text(f"Precio actualizado: {row[1]} → {cents_to_euros(cents)}")
            elif mode == "stock":
                try:
                    stock = int(update.message.text)
                    if stock < 0: raise ValueError()
                except ValueError:
                    await update.message.reply_text("Stock inválido. Intenta de nuevo.")
                    return
                await db.execute("UPDATE products SET stock=? WHERE id=?", (stock, pid))
                await db.commit()
                await update.message.reply_text(f"Stock actualizado: {row[1]} → {stock} ud")
    context.user_data.pop("edit_mode", None)
    context.user_data.pop("edit_pid", None)

# Mini servidor HTTP para health-check
async def health(request):
    return web.Response(text="ok")

async def run_http():
    app = web.Application()
    app.add_routes([web.get("/", health), web.get("/health", health)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()

async def main():
    if not TOKEN:
        raise RuntimeError("Falta TELEGRAM_TOKEN")
    await init_db()
    # Si no hay admin y ADMIN_USER_ID no está, el primer /start seguirá como buyer.
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("catalogo", catalogo))
    application.add_handler(CommandHandler("solicitar_vendedor", solicitar_vendedor))
    application.add_handler(CallbackQueryHandler(on_approval_callback, pattern=r"^(approve|reject):\d+$"))

    application.add_handler(CommandHandler("mis_productos", mis_productos))
    application.add_handler(CommandHandler("producto", producto_rapido))
    conv = ConversationHandler(
        entry_points=[CommandHandler("producto_nuevo", producto_nuevo)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, pn_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pn_price)],
            STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, pn_stock)],
        },
        fallbacks=[CommandHandler("cancelar", pn_cancel)],
    )
    application.add_handler(conv)
    application.add_handler(CallbackQueryHandler(on_edit_buttons, pattern=r"^(editprice|editstock):\d+$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_after_edit))

    # Correr bot y servidor health
    await asyncio.gather(
        run_http(),
        application.initialize(),
        application.start(),
        application.updater.start_polling(allowed_updates=Update.ALL_TYPES),
    )
    # Mantener vivo
    await application.updater.idle()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
