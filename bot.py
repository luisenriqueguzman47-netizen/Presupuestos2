import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Constantes de estado para ConversationHandler ────────────────────────────
(ASK_BUDGET_NAME, ASK_BUDGET_AMOUNT, ASK_BUDGET_TYPE,
 ASK_EXPENSE_AMOUNT, ASK_EXPENSE_DESC) = range(5)

# ── Persistencia de datos (archivo JSON) ─────────────────────────────────────
DATA_FILE = "data.json"

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"budgets": {}, "transactions": []}
    return data[uid]

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *¡Hola! Soy tu bot de presupuestos.*\n\n"
        "Con comandos simples puedes:\n"
        "• Crear presupuestos\n"
        "• Registrar gastos rápido\n"
        "• Ver reportes\n\n"
        "📌 *Comandos disponibles:*\n"
        "/nuevo\\_presupuesto — Crear un presupuesto\n"
        "/gasto — Registrar un gasto\n"
        "/saldos — Ver saldos actuales\n"
        "/reporte — Reporte detallado\n"
        "/historial — Últimos gastos\n"
        "/reset — Borrar todo y empezar de cero\n\n"
        "💡 *Atajo rápido:* escribe directamente\n"
        "`[monto] [categoría] [descripción opcional]`\n"
        "Ejemplo: `15000 mercado frutas y verduras`",
        parse_mode="Markdown"
    )

# ── CREAR PRESUPUESTO ─────────────────────────────────────────────────────────
async def nuevo_presupuesto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📂 *Nuevo presupuesto*\n\n¿Cómo se llamará este presupuesto?\n"
        "_(ej: Mercado, Transporte, Salidas, Netflix...)_",
        parse_mode="Markdown"
    )
    return ASK_BUDGET_NAME

async def ask_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["new_budget_name"] = name
    await update.message.reply_text(
        f"💰 ¿Cuánto asignas al presupuesto *{name}*?\n"
        "_(solo el número, ej: 500000)_",
        parse_mode="Markdown"
    )
    return ASK_BUDGET_AMOUNT

async def ask_budget_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip().replace(",", ".").replace(".", "").replace(",", "."))
        # Si el usuario escribe 500.000 o 500,000 → lo parseamos bien
        raw = update.message.text.strip().replace(" ", "")
        # Intentar parsear formato colombiano (500.000 o 500000)
        amount = float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("⚠️ Por favor ingresa solo el número (ej: 500000)")
        return ASK_BUDGET_AMOUNT

    context.user_data["new_budget_amount"] = amount
    keyboard = [
        [InlineKeyboardButton("📌 Fijo", callback_data="type_fixed"),
         InlineKeyboardButton("🔄 Variable", callback_data="type_variable")]
    ]
    await update.message.reply_text(
        "¿Este gasto es *fijo* (igual cada mes) o *variable*?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_BUDGET_TYPE

async def save_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    btype = "Fijo" if query.data == "type_fixed" else "Variable"

    data = load_data()
    user = get_user(data, query.from_user.id)

    name = context.user_data["new_budget_name"]
    amount = context.user_data["new_budget_amount"]

    user["budgets"][name] = {
        "total": amount,
        "spent": 0,
        "type": btype,
        "created": datetime.now().isoformat()
    }
    save_data(data)

    await query.edit_message_text(
        f"✅ *Presupuesto creado:*\n\n"
        f"📂 {name}\n"
        f"💰 ${amount:,.0f}\n"
        f"🏷️ {btype}\n\n"
        "Usa /gasto para registrar un gasto en esta categoría.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ── REGISTRAR GASTO (comando /gasto) ─────────────────────────────────────────
async def gasto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})

    if not budgets:
        await update.message.reply_text(
            "⚠️ No tienes presupuestos creados. Usa /nuevo\\_presupuesto primero.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"📂 {name}", callback_data=f"cat_{name}")]
                for name in budgets.keys()]
    await update.message.reply_text(
        "💸 *Registrar gasto*\n\n¿En qué categoría?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_EXPENSE_AMOUNT

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["expense_category"] = category
    await query.edit_message_text(
        f"📂 Categoría: *{category}*\n\n¿Cuánto gastaste? _(solo el número)_",
        parse_mode="Markdown"
    )
    return ASK_EXPENSE_DESC

async def ask_expense_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw = update.message.text.strip().replace(" ", "")
        amount = float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        await update.message.reply_text("⚠️ Solo el número, ej: 25000")
        return ASK_EXPENSE_DESC

    context.user_data["expense_amount"] = amount
    await update.message.reply_text(
        "📝 ¿Descripción del gasto? _(opcional, escribe - para omitir)_"
    )
    return ASK_EXPENSE_AMOUNT  # reutilizamos estado para guardar

async def save_expense_from_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    if desc == "-":
        desc = ""

    data = load_data()
    user = get_user(data, update.effective_user.id)
    category = context.user_data["expense_category"]
    amount = context.user_data["expense_amount"]

    await _register_expense(update, user, data, category, amount, desc)
    return ConversationHandler.END

# ── ATAJO RÁPIDO: mensaje directo ─────────────────────────────────────────────
async def quick_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Formato: [monto] [categoría] [descripción opcional]
    Ej: 15000 mercado frutas y verduras
    """
    text = update.message.text.strip()
    parts = text.split(None, 2)  # máx 3 partes

    if len(parts) < 2:
        await update.message.reply_text(
            "💡 Formato: `monto categoría descripción`\n"
            "Ej: `25000 transporte taxi al trabajo`\n\n"
            "O usa /gasto para el modo guiado.",
            parse_mode="Markdown"
        )
        return

    # Parsear monto
    try:
        raw = parts[0].replace(".", "").replace(",", ".")
        amount = float(raw)
    except ValueError:
        await update.message.reply_text(
            "⚠️ El primer valor debe ser el monto. Ej: `25000 mercado`",
            parse_mode="Markdown"
        )
        return

    category_input = parts[1].lower().strip()
    desc = parts[2] if len(parts) > 2 else ""

    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})

    if not budgets:
        await update.message.reply_text(
            "⚠️ No tienes presupuestos. Usa /nuevo\\_presupuesto primero.",
            parse_mode="Markdown"
        )
        return

    # Buscar categoría (búsqueda flexible)
    matched = None
    for name in budgets.keys():
        if category_input in name.lower() or name.lower() in category_input:
            matched = name
            break

    if not matched:
        cats = "\n".join([f"• {n}" for n in budgets.keys()])
        await update.message.reply_text(
            f"❓ No encontré la categoría *{parts[1]}*.\n\n"
            f"Tus categorías:\n{cats}\n\n"
            f"Intenta de nuevo con el nombre exacto.",
            parse_mode="Markdown"
        )
        return

    await _register_expense(update, user, data, matched, amount, desc)

# ── Función central de registro de gasto ─────────────────────────────────────
async def _register_expense(update, user, data, category, amount, desc):
    budget = user["budgets"][category]
    budget["spent"] += amount
    remaining = budget["total"] - budget["spent"]
    percent_used = (budget["spent"] / budget["total"] * 100) if budget["total"] > 0 else 0

    user["transactions"].append({
        "category": category,
        "amount": amount,
        "desc": desc,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_data(data)

    # Emoji según % gastado
    if percent_used >= 100:
        status = "🔴 ¡Presupuesto agotado!"
    elif percent_used >= 80:
        status = "🟠 Casi agotado"
    elif percent_used >= 50:
        status = "🟡 A la mitad"
    else:
        status = "🟢 En buen estado"

    msg = (
        f"✅ *Gasto registrado*\n\n"
        f"📂 {category}\n"
        f"💸 -${amount:,.0f}"
    )
    if desc:
        msg += f" — _{desc}_"
    msg += (
        f"\n\n"
        f"📊 Usado: ${budget['spent']:,.0f} / ${budget['total']:,.0f} ({percent_used:.1f}%)\n"
        f"💰 Saldo: *${remaining:,.0f}*\n"
        f"{status}"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")

# ── /saldos ───────────────────────────────────────────────────────────────────
async def saldos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})

    if not budgets:
        await update.message.reply_text("No tienes presupuestos aún. Usa /nuevo\\_presupuesto", parse_mode="Markdown")
        return

    lines = ["📊 *Saldos actuales*\n"]
    for name, b in budgets.items():
        remaining = b["total"] - b["spent"]
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        bar = _progress_bar(pct)
        emoji = "🔴" if pct >= 100 else ("🟠" if pct >= 80 else ("🟡" if pct >= 50 else "🟢"))
        lines.append(
            f"{emoji} *{name}* ({b['type']})\n"
            f"{bar} {pct:.0f}%\n"
            f"Saldo: ${remaining:,.0f} de ${b['total']:,.0f}\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /reporte ──────────────────────────────────────────────────────────────────
async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})

    if not budgets:
        await update.message.reply_text("No tienes presupuestos aún.")
        return

    total_asignado = sum(b["total"] for b in budgets.values())
    total_gastado = sum(b["spent"] for b in budgets.values())
    total_restante = total_asignado - total_gastado

    fijos = {k: v for k, v in budgets.items() if v["type"] == "Fijo"}
    variables = {k: v for k, v in budgets.items() if v["type"] == "Variable"}

    lines = [
        "📈 *Reporte general*\n",
        f"💰 Total asignado: *${total_asignado:,.0f}*",
        f"💸 Total gastado: *${total_gastado:,.0f}* ({(total_gastado/total_asignado*100) if total_asignado else 0:.1f}%)",
        f"✅ Total restante: *${total_restante:,.0f}*\n",
        "📌 *Gastos Fijos:*"
    ]
    for name, b in fijos.items():
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        lines.append(f"  • {name}: ${b['spent']:,.0f} / ${b['total']:,.0f} ({pct:.0f}%)")

    lines.append("\n🔄 *Gastos Variables:*")
    for name, b in variables.items():
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        lines.append(f"  • {name}: ${b['spent']:,.0f} / ${b['total']:,.0f} ({pct:.0f}%)")

    # Distribución porcentual
    lines.append("\n📊 *Distribución del presupuesto:*")
    for name, b in budgets.items():
        pct_of_total = (b["total"] / total_asignado * 100) if total_asignado else 0
        lines.append(f"  • {name}: {pct_of_total:.1f}% del total")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /historial ────────────────────────────────────────────────────────────────
async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    txs = user.get("transactions", [])

    if not txs:
        await update.message.reply_text("No hay transacciones aún.")
        return

    lines = ["🕐 *Últimos 10 gastos:*\n"]
    for tx in reversed(txs[-10:]):
        desc = f" — {tx['desc']}" if tx.get("desc") else ""
        lines.append(f"• `{tx['date']}` | *{tx['category']}* | ${tx['amount']:,.0f}{desc}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /reset ────────────────────────────────────────────────────────────────────
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚠️ Sí, borrar todo", callback_data="confirm_reset"),
         InlineKeyboardButton("❌ Cancelar", callback_data="cancel_reset")]
    ]
    await update.message.reply_text(
        "¿Seguro que quieres borrar *todos* tus presupuestos y transacciones?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_reset":
        data = load_data()
        uid = str(query.from_user.id)
        data[uid] = {"budgets": {}, "transactions": []}
        save_data(data)
        await query.edit_message_text("✅ Todo borrado. Usa /nuevo\\_presupuesto para empezar.", parse_mode="Markdown")
    else:
        await query.edit_message_text("❌ Operación cancelada.")

# ── Cancelar conversación ─────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

# ── Helper: barra de progreso ─────────────────────────────────────────────────
def _progress_bar(pct: float, length: int = 10) -> str:
    filled = min(int(pct / 100 * length), length)
    return "█" * filled + "░" * (length - filled)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("❌ Define TELEGRAM_TOKEN en las variables de entorno.")

    app = Application.builder().token(token).build()

    # Conversación: crear presupuesto
    budget_conv = ConversationHandler(
        entry_points=[CommandHandler("nuevo_presupuesto", nuevo_presupuesto)],
        states={
            ASK_BUDGET_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_budget_amount)],
            ASK_BUDGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_budget_type)],
            ASK_BUDGET_TYPE:   [CallbackQueryHandler(save_budget, pattern="^type_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Conversación: registrar gasto por comando
    expense_conv = ConversationHandler(
        entry_points=[CommandHandler("gasto", gasto_cmd)],
        states={
            ASK_EXPENSE_AMOUNT: [
                CallbackQueryHandler(select_category, pattern="^cat_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_expense_from_cmd),
            ],
            ASK_EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_expense_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(budget_conv)
    app.add_handler(expense_conv)
    app.add_handler(CommandHandler("saldos", saldos))
    app.add_handler(CommandHandler("reporte", reporte))
    app.add_handler(CommandHandler("historial", historial))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(confirm_reset, pattern="^(confirm|cancel)_reset$"))

    # Atajo rápido: mensajes de texto libre
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quick_expense))

    logger.info("🤖 Bot iniciado correctamente.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
