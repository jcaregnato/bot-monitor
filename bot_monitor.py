import yfinance as yf
import schedule
import time
import sqlite3
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# ===== CONFIGURAÇÕES =====
TELEGRAM_TOKEN = "SEU_TOKEN_DO_BOT"
CHAT_ID = "SEU_CHAT_ID"
VARIACAO_ALERTA = 2  # % mínimo para alertar
NORMAIS = ["HGLG11.SA", "BIDI11.SA", "ABEV3.SA"]  # outros ativos
DB_NAME = "bot_monitor.db"

# ===== BOT TELEGRAM =====
updater = Updater(token=TELEGRAM_TOKEN)
bot = updater.bot

# ===== BANCO DE DADOS =====
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# Tabelas: preços e prioritários
cursor.execute("""
CREATE TABLE IF NOT EXISTS precos (
    ticker TEXT PRIMARY KEY,
    preco REAL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS prioritarios (
    ticker TEXT PRIMARY KEY
)
""")
conn.commit()

# ===== FUNÇÕES UTILITÁRIAS =====
def get_preco_anterior(ticker):
    cursor.execute("SELECT preco FROM precos WHERE ticker=?", (ticker,))
    r = cursor.fetchone()
    return r[0] if r else None

def update_preco(ticker, preco):
    cursor.execute("INSERT OR REPLACE INTO precos (ticker, preco) VALUES (?, ?)", (ticker, preco))
    conn.commit()

def get_prioritarios():
    cursor.execute("SELECT ticker FROM prioritarios")
    return [r[0] for r in cursor.fetchall()]

def add_prioritario(ticker):
    cursor.execute("INSERT OR IGNORE INTO prioritarios (ticker) VALUES (?)", (ticker,))
    conn.commit()

def remove_prioritario(ticker):
    cursor.execute("DELETE FROM prioritarios WHERE ticker=?", (ticker,))
    conn.commit()

# ===== CONSULTA ATIVOS =====
def consultar_ativos(tickers):
    resultados = {}
    bloco = 50
    for i in range(0, len(tickers), bloco):
        sublista = tickers[i:i+bloco]
        data = yf.download(sublista, period="1d", interval="1d", progress=False)
        for t in sublista:
            try:
                preco = data['Close'][t][-1]
                resultados[t] = preco
            except:
                resultados[t] = None
    return resultados

# ===== GERAR GRÁFICO DE TENDÊNCIA =====
def gerar_grafico(ticker):
    df = yf.download(ticker, period="7d", interval="1d", progress=False)
    plt.figure(figsize=(4,3))
    plt.plot(df['Close'], marker='o', color='blue')
    plt.title(ticker)
    plt.grid(True)
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# ===== CRIAR RELATÓRIO =====
def criar_relatorio():
    prioritarios = get_prioritarios()
    todos = list(set(prioritarios + NORMAIS))
    precos_atuais = consultar_ativos(todos)
    mensagem = "💹 *Relatório de Ações/FIIs*\n\n"

    for t in todos:
        preco_atual = precos_atuais.get(t, 0)
        preco_ant = get_preco_anterior(t) or preco_atual
        variacao = ((preco_atual - preco_ant)/preco_ant)*100 if preco_ant != 0 else 0
        update_preco(t, preco_atual)

        # cores / emojis
        if t in prioritarios and abs(variacao) >= VARIACAO_ALERTA:
            emoji = "⚠️"
        elif variacao > VARIACAO_ALERTA:
            emoji = "📈"
        elif variacao < -VARIACAO_ALERTA:
            emoji = "📉"
        else:
            emoji = "🔹"

        mensagem += f"{emoji} *{t}*: R$ {preco_atual:.2f} ({variacao:+.2f}%)\n"

    return mensagem

# ===== ENVIAR RELATÓRIO =====
def enviar_relatorio():
    mensagem = criar_relatorio()
    bot.send_message(chat_id=CHAT_ID, text=mensagem, parse_mode="Markdown")

    # enviar gráficos dos prioritários
    for t in get_prioritarios():
        buf = gerar_grafico(t)
        bot.send_photo(chat_id=CHAT_ID, photo=buf)

# ===== COMANDOS TELEGRAM =====
def cmd_add(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Use: /add TICKER")
        return
    ticker = context.args[0].upper()
    add_prioritario(ticker)
    update.message.reply_text(f"✅ Adicionado aos prioritários: {ticker}")

def cmd_remove(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Use: /remove TICKER")
        return
    ticker = context.args[0].upper()
    remove_prioritario(ticker)
    update.message.reply_text(f"❌ Removido dos prioritários: {ticker}")

def cmd_list(update: Update, context: CallbackContext):
    pri = get_prioritarios()
    update.message.reply_text("🌟 Prioritários:\n" + "\n".join(pri) if pri else "Nenhum ativo prioritário.")

updater.dispatcher.add_handler(CommandHandler("add", cmd_add))
updater.dispatcher.add_handler(CommandHandler("remove", cmd_remove))
updater.dispatcher.add_handler(CommandHandler("list", cmd_list))

# ===== AGENDAMENTO =====
schedule.every().day.at("10:00").do(enviar_relatorio)
schedule.every().day.at("12:00").do(enviar_relatorio)
schedule.every().day.at("15:00").do(enviar_relatorio)
schedule.every().day.at("17:00").do(enviar_relatorio)

# ===== LOOP PRINCIPAL =====
print("Bot avançado de monitoramento iniciado...")
updater.start_polling()

while True:
    schedule.run_pending()
    time.sleep(60)
