# 🤖 Bot de Alertas Crypto

Bot de Telegram gratuito que monitorea precios de criptomonedas 
en Binance y Bybit en tiempo real.

**Creado por Emanuel Arano | IA & Trading**  
📺 [youtube.com/@EmanuelAranoIATrading](https://youtube.com/@EmanuelAranoIATrading)

---

## ¿Qué hace?

- 🔔 Alertas de precio: sube, baja, rango o cambio porcentual
- 📊 Alertas de indicadores: RSI, Golden Cross y Death Cross
- 📈 Gráfico automático al dispararse cada alerta
- 🌅 Resumen diario de precios a las 9:00 AM
- 📰 Noticias crypto en español a las 8:00 AM
- 🔒 Sistema de whitelist con aprobación desde Telegram

## Instalación

```bash
pip install python-telegram-bot requests feedparser matplotlib
python3 crypto_alertas.py
```

## Archivos

- `crypto_alertas.py` — Código del bot
- `bot_crypto_guia.pdf` — Guía completa de instalación y uso

## Configuración

Necesitas dos variables de entorno:

```bash
export TELEGRAM_BOT_TOKEN="tu_token_aqui"
export ADMIN_CHAT_ID="tu_chat_id_aqui"
```

---
⚠️ Este bot es una herramienta de monitoreo, no de inversión.
