# Bot de señales (Binance → Telegram)

Lee velas públicas de Binance cada 15 min, aplica la estrategia elegida y manda la señal a Telegram con entrada, SL y TP. **No opera solo:** la orden la pones tú.

## Instalación (una sola vez)

### 1. Bot de Telegram (gratis)
1. En Telegram, abre **@BotFather** → `/newbot` → ponle un nombre. Copia el **token**.
2. Abre tu bot nuevo y mándale cualquier mensaje (por ejemplo "hola").
3. En el navegador, abre `https://api.telegram.org/bot<TOKEN>/getUpdates` y busca `"chat":{"id":123456789`. Ese número es tu **chat_id**.

### 2. Repositorio en GitHub
1. Crea un repositorio nuevo **público**: con 15 min de intervalo, uno privado pasa el límite gratis de minutos. El token no queda expuesto, porque va en *Secrets*.
2. Sube todo el contenido de esta carpeta, incluida la carpeta oculta `.github`.
3. *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_TOKEN` = el token
   - `TELEGRAM_CHAT_ID` = el chat_id
4. *Settings → Actions → General → Workflow permissions* → **Read and write**.

### 3. Probar
- *Actions → Señales → Run workflow* → marca **prueba** → te llega "✅ Bot de señales conectado".
- Desde ahí corre solo cada 15 min.

## Backtest
*Actions → Backtest → Run workflow*. El resultado sale en el resumen de la ejecución, y los CSV quedan en *Artifacts*.

Columnas clave:
- `R_promedio` > 0: la estrategia gana a largo plazo, ya con costos.
- `R_prom_ultimo_30%`: el resultado solo en la parte más reciente. Si se mantiene positivo, es más confiable.
- `trades`: con menos de ~100, no es concluyente.
- `caida_max_R`: la peor racha, medida en pérdidas de 1R.

## Cambiar la estrategia
Edita `config.json`:
```json
{"name": "donchian", "tf": "1h", "symbols": ["XRPUSDT", "DOGEUSDT"]}
```
Estrategias disponibles: `ema_pullback`, `donchian`, `rsi2`, `supertrend`, `macd` (ver `bot/strategies.py`).

## Notas
- Los datos son de **Spot**; el precio del perpetuo difiere muy poco.
- GitHub puede atrasar las ejecuciones programadas varios minutos. Si la señal llega tarde, el mensaje lo avisa.
- GitHub desactiva los cron de repos sin actividad en 60 días. Los commits de `state.json` cuentan como actividad.
