#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  BOT DE ALERTAS CRYPTO - VERSION PERSONAL                        ║
║  Creado por Emanuel Arano | IA & Trading                         ║
║  youtube.com/@EmanuelAranoIATrading                              ║
╠══════════════════════════════════════════════════════════════════╣
║  Uso personal · Un usuario · Charts · F&G · Noticias            ║
╚══════════════════════════════════════════════════════════════════╝

INSTALACION:
  pip install python-telegram-bot requests feedparser matplotlib

CONFIGURACION:
  TELEGRAM_BOT_TOKEN = tu token de @BotFather
  ADMIN_CHAT_ID      = tu chat ID (obtenlo con @userinfobot)

GitHub: github.com/farano90/crypto-alertas-bot

Dependencias:
  pip install python-telegram-bot requests feedparser matplotlib

Comandos de usuario:
  /solicitar  — Pedir acceso al bot
  /agregar    — Nueva alerta de precio
  /listar     — Ver alertas activas
  /eliminar   — Eliminar una alerta por ID
  /precio     — Consultar precio actual
  /miedo      — Índice Fear & Greed
  /noticias   — Últimas noticias crypto

Comandos de admin:
  /usuarios   — Ver y gestionar solicitudes
"""

import logging
import asyncio
import sqlite3
import os
import io
import time
import requests
import feedparser
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ── Configuración ────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID      = os.environ.get("ADMIN_CHAT_ID", "")

HORA_RESUMEN   = 9   # 9:00 AM — resumen de precios
HORA_NOTICIAS  = 8   # 8:00 AM — noticias del día
COOLDOWN_MIN   = 30  # minutos entre disparos de alertas recurrentes

# ── Exchanges ────────────────────────────────────────────────────
EXCHANGES = {
    "binance": {
        "nombre":     "Binance",
        "precio_url": "https://api.binance.com/api/v3/ticker/price",
        "klines_url": "https://api.binance.com/api/v3/klines",
        "tv_prefix":  "BINANCE",
    },
    "bybit": {
        "nombre":     "Bybit",
        "precio_url": "https://api.bybit.com/v5/market/tickers",
        "klines_url": "https://api.bybit.com/v5/market/kline",
        "tv_prefix":  "BYBIT",
    },
}

# ── Estados de conversación /agregar ─────────────────────────────
(EXCHANGE, SYMBOL, CATEGORIA, COND_PRECIO, PRECIO_ALERTA,
 IND_TIPO, IND_CONDICION, IND_TIMEFRAME, RECURRENTE) = range(9)

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alertas.db")

# cooldown en memoria para alertas recurrentes: aid → timestamp
_cooldown: dict[int, float] = {}

# minutos de cooldown según timeframe para alertas de indicadores
_COOLDOWN_IND: dict[str, int] = {"1h": 60, "4h": 240, "1d": 1440, "1w": 10080}

def _cooldown_mins(alerta: dict) -> int:
    if alerta.get("tipo") == "indicador":
        return _COOLDOWN_IND.get(alerta.get("timeframe", "1h"), 60)
    return COOLDOWN_MIN


# ════════════════════════════════════════════════════════════════
#  BASE DE DATOS
# ════════════════════════════════════════════════════════════════

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alertas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     TEXT    NOT NULL DEFAULT '',
            symbol      TEXT    NOT NULL,
            exchange    TEXT    NOT NULL DEFAULT 'binance',
            tipo        TEXT    NOT NULL,
            precio      REAL    NOT NULL,
            precio_base REAL,
            porcentaje  REAL,
            rango_min   REAL,
            rango_max   REAL,
            recurrente  INTEGER NOT NULL DEFAULT 0,
            activa      INTEGER NOT NULL DEFAULT 1,
            creada      TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    # Migracion inline: agrega columnas nuevas si ya existia la tabla
    cols = {r[1] for r in conn.execute("PRAGMA table_info(alertas)").fetchall()}
    nuevas = {
        "chat_id":       "TEXT NOT NULL DEFAULT ''",
        "precio_base":   "REAL",
        "porcentaje":    "REAL",
        "recurrente":    "INTEGER NOT NULL DEFAULT 0",
        "indicador":     "TEXT",
        "condicion_ind": "TEXT",
        "timeframe":     "TEXT",
    }
    for col, definition in nuevas.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE alertas ADD COLUMN {col} {definition}")
    conn.commit()
    conn.close()
    logger.info(f"Base de datos lista: {DB_PATH}")




# ── Usuarios ─────────────────────────────────────────────────────











def insertar_alerta(chat_id: str, symbol: str, exchange: str, tipo: str,
                    precio: float = 0.0, precio_base: float | None = None,
                    porcentaje: float | None = None,
                    rango_min: float | None = None, rango_max: float | None = None,
                    recurrente: bool = False,
                    indicador: str | None = None,
                    condicion_ind: str | None = None,
                    timeframe: str | None = None) -> int:
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO alertas
           (chat_id, symbol, exchange, tipo, precio, precio_base, porcentaje,
            rango_min, rango_max, recurrente, activa, indicador, condicion_ind, timeframe)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (chat_id, symbol, exchange, tipo, precio, precio_base, porcentaje,
         rango_min, rango_max, 1 if recurrente else 0, indicador, condicion_ind, timeframe),
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    logger.info(f"Alerta #{aid} creada: {symbol} ({exchange}) {tipo}")
    return aid


def obtener_alertas_activas(chat_id: str | None = None) -> list[dict]:
    conn = _get_conn()
    if chat_id:
        rows = conn.execute(
            "SELECT * FROM alertas WHERE activa = 1 AND chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM alertas WHERE activa = 1 ORDER BY id").fetchall()
    conn.close()

    resultado = []
    for r in rows:
        a = {
            "id":           r["id"],
            "chat_id":      r["chat_id"],
            "symbol":       r["symbol"],
            "exchange":     r["exchange"],
            "tipo":         r["tipo"],
            "precio":       r["precio"],
            "precio_base":  r["precio_base"],
            "porcentaje":   r["porcentaje"],
            "recurrente":   bool(r["recurrente"]),
            "activa":       bool(r["activa"]),
            "indicador":    r["indicador"],
            "condicion_ind": r["condicion_ind"],
            "timeframe":    r["timeframe"],
        }
        if r["rango_min"] is not None and r["rango_max"] is not None:
            a["rango"] = (r["rango_min"], r["rango_max"])
        resultado.append(a)
    return resultado


def desactivar_alerta(aid: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("UPDATE alertas SET activa = 0 WHERE id = ?", (aid,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def actualizar_precio_base(aid: int, nuevo_precio: float):
    conn = _get_conn()
    conn.execute("UPDATE alertas SET precio_base = ? WHERE id = ?", (nuevo_precio, aid))
    conn.commit()
    conn.close()


def alerta_existe(aid: int, chat_id: str) -> bool:
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM alertas WHERE id = ? AND chat_id = ?", (aid, chat_id)
    ).fetchone()
    conn.close()
    return row is not None


def obtener_simbolos_activos(chat_id: str) -> list[tuple[str, str]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT symbol, exchange FROM alertas WHERE activa = 1 AND chat_id = ?",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [(r["symbol"], r["exchange"]) for r in rows]


# ════════════════════════════════════════════════════════════════
#  EXCHANGES
# ════════════════════════════════════════════════════════════════

def obtener_precio(symbol: str, exchange: str = "binance") -> float | None:
    cfg = EXCHANGES.get(exchange, EXCHANGES["binance"])
    try:
        if exchange == "binance":
            r = requests.get(cfg["precio_url"], params={"symbol": symbol.upper()}, timeout=5)
            if r.status_code == 200:
                return float(r.json()["price"])
        elif exchange == "bybit":
            r = requests.get(
                cfg["precio_url"],
                params={"category": "spot", "symbol": symbol.upper()},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                    return float(data["result"]["list"][0]["lastPrice"])
    except Exception as e:
        logger.error(f"Error precio {symbol} ({exchange}): {e}")
    return None


_BYBIT_INTERVAL = {"1h": "60", "4h": "240", "1d": "D", "1w": "W"}

def obtener_klines(symbol: str, exchange: str = "binance",
                   timeframe: str = "1h", limit: int = 48) -> list | None:
    """Devuelve lista de [datetime, close] para las últimas `limit` velas del timeframe dado."""
    cfg = EXCHANGES.get(exchange, EXCHANGES["binance"])
    try:
        if exchange == "binance":
            r = requests.get(
                cfg["klines_url"],
                params={"symbol": symbol.upper(), "interval": timeframe, "limit": limit},
                timeout=10,
            )
            if r.status_code == 200:
                return [[datetime.fromtimestamp(k[0] / 1000), float(k[4])] for k in r.json()]
        elif exchange == "bybit":
            bybit_tf = _BYBIT_INTERVAL.get(timeframe, "60")
            r = requests.get(
                cfg["klines_url"],
                params={"category": "spot", "symbol": symbol.upper(),
                        "interval": bybit_tf, "limit": limit},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("retCode") == 0:
                    klines = data["result"]["list"][::-1]
                    return [[datetime.fromtimestamp(int(k[0]) / 1000), float(k[4])] for k in klines]
    except Exception as e:
        logger.error(f"Error klines {symbol} ({exchange}) {timeframe}: {e}")
    return None


def calcular_rsi(closes: list[float], periodo: int = 14) -> float | None:
    if len(closes) < periodo + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    g = [d if d > 0 else 0.0 for d in deltas]
    p = [-d if d < 0 else 0.0 for d in deltas]
    avg_g = sum(g[:periodo]) / periodo
    avg_p = sum(p[:periodo]) / periodo
    for i in range(periodo, len(deltas)):
        avg_g = (avg_g * (periodo - 1) + g[i]) / periodo
        avg_p = (avg_p * (periodo - 1) + p[i]) / periodo
    if avg_p == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_p)


def _ema_series(closes: list[float], periodo: int) -> list[float]:
    k = 2 / (periodo + 1)
    ema = [closes[0]]
    for price in closes[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def simbolo_valido(symbol: str, exchange: str = "binance") -> bool:
    return obtener_precio(symbol, exchange) is not None


def tv_link(exchange: str, symbol: str) -> str:
    cfg = EXCHANGES.get(exchange, EXCHANGES["binance"])
    return f"https://www.tradingview.com/chart/?symbol={cfg['tv_prefix']}:{symbol}"


# ════════════════════════════════════════════════════════════════
#  CHART
# ════════════════════════════════════════════════════════════════

def generar_chart(symbol: str, exchange: str, precio_alerta: float) -> io.BytesIO | None:
    klines = obtener_klines(symbol, exchange)
    if not klines:
        return None

    fechas  = [k[0] for k in klines]
    cierres = [k[1] for k in klines]
    nombre_ex = EXCHANGES.get(exchange, {}).get("nombre", exchange)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")

    ax.plot(fechas, cierres, color="#58a6ff", linewidth=1.8, label="Precio")
    ax.fill_between(fechas, cierres, min(cierres) * 0.995, alpha=0.15, color="#58a6ff")
    ax.axhline(
        y=precio_alerta, color="#f85149", linewidth=1.5,
        linestyle="--", label=f"Alerta: {precio_alerta:,.4f}",
    )

    ax.set_title(f"{symbol}  •  {nombre_ex}  •  48h", color="white", fontsize=13, pad=12)
    ax.set_ylabel("Precio (USDT)", color="#8b949e", fontsize=10)
    ax.tick_params(colors="#8b949e", labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=8))
    plt.xticks(rotation=30, ha="right")
    ax.grid(color="#21262d", linewidth=0.6)
    ax.legend(facecolor="#161b22", labelcolor="white", fontsize=9)
    for spine in ax.spines.values():
        spine.set_color("#30363d")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


# ════════════════════════════════════════════════════════════════
#  FEAR & GREED
# ════════════════════════════════════════════════════════════════

def obtener_fear_greed() -> dict | None:
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=5)
        if r.status_code == 200:
            d = r.json()["data"][0]
            return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception as e:
        logger.error(f"Error Fear & Greed: {e}")
    return None


def _emoji_fg(value: int) -> str:
    if value <= 25:  return "😱"
    if value <= 45:  return "😰"
    if value <= 55:  return "😐"
    if value <= 75:  return "😏"
    return "🤑"


# ════════════════════════════════════════════════════════════════
#  NOTICIAS RSS
# ════════════════════════════════════════════════════════════════

_NEWS_FEEDS = [
    "https://es.cointelegraph.com/rss",
    "https://www.criptonoticias.com/feed/",
]


def obtener_noticias(limit: int = 5) -> list[dict]:
    for url in _NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
            noticias = [
                {"titulo": e.title, "link": e.link, "fuente": feed.feed.get("title", "Crypto News")}
                for e in feed.entries[:limit]
            ]
            if noticias:
                return noticias
        except Exception as e:
            logger.error(f"Error noticias {url}: {e}")
    return []


# ════════════════════════════════════════════════════════════════
#  HELPER DE ACCESO
# ════════════════════════════════════════════════════════════════

async def verificar_acceso(update: Update) -> bool:
    """Solo el dueno del bot puede usarlo (uso personal)."""
    chat_id = str(update.effective_chat.id)
    if chat_id == ADMIN_CHAT_ID:
        return True
    await update.message.reply_text(
        "Este bot es de uso personal.\n"
        "Si quieres tu propio bot visita:\n"
        "youtube.com/@EmanuelAranoIATrading"
    )
    return False


# ════════════════════════════════════════════════════════════════
#  COMANDOS
# ════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    texto = (
        "👋 *Bot de Alertas Crypto - Uso Personal*\n\n"
        "📡 Monitoreo en tiempo real desde *Binance* y *Bybit*\n\n"
        "📋 *Comandos disponibles:*\n"
        "• /agregar — Nueva alerta de precio o indicador\n"
        "• /listar — Ver alertas activas\n"
        "• /eliminar `<ID>` — Eliminar una alerta\n"
        "• /precio `BTCUSDT` — Precio actual\n"
        "• /miedo — Indice Fear and Greed\n"
        "• /noticias — Ultimas noticias crypto\n"
        "• /cancelar — Cancelar operacion actual\n"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")








async def cmd_miedo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    fg = obtener_fear_greed()
    if not fg:
        await update.message.reply_text("❌ No pude obtener el índice en este momento.")
        return
    value = fg["value"]
    barra = "█" * (value // 10) + "░" * (10 - value // 10)
    if value <= 25:
        comentario = "🔴 Zona de miedo extremo — oportunidad histórica de compra para muchos traders."
    elif value <= 45:
        comentario = "🟠 Mercado con miedo — precaución pero posibles oportunidades."
    elif value <= 55:
        comentario = "🟡 Mercado neutral — sin señal clara."
    elif value <= 75:
        comentario = "🟢 Codicia — el mercado está optimista, cuidado con FOMO."
    else:
        comentario = "🔴 Codicia extrema — zona de precaución, posible corrección."
    await update.message.reply_text(
        f"{_emoji_fg(value)} *Fear & Greed Index*\n\n"
        f"`{barra}`\n"
        f"*{value}/100* — {fg['label']}\n\n"
        f"{comentario}",
        parse_mode="Markdown",
    )


async def cmd_noticias(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    noticias = obtener_noticias(5)
    if not noticias:
        await update.message.reply_text("❌ No pude obtener noticias en este momento.")
        return
    lineas = [f"📰 *Noticias Crypto — {noticias[0]['fuente']}*\n"]
    for i, n in enumerate(noticias, 1):
        lineas.append(f"{i}. [{n['titulo']}]({n['link']})")
    await update.message.reply_text(
        "\n".join(lineas), parse_mode="Markdown", disable_web_page_preview=True
    )


async def cmd_precio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "❓ Uso: `/precio BTCUSDT` o `/precio BTCUSDT bybit`", parse_mode="Markdown"
        )
        return
    symbol   = args[0].strip().upper()
    exchange = args[1].strip().lower() if len(args) > 1 else "binance"
    if exchange not in EXCHANGES:
        await update.message.reply_text(
            f"❌ Exchange no soportado: `{exchange}`. Usá: {', '.join(EXCHANGES.keys())}",
            parse_mode="Markdown",
        )
        return
    precio = obtener_precio(symbol, exchange)
    if precio is None:
        await update.message.reply_text(
            f"❌ No encontré `{symbol}` en *{EXCHANGES[exchange]['nombre']}*.",
            parse_mode="Markdown",
        )
        return
    await update.message.reply_text(
        f"💰 *{symbol}* en *{EXCHANGES[exchange]['nombre']}*\nPrecio actual: `{precio:,.8f}`",
        parse_mode="Markdown",
    )


async def cmd_listar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    chat_id = str(update.effective_chat.id)
    activas = obtener_alertas_activas(chat_id)
    if not activas:
        await update.message.reply_text("📭 No tenés alertas activas.")
        return
    lineas = [f"📋 *Alertas activas ({len(activas)}):*\n"]
    _tf_lbl = {"1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W"}
    for a in activas:
        nombre_ex = EXCHANGES.get(a["exchange"], {}).get("nombre", a["exchange"])
        if a["tipo"] == "indicador":
            cond_label = {
                "sobrevendido": "RSI<30", "sobrecomprado": "RSI>70",
                "golden": "GoldenCross", "death": "DeathCross",
            }.get(a.get("condicion_ind", ""), a.get("condicion_ind", ""))
            tf = _tf_lbl.get(a.get("timeframe", ""), a.get("timeframe", ""))
            condicion = f"{a.get('indicador','')} {cond_label} {tf}"
        elif a["tipo"] == "rango":
            r = a.get("rango", (0, 0))
            condicion = f"rango [{r[0]:,.4f} – {r[1]:,.4f}]"
        elif a["tipo"] == "%":
            condicion = f"cambie ≥ {a['porcentaje']}%"
        elif a["tipo"] == ">=":
            condicion = f"suba a ≥ {a['precio']:,.8f}"
        else:
            condicion = f"baje a ≤ {a['precio']:,.8f}"
        rec = " 🔁" if a["recurrente"] else ""
        lineas.append(f"*#{a['id']}* `{a['symbol']}` ({nombre_ex}) → {condicion}{rec}")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def cmd_eliminar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    chat_id = str(update.effective_chat.id)
    if not ctx.args:
        await update.message.reply_text(
            "❓ Uso: `/eliminar <ID>`\nPrimero usá /listar para ver los IDs.",
            parse_mode="Markdown",
        )
        return
    try:
        aid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ El ID debe ser un número.")
        return
    if not alerta_existe(aid, chat_id):
        await update.message.reply_text(f"❌ No existe la alerta #{aid}.")
        return
    desactivar_alerta(aid)
    await update.message.reply_text(f"🗑️ Alerta *#{aid}* eliminada.", parse_mode="Markdown")


# ════════════════════════════════════════════════════════════════
#  CONVERSACIÓN /agregar
# ════════════════════════════════════════════════════════════════

async def cmd_agregar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return ConversationHandler.END
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟡 Binance", callback_data="ex_binance")],
        [InlineKeyboardButton("🟠 Bybit",   callback_data="ex_bybit")],
    ])
    await update.message.reply_text(
        "➕ *Nueva alerta — Paso 1*\n\n¿En qué exchange?\n\n/cancelar para salir.",
        reply_markup=teclado,
        parse_mode="Markdown",
    )
    return EXCHANGE


async def recibir_exchange(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange = query.data.replace("ex_", "")
    ctx.user_data["exchange"] = exchange
    nombre = EXCHANGES[exchange]["nombre"]
    await query.message.reply_text(
        f"✅ *Exchange: {nombre}* — Paso 2\n\n"
        "¿Qué par de trading?\nEjemplos: `BTCUSDT`  `ETHUSDT`  `SOLUSDT`\n\n/cancelar para salir.",
        parse_mode="Markdown",
    )
    return SYMBOL


async def recibir_symbol(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    symbol        = update.message.text.strip().upper().replace(" ", "")
    exchange      = ctx.user_data["exchange"]
    precio_actual = obtener_precio(symbol, exchange)
    if precio_actual is None:
        await update.message.reply_text(
            f"❌ No encontré `{symbol}` en *{EXCHANGES[exchange]['nombre']}*. Verificá el símbolo.",
            parse_mode="Markdown",
        )
        return SYMBOL
    ctx.user_data["symbol"]        = symbol
    ctx.user_data["precio_actual"] = precio_actual
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Alerta de PRECIO",    callback_data="cat_precio")],
        [InlineKeyboardButton("📊 Indicador técnico",   callback_data="cat_indicador")],
    ])
    await update.message.reply_text(
        f"✅ *{symbol}* en *{EXCHANGES[exchange]['nombre']}*\n"
        f"💰 Precio actual: `{precio_actual:,.8f}`\n\n"
        "¿Qué tipo de alerta? — *Paso 3*",
        reply_markup=teclado,
        parse_mode="Markdown",
    )
    return CATEGORIA


async def recibir_categoria(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
    ctx.user_data["categoria"] = cat

    if cat == "precio":
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Sube a precio",  callback_data="cprecio_>=")],
            [InlineKeyboardButton("📉 Baja a precio",  callback_data="cprecio_<=")],
            [InlineKeyboardButton("↔️ Entra en rango", callback_data="cprecio_rango")],
            [InlineKeyboardButton("📊 Cambia X%",      callback_data="cprecio_%")],
        ])
        await query.message.reply_text(
            "💰 *Alerta de precio — Paso 4/6*\n\n¿Qué condición?",
            reply_markup=teclado,
            parse_mode="Markdown",
        )
        return COND_PRECIO
    else:
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 RSI (14)",       callback_data="ind_RSI")],
            [InlineKeyboardButton("📊 EMA 50 / 200",   callback_data="ind_EMA")],
        ])
        await query.message.reply_text(
            "📊 *Indicador técnico — Paso 4/7*\n\n¿Qué indicador?",
            reply_markup=teclado,
            parse_mode="Markdown",
        )
        return IND_TIPO


async def recibir_cond_precio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tipo      = query.data.replace("cprecio_", "")
    ctx.user_data["tipo"] = tipo
    symbol    = ctx.user_data["symbol"]
    precioA   = ctx.user_data["precio_actual"]
    nombre_ex = EXCHANGES[ctx.user_data["exchange"]]["nombre"]
    mensajes = {
        ">=":    f"📈 *Alerta SUBIDA* — `{symbol}` en {nombre_ex}\nPrecio actual: `{precioA:,.8f}`\n\n¿A qué precio? Ejemplo: `95000`",
        "<=":    f"📉 *Alerta BAJADA* — `{symbol}` en {nombre_ex}\nPrecio actual: `{precioA:,.8f}`\n\n¿A qué precio? Ejemplo: `80000`",
        "rango": f"↔️ *Alerta RANGO* — `{symbol}` en {nombre_ex}\nPrecio actual: `{precioA:,.8f}`\n\nDos precios separados por coma. Ejemplo: `85000, 90000`",
        "%":     f"📊 *Alerta PORCENTAJE* — `{symbol}` en {nombre_ex}\nPrecio actual: `{precioA:,.8f}`\n\n¿A qué % de cambio te aviso?\nEjemplo: `5` (avisa si sube o baja 5% desde ahora)",
    }
    await query.message.reply_text(mensajes[tipo] + "\n\n*Paso 5/6*", parse_mode="Markdown")
    return PRECIO_ALERTA


async def recibir_precio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto   = update.message.text.strip()
    tipo    = ctx.user_data["tipo"]
    precioA = ctx.user_data["precio_actual"]

    if tipo == "rango":
        partes = texto.replace(" ", "").split(",")
        if len(partes) != 2:
            await update.message.reply_text("❌ Formato incorrecto. Usá: `85000, 90000`", parse_mode="Markdown")
            return PRECIO_ALERTA
        try:
            p1, p2 = float(partes[0]), float(partes[1])
        except ValueError:
            await update.message.reply_text("❌ Los precios deben ser números.")
            return PRECIO_ALERTA
        if p1 >= p2:
            await update.message.reply_text("❌ El primer precio debe ser menor que el segundo.")
            return PRECIO_ALERTA
        ctx.user_data["precio_obj"] = p1
        ctx.user_data["rango"]      = (p1, p2)
    elif tipo == "%":
        try:
            pct = float(texto.replace(",", ".").replace("%", ""))
            if not (0 < pct <= 100):
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Ingresá un porcentaje válido. Ejemplo: `5`", parse_mode="Markdown")
            return PRECIO_ALERTA
        ctx.user_data["porcentaje"]  = pct
        ctx.user_data["precio_obj"]  = precioA
        ctx.user_data["precio_base"] = precioA
    else:
        try:
            ctx.user_data["precio_obj"] = float(texto.replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ El precio debe ser un número.")
            return PRECIO_ALERTA

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Sí, que se repita", callback_data="rec_si")],
        [InlineKeyboardButton("1️⃣ No, solo una vez",  callback_data="rec_no")],
    ])
    await update.message.reply_text(
        "🔁 *Paso 6/6 — ¿La alerta se repite?*\n\n"
        "• *Sí*: vuelve a activarse tras dispararse (cooldown 30 min)\n"
        "• *No*: se desactiva al cumplirse, una sola vez",
        reply_markup=teclado,
        parse_mode="Markdown",
    )
    return RECURRENTE


async def recibir_ind_tipo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ind = query.data.replace("ind_", "")
    ctx.user_data["indicador"] = ind

    if ind == "RSI":
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("📉 Sobrevendido  (RSI < 30)", callback_data="icond_sobrevendido")],
            [InlineKeyboardButton("📈 Sobrecomprado (RSI > 70)", callback_data="icond_sobrecomprado")],
        ])
    else:
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Golden Cross  (EMA50 cruza arriba EMA200)", callback_data="icond_golden")],
            [InlineKeyboardButton("📉 Death Cross   (EMA50 cruza abajo EMA200)",  callback_data="icond_death")],
        ])
    await query.message.reply_text(
        f"*{ind} — Paso 5/7*\n\n¿Qué condición te interesa?",
        reply_markup=teclado,
        parse_mode="Markdown",
    )
    return IND_CONDICION


async def recibir_ind_condicion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["condicion_ind"] = query.data.replace("icond_", "")
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ 1 hora",    callback_data="itf_1h")],
        [InlineKeyboardButton("⏱ 4 horas",   callback_data="itf_4h")],
        [InlineKeyboardButton("📅 Diario",    callback_data="itf_1d")],
        [InlineKeyboardButton("📅 Semanal",   callback_data="itf_1w")],
    ])
    await query.message.reply_text(
        "⏱ *Temporalidad — Paso 6/7*\n\n¿En qué timeframe?",
        reply_markup=teclado,
        parse_mode="Markdown",
    )
    return IND_TIMEFRAME


async def recibir_ind_timeframe(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["timeframe"] = query.data.replace("itf_", "")
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Sí, que se repita", callback_data="rec_si")],
        [InlineKeyboardButton("1️⃣ No, solo una vez",  callback_data="rec_no")],
    ])
    await query.message.reply_text(
        "🔁 *Paso 7/7 — ¿La alerta se repite?*\n\n"
        "• *Sí*: vuelve a activarse cuando la condición se cumpla de nuevo\n"
        "• *No*: se desactiva al primer disparo",
        reply_markup=teclado,
        parse_mode="Markdown",
    )
    return RECURRENTE


async def recibir_recurrente(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    recurrente = query.data == "rec_si"
    symbol     = ctx.user_data["symbol"]
    exchange   = ctx.user_data["exchange"]
    chat_id    = str(update.effective_chat.id)
    nombre_ex  = EXCHANGES[exchange]["nombre"]
    categoria  = ctx.user_data.get("categoria", "precio")
    rec_txt    = "🔁 Recurrente" if recurrente else "1️⃣ Una sola vez"

    if categoria == "indicador":
        ind      = ctx.user_data["indicador"]
        cond     = ctx.user_data["condicion_ind"]
        tf       = ctx.user_data["timeframe"]
        tf_label = {"1h": "1H", "4h": "4H", "1d": "Diario", "1w": "Semanal"}.get(tf, tf)
        cond_label = {
            "sobrevendido":  "RSI < 30",
            "sobrecomprado": "RSI > 70",
            "golden":        "Golden Cross EMA50/200",
            "death":         "Death Cross EMA50/200",
        }.get(cond, cond)
        aid = insertar_alerta(
            chat_id, symbol, exchange, "indicador",
            recurrente=recurrente, indicador=ind,
            condicion_ind=cond, timeframe=tf,
        )
        condicion = f"📊 {cond_label} — {tf_label}"
    else:
        tipo       = ctx.user_data["tipo"]
        precio_obj = ctx.user_data["precio_obj"]
        if tipo == "rango":
            p1, p2 = ctx.user_data["rango"]
            aid = insertar_alerta(chat_id, symbol, exchange, "rango", p1,
                                  rango_min=p1, rango_max=p2, recurrente=recurrente)
            condicion = f"↔️ Rango: `{p1:,.4f}` — `{p2:,.4f}`"
        elif tipo == "%":
            pct = ctx.user_data["porcentaje"]
            aid = insertar_alerta(chat_id, symbol, exchange, "%", precio_obj,
                                  precio_base=precio_obj, porcentaje=pct, recurrente=recurrente)
            condicion = f"📊 Cambio ≥ `{pct}%` desde `{precio_obj:,.4f}`"
        else:
            aid = insertar_alerta(chat_id, symbol, exchange, tipo, precio_obj,
                                  recurrente=recurrente)
            signo = "≥" if tipo == ">=" else "≤"
            condicion = f"{'📈' if tipo == '>=' else '📉'} Precio {signo} `{precio_obj:,.8f}`"

    await query.message.reply_text(
        f"✅ *Alerta #{aid} creada 💾*\n\n"
        f"🏦 {nombre_ex}\n🪙 `{symbol}`\n{condicion}\n{rec_txt}\n\n"
        "Te avisaré cuando se cumpla la condición. 🔔",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cmd_cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════
#  MONITOR (background)
# ════════════════════════════════════════════════════════════════

async def monitorear_alertas(app: Application):
    ultimo_resumen   = ""
    ultimas_noticias = ""

    while True:
        await asyncio.sleep(10)
        ahora     = datetime.now()
        fecha_hoy = ahora.strftime("%Y-%m-%d")

        if ahora.hour == HORA_RESUMEN and fecha_hoy != ultimo_resumen:
            ultimo_resumen = fecha_hoy
            await _enviar_resumen_diario(app)

        if ahora.hour == HORA_NOTICIAS and fecha_hoy != ultimas_noticias:
            ultimas_noticias = fecha_hoy
            await _enviar_noticias_diarias(app)

        activas    = obtener_alertas_activas()
        disparadas = []

        for alerta in activas:
            aid = alerta["id"]
            ts  = _cooldown.get(aid)
            if ts and (time.time() - ts) < _cooldown_mins(alerta) * 60:
                continue

            tipo   = alerta["tipo"]
            tocada = False
            precio_actual = None

            if tipo == "indicador":
                ind      = alerta.get("indicador")
                cond     = alerta.get("condicion_ind")
                tf       = alerta.get("timeframe", "1h")
                limit    = 260 if ind == "EMA" else 50
                klines   = obtener_klines(alerta["symbol"], alerta["exchange"], tf, limit)
                if not klines or len(klines) < 3:
                    continue
                closes = [k[1] for k in klines]
                if ind == "RSI":
                    rsi = calcular_rsi(closes)
                    if rsi is not None:
                        tocada = (cond == "sobrevendido" and rsi < 30) or \
                                 (cond == "sobrecomprado" and rsi > 70)
                        precio_actual = rsi
                elif ind == "EMA" and len(closes) >= 202:
                    ema50  = _ema_series(closes, 50)
                    ema200 = _ema_series(closes, 200)
                    prev_diff = ema50[-3] - ema200[-3]
                    curr_diff = ema50[-2] - ema200[-2]
                    tocada = (cond == "golden" and prev_diff <= 0 and curr_diff > 0) or \
                             (cond == "death"  and prev_diff >= 0 and curr_diff < 0)
                    precio_actual = closes[-1]
            else:
                precio_actual = obtener_precio(alerta["symbol"], alerta["exchange"])
                if precio_actual is None:
                    continue
                precio = alerta["precio"]
                if tipo == ">=":
                    tocada = precio_actual >= precio
                elif tipo == "<=":
                    tocada = precio_actual <= precio
                elif tipo == "rango" and "rango" in alerta:
                    tocada = alerta["rango"][0] <= precio_actual <= alerta["rango"][1]
                elif tipo == "%":
                    base = alerta.get("precio_base") or precio
                    if base:
                        tocada = abs(precio_actual - base) / base * 100 >= (alerta["porcentaje"] or 0)

            if tocada:
                disparadas.append((aid, alerta, precio_actual))

        _TF_LABEL   = {"1h": "1H", "4h": "4H", "1d": "Diario", "1w": "Semanal"}
        _COND_LABEL = {
            "sobrevendido":  "RSI(14) < 30 — sobrevendido",
            "sobrecomprado": "RSI(14) > 70 — sobrecomprado",
            "golden":        "Golden Cross EMA50/200 — cruce alcista",
            "death":         "Death Cross EMA50/200 — cruce bajista",
        }

        for aid, alerta, precio_actual in disparadas:
            exchange  = alerta["exchange"]
            tipo      = alerta["tipo"]
            nombre_ex = EXCHANGES.get(exchange, {}).get("nombre", exchange)

            if tipo == "indicador":
                tf    = alerta.get("timeframe", "1h")
                cond  = alerta.get("condicion_ind", "")
                ind   = alerta.get("indicador", "")
                val   = f"`{precio_actual:.2f}`" if ind == "RSI" else f"`{precio_actual:,.4f} USDT`"
                desc  = _COND_LABEL.get(cond, cond)
                tf_lbl = _TF_LABEL.get(tf, tf)
                rec_txt = (
                    "🔁 _La alerta seguirá activa (recurrente)._"
                    if alerta["recurrente"]
                    else "_La alerta fue desactivada automáticamente._"
                )
                msg = (
                    f"📊 *¡ALERTA DE INDICADOR!* (ID #{aid})\n\n"
                    f"🏦 *Exchange:* {nombre_ex}\n"
                    f"🪙 *Par:* `{alerta['symbol']}`\n"
                    f"⏱ *Temporalidad:* {tf_lbl}\n"
                    f"📌 *Señal:* {desc}\n"
                    f"📈 *Valor actual:* {val}\n\n"
                    f"📊 [Ver en TradingView]({tv_link(exchange, alerta['symbol'])})\n\n"
                    f"{rec_txt}"
                )
                precio_chart = precio_actual if ind != "RSI" else 0.0
                chart_buf = generar_chart(alerta["symbol"], exchange, precio_chart)
            else:
                if tipo == "rango":
                    r    = alerta["rango"]
                    desc = f"entró al rango [{r[0]:,.4f} – {r[1]:,.4f}]"
                elif tipo == "%":
                    base = alerta.get("precio_base") or alerta["precio"]
                    cambio = (precio_actual - base) / base * 100
                    desc = f"cambió {cambio:+.2f}% (umbral: {alerta['porcentaje']}%)"
                else:
                    desc = f"alcanzó {tipo} {alerta['precio']:,.4f}"

                rec_txt = (
                    "🔁 _La alerta seguirá activa (recurrente)._"
                    if alerta["recurrente"]
                    else "_La alerta fue desactivada automáticamente._"
                )
                msg = (
                    f"🔔 *¡ALERTA DISPARADA!* (ID #{aid})\n\n"
                    f"🏦 *Exchange:* {nombre_ex}\n"
                    f"🪙 *Par:* `{alerta['symbol']}`\n"
                    f"📌 *Condición:* precio {desc}\n"
                    f"💰 *Precio actual:* `{precio_actual:,.8f} USDT`\n\n"
                    f"📊 [Ver en TradingView]({tv_link(exchange, alerta['symbol'])})\n\n"
                    f"{rec_txt}"
                )
                chart_buf = generar_chart(alerta["symbol"], exchange, alerta["precio"])
            try:
                if chart_buf:
                    await app.bot.send_photo(
                        chat_id=alerta["chat_id"], photo=chart_buf,
                        caption=msg, parse_mode="Markdown",
                    )
                else:
                    await app.bot.send_message(
                        chat_id=alerta["chat_id"], text=msg, parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Error enviando alerta #{aid}: {e}")

            if alerta["recurrente"]:
                _cooldown[aid] = time.time()
                if tipo == "%":
                    actualizar_precio_base(aid, precio_actual)
            else:
                desactivar_alerta(aid)


async def _enviar_resumen_diario(app: Application):
    usuarios = [ADMIN_CHAT_ID]
    for chat_id in usuarios:
        simbolos = obtener_simbolos_activos(chat_id)
        if not simbolos:
            continue
        lineas = [f"🌅 *Resumen diario — {datetime.now().strftime('%d/%m/%Y')}*\n"]
        for symbol, exchange in simbolos:
            precio = obtener_precio(symbol, exchange)
            nombre_ex = EXCHANGES.get(exchange, {}).get("nombre", exchange)
            if precio:
                lineas.append(f"🪙 `{symbol}` ({nombre_ex}): `{precio:,.8f}`")
        if len(lineas) > 1:
            try:
                await app.bot.send_message(
                    chat_id=chat_id, text="\n".join(lineas), parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error resumen {chat_id}: {e}")


async def _enviar_noticias_diarias(app: Application):
    noticias = obtener_noticias(5)
    if not noticias:
        return
    lineas = [f"📰 *Noticias Crypto — {noticias[0]['fuente']}*\n"]
    for i, n in enumerate(noticias, 1):
        lineas.append(f"{i}. [{n['titulo']}]({n['link']})")
    texto    = "\n".join(lineas)
    for chat_id in [ADMIN_CHAT_ID]:
        try:
            await app.bot.send_message(
                chat_id=chat_id, text=texto,
                parse_mode="Markdown", disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"Error noticias {chat_id}: {e}")


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        print("ERROR: Faltan variables de entorno TELEGRAM_BOT_TOKEN y/o ADMIN_CHAT_ID")
        return
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("agregar", cmd_agregar)],
        states={
            EXCHANGE:     [CallbackQueryHandler(recibir_exchange,      pattern="^ex_")],
            SYMBOL:       [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_symbol)],
            CATEGORIA:    [CallbackQueryHandler(recibir_categoria,     pattern="^cat_")],
            COND_PRECIO:  [CallbackQueryHandler(recibir_cond_precio,   pattern="^cprecio_")],
            PRECIO_ALERTA:[MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_precio)],
            IND_TIPO:     [CallbackQueryHandler(recibir_ind_tipo,      pattern="^ind_")],
            IND_CONDICION:[CallbackQueryHandler(recibir_ind_condicion, pattern="^icond_")],
            IND_TIMEFRAME:[CallbackQueryHandler(recibir_ind_timeframe, pattern="^itf_")],
            RECURRENTE:   [CallbackQueryHandler(recibir_recurrente,    pattern="^rec_")],
        },
        fallbacks=[CommandHandler("cancelar", cmd_cancelar)],
        allow_reentry=True,
        conversation_timeout=300,
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("listar",    cmd_listar))
    app.add_handler(CommandHandler("eliminar",  cmd_eliminar))
    app.add_handler(CommandHandler("precio",    cmd_precio))
    app.add_handler(CommandHandler("miedo",     cmd_miedo))
    app.add_handler(CommandHandler("noticias",  cmd_noticias))
    app.add_handler(conv)

    async def post_init(application: Application):
        asyncio.create_task(monitorear_alertas(application))

    app.post_init = post_init
    print("🤖 Bot iniciado. Presiona Ctrl+C para detenerlo.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
