import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

(ASK_BUDGET_NAME, ASK_BUDGET_AMOUNT, ASK_BUDGET_TYPE,
 ASK_EXPENSE_AMOUNT, ASK_EXPENSE_DESC) = range(5)

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"budgets": {}, "transactions": []}
    return data[uid]

def progress_bar(pct, length=10):
    filled = min(int(pct / 100 * length), length)
    return "X" * filled + "." * (length - filled)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Hola! Soy tu bot de presupuestos.*\n\n"
        "Comandos disponibles:\n"
        "/nuevo\_presupuesto - Crear un presupuesto\n"
        "/gasto - Registrar un gasto\n"
        "/saldos - Ver saldos actuales\n"
        "/categorias - Ver tus presupuestos creados\n"
        "/reporte - Reporte detallado\n"
        "/historial - Ultimos gastos\n"
        "/nuevo\_mes - Reiniciar gastos del mes\n"
        "/reset - Borrar todo\n\n"
        "Atajo rapido: escribe directamente\n"
        "`monto categoria descripcion`\n"
        "Ej: `15000 mercado frutas`",
        parse_mode="Markdown"
    )

async def nuevo_presupuesto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Nuevo presupuesto*\n\nComo se llamara?\n_(ej: Mercado, Transporte, Netflix...)_",
        parse_mode="Markdown"
    )
    return ASK_BUDGET_NAME

async def ask_budget_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["new_budget_name"] = name
    await update.message.reply_text(
        f"Cuanto asignas a *{name}*?\n_(solo el numero, ej: 500000)_",
        parse_mode="Markdown"
    )
    return ASK_BUDGET_AMOUNT

async def ask_budget_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw = update.message.text.strip().replace(" ", "").replace(".", "").replace(",", ".")
        amount = float(raw)
    except ValueError:
        await update.message.reply_text("Por favor ingresa solo el numero (ej: 500000)")
        return ASK_BUDGET_AMOUNT
    context.user_data["new_budget_amount"] = amount
    keyboard = [[
        InlineKeyboardButton("Fijo", callback_data="type_fixed"),
        InlineKeyboardButton("Variable", callback_data="type_variable")
    ]]
    await update.message.reply_text(
        "Es un gasto *fijo* (igual cada mes) o *variable*?",
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
    user["budgets"][name] = {"total": amount, "spent": 0, "type": btype, "created": datetime.now().isoformat()}
    save_data(data)
    await query.edit_message_text(
        f"Presupuesto creado:\n\n*{name}*\n${amount:,.0f}/mes\nTipo: {btype}\n\nUsa /gasto para registrar.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def gasto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})
    if not budgets:
        await update.message.reply_text("No tienes presupuestos. Usa /nuevo\_presupuesto primero.", parse_mode="Markdown")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(name, callback_data=f"cat_{name}")] for name in budgets.keys()]
    await update.message.reply_text("*Registrar gasto*\n\nEn que categoria?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ASK_EXPENSE_AMOUNT

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["expense_category"] = category
    await query.edit_message_text(f"Categoria: *{category}*\n\nCuanto gastaste? _(solo el numero)_", parse_mode="Markdown")
    return ASK_EXPENSE_DESC

async def ask_expense_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw = update.message.text.strip().replace(" ", "").replace(".", "").replace(",", ".")
        amount = float(raw)
    except ValueError:
        await update.message.reply_text("Solo el numero, ej: 25000")
        return ASK_EXPENSE_DESC
    context.user_data["expense_amount"] = amount
    await update.message.reply_text("Descripcion? _(opcional, escribe - para omitir)_", parse_mode="Markdown")
    return ASK_EXPENSE_AMOUNT

async def save_expense_from_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    if desc == "-":
        desc = ""
    data = load_data()
    user = get_user(data, update.effective_user.id)
    await _register_expense(update, user, data, context.user_data["expense_category"], context.user_data["expense_amount"], desc)
    return ConversationHandler.END

async def quick_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split(None, 2)
    if len(parts) < 2:
        await update.message.reply_text("Formato: `monto categoria descripcion`\nEj: `25000 transporte taxi`\n\nO usa /gasto.", parse_mode="Markdown")
        return
    try:
        raw = parts[0].replace(".", "").replace(",", ".")
        amount = float(raw)
    except ValueError:
        await update.message.reply_text("El primer valor debe ser el monto. Ej: `25000 mercado`", parse_mode="Markdown")
        return
    category_input = parts[1].lower().strip()
    desc = parts[2] if len(parts) > 2 else ""
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})
    if not budgets:
        await update.message.reply_text("No tienes presupuestos. Usa /nuevo\_presupuesto primero.", parse_mode="Markdown")
        return
    matched = None
    for name in budgets.keys():
        if category_input in name.lower() or name.lower() in category_input:
            matched = name
            break
    if not matched:
        cats = "\n".join([f"- {n}" for n in budgets.keys()])
        await update.message.reply_text(f"No encontre la categoria *{parts[1]}*.\n\nTus categorias:\n{cats}", parse_mode="Markdown")
        return
    await _register_expense(update, user, data, matched, amount, desc)

async def _register_expense(update, user, data, category, amount, desc):
    budget = user["budgets"][category]
    budget["spent"] += amount
    remaining = budget["total"] - budget["spent"]
    pct = (budget["spent"] / budget["total"] * 100) if budget["total"] > 0 else 0
    user["transactions"].append({"category": category, "amount": amount, "desc": desc, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    save_data(data)
    if pct >= 100:
        status = "PRESUPUESTO AGOTADO"
    elif pct >= 80:
        status = "Casi agotado"
    elif pct >= 50:
        status = "A la mitad"
    else:
        status = "En buen estado"
    msg = f"Gasto registrado\n\n*{category}*\n-${amount:,.0f}"
    if desc:
        msg += f" ({desc})"
    msg += f"\n\nUsado: ${budget['spent']:,.0f} / ${budget['total']:,.0f} ({pct:.1f}%)\nSaldo: *${remaining:,.0f}*\n{status}"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def saldos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})
    if not budgets:
        await update.message.reply_text("No tienes presupuestos. Usa /nuevo\_presupuesto", parse_mode="Markdown")
        return
    lines = ["*Saldos actuales*\n"]
    for name, b in budgets.items():
        remaining = b["total"] - b["spent"]
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        bar = progress_bar(pct)
        lines.append(f"*{name}* ({b['type']})\n{bar} {pct:.0f}%\nSaldo: ${remaining:,.0f} de ${b['total']:,.0f}\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def categorias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})
    if not budgets:
        await update.message.reply_text("No tienes presupuestos creados. Usa /nuevo\_presupuesto", parse_mode="Markdown")
        return
    fijos = {k: v for k, v in budgets.items() if v["type"] == "Fijo"}
    variables = {k: v for k, v in budgets.items() if v["type"] == "Variable"}
    lines = [f"*Tus presupuestos* ({len(budgets)} en total)\n"]
    if fijos:
        lines.append("*Fijos:*")
        for name, b in fijos.items():
            lines.append(f"  - *{name}* - ${b['total']:,.0f}/mes")
    if variables:
        lines.append("\n*Variables:*")
        for name, b in variables.items():
            lines.append(f"  - *{name}* - ${b['total']:,.0f}/mes")
    total = sum(b["total"] for b in budgets.values())
    lines.append(f"\nTotal presupuestado: *${total:,.0f}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def nuevo_mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})
    if not budgets:
        await update.message.reply_text("No tienes presupuestos. Usa /nuevo\_presupuesto", parse_mode="Markdown")
        return
    keyboard = [[
        InlineKeyboardButton("Si, iniciar nuevo mes", callback_data="confirm_nuevo_mes"),
        InlineKeyboardButton("Cancelar", callback_data="cancel_nuevo_mes")
    ]]
    lines = ["*Cerrar mes y reiniciar gastos*\n",
             "Se reiniciaran los gastos a $0.\nLos montos y categorias se *conservan*.\n",
             "*Resumen del mes actual:*"]
    for name, b in budgets.items():
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        lines.append(f"  - {name}: gasto ${b['spent']:,.0f} ({pct:.0f}%)")
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def confirm_nuevo_mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_nuevo_mes":
        data = load_data()
        user = get_user(data, query.from_user.id)
        budgets = user.get("budgets", {})
        user["transactions"].append({
            "type": "cierre_mes",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "mes": datetime.now().strftime("%B %Y"),
            "resumen": {name: b["spent"] for name, b in budgets.items()}
        })
        for name in budgets:
            budgets[name]["spent"] = 0
        save_data(data)
        cats = "\n".join([f"  - {name}: ${b['total']:,.0f}" for name, b in budgets.items()])
        await query.edit_message_text(f"*Nuevo mes iniciado!*\n\nTodos los gastos en $0.\nCategorias activas:\n{cats}", parse_mode="Markdown")
    else:
        await query.edit_message_text("Operacion cancelada.")

async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    budgets = user.get("budgets", {})
    if not budgets:
        await update.message.reply_text("No tienes presupuestos aun.")
        return
    total_asignado = sum(b["total"] for b in budgets.values())
    total_gastado = sum(b["spent"] for b in budgets.values())
    pct_g = (total_gastado / total_asignado * 100) if total_asignado else 0
    fijos = {k: v for k, v in budgets.items() if v["type"] == "Fijo"}
    variables = {k: v for k, v in budgets.items() if v["type"] == "Variable"}
    lines = ["*Reporte general*\n",
             f"Total asignado: *${total_asignado:,.0f}*",
             f"Total gastado: *${total_gastado:,.0f}* ({pct_g:.1f}%)",
             f"Total restante: *${total_asignado - total_gastado:,.0f}*\n",
             "*Gastos Fijos:*"]
    for name, b in fijos.items():
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        lines.append(f"  - {name}: ${b['spent']:,.0f} / ${b['total']:,.0f} ({pct:.0f}%)")
    lines.append("\n*Gastos Variables:*")
    for name, b in variables.items():
        pct = (b["spent"] / b["total"] * 100) if b["total"] > 0 else 0
        lines.append(f"  - {name}: ${b['spent']:,.0f} / ${b['total']:,.0f} ({pct:.0f}%)")
    lines.append("\n*Distribucion del presupuesto:*")
    for name, b in budgets.items():
        pct_of_total = (b["total"] / total_asignado * 100) if total_asignado else 0
        lines.append(f"  - {name}: {pct_of_total:.1f}% del total")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = get_user(data, update.effective_user.id)
    txs = [t for t in user.get("transactions", []) if t.get("type") != "cierre_mes"]
    if not txs:
        await update.message.reply_text("No hay transacciones aun.")
        return
    lines = ["*Ultimos 10 gastos:*\n"]
    for tx in reversed(txs[-10:]):
        desc = f" - {tx['desc']}" if tx.get("desc") else ""
        lines.append(f"- `{tx['date']}` | *{tx['category']}* | ${tx['amount']:,.0f}{desc}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("Si, borrar todo", callback_data="confirm_reset"),
        InlineKeyboardButton("Cancelar", callback_data="cancel_reset")
    ]]
    await update.message.reply_text("Seguro que quieres borrar *todo*? Esta accion no se puede deshacer.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_reset":
        data = load_data()
        data[str(query.from_user.id)] = {"budgets": {}, "transactions": []}
        save_data(data)
        await query.edit_message_text("Todo borrado. Usa /nuevo\_presupuesto para empezar.", parse_mode="Markdown")
    else:
        await query.edit_message_text("Operacion cancelada.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operacion cancelada.")
    return ConversationHandler.END

def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("Define TELEGRAM_TOKEN en las variables de entorno.")

    app = Application.builder().token(token).build()

    budget_conv = ConversationHandler(
        entry_points=[CommandHandler("nuevo_presupuesto", nuevo_presupuesto)],
        states={
            ASK_BUDGET_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_budget_amount)],
            ASK_BUDGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_budget_type)],
            ASK_BUDGET_TYPE:   [CallbackQueryHandler(save_budget, pattern="^type_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

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
    app.add_handler(CommandHandler("categorias", categorias))
    app.add_handler(CommandHandler("reporte", reporte))
    app.add_handler(CommandHandler("historial", historial))
    app.add_handler(CommandHandler("nuevo_mes", nuevo_mes))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(confirm_reset, pattern="^(confirm|cancel)_reset$"))
    app.add_handler(CallbackQueryHandler(confirm_nuevo_mes, pattern="^(confirm|cancel)_nuevo_mes$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quick_expense))

    logger.info("Bot iniciado correctamente.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
