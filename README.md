# 🤖 Bot de Alertas Crypto

Bot de Telegram gratuito y open source para uso personal que monitorea
precios de criptomonedas en **Binance** y **Bybit** en tiempo real.

**Creado por Emanuel Arano | IA & Trading**  
📺 [youtube.com/@EmanuelAranoIATrading](https://youtube.com/@EmanuelAranoIATrading)

---

## ¿Qué hace?

- 🔔 Alertas de precio: sube, baja, rango o cambio porcentual
- 📊 Alertas de indicadores: RSI, Golden Cross y Death Cross
- 📈 Gráfico automático al dispararse cada alerta
- 🌅 Resumen diario de precios a las 9:00 AM
- 📰 Noticias crypto en español a las 8:00 AM
- 😨 Índice Fear and Greed del mercado

---

## Instalación

### 1. Instalar librerías

```bash
pip install python-telegram-bot requests feedparser matplotlib
```

### 2. Crear tu bot en Telegram

- Abre Telegram y busca **@BotFather**
- Mándale `/newbot` y sigue las instrucciones
- Copia el **TOKEN** que te da

### 3. Obtener tu Chat ID

- Busca en Telegram el bot **@userinfobot**
- Mándale `/start`
- Copia el número que te responde, ese es tu **ADMIN_CHAT_ID**

### 4. Configurar el archivo

Abre `crypto_alertas.py` y reemplaza los valores:

```python
TELEGRAM_BOT_TOKEN = "tu_token_aqui"
ADMIN_CHAT_ID      = "tu_chat_id_aqui"
```

### 5. Ejecutar

```bash
python3 crypto_alertas.py
```

---

## Comandos disponibles

| Comando | Descripción |
|---|---|
| `/agregar` | Crear una nueva alerta de precio o indicador |
| `/listar` | Ver todas tus alertas activas |
| `/eliminar <ID>` | Eliminar una alerta por su ID |
| `/precio BTCUSDT` | Consultar el precio actual de cualquier par |
| `/miedo` | Ver el índice Fear and Greed del mercado |
| `/noticias` | Ver las últimas noticias crypto en español |
| `/cancelar` | Cancelar la operación actual |

---

## Tipos de alerta

| Tipo | Cuándo se dispara |
|---|---|
| Sube a precio | Cuando el precio llega o supera un valor definido |
| Baja a precio | Cuando el precio cae hasta un valor definido |
| Entra en rango | Cuando el precio entra entre dos valores |
| Cambia X% | Cuando el precio sube o baja más de X% desde ahora |
| RSI sobrevendido | RSI(14) cae por debajo de 30 — posible rebote |
| RSI sobrecomprado | RSI(14) supera 70 — posible corrección |
| Golden Cross | EMA50 cruza hacia arriba a EMA200 — señal alcista |
| Death Cross | EMA50 cruza hacia abajo a EMA200 — señal bajista |

---

## Timeframes para indicadores

- `1H` — 1 hora, para trading activo
- `4H` — 4 horas, para swing trading corto plazo
- `1D` — Diario, para swing trading mediano plazo
- `1W` — Semanal, para análisis de tendencia general

---

## Archivos

- `crypto_alertas.py` — Código del bot
- `bot_crypto_guia.pdf` — Guía completa de instalación y uso

---

## Consejos

- Si el bot no responde manda `/cancelar` y vuelve a intentarlo
- Para correr el bot 24/7 usa un servidor en la nube como DigitalOcean ($4/mes)
- Puedes tener múltiples alertas activas al mismo tiempo

---

⚠️ **Aviso:** Este bot es una herramienta de monitoreo, no de inversión.
La decisión de operar siempre es tuya y bajo tu propia responsabilidad.
