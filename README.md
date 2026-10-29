# Vietnam Money Flow – private team dashboard

Two working Streamlit pages: **Stock Screener** and **Sector Rotation**, with OIDC login and email allowlist. Intended for 5–15 users. This package is **not hosted or scheduled** and does **not** contain Finwise credentials.

## Quick start (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Set FINWISE_API_KEY via a secure environment/secret manager (not in Git).
$env:FINWISE_API_KEY = 'YOUR_FINWISE_REST_KEY'
python pipeline.py
streamlit run app.py
```

## Authentication (required; no anonymous mode)

Streamlit built-in OIDC login uses a provider such as Google. Register an OAuth web client with redirect `https://YOUR-APP-DOMAIN/oauth2callback` (for local testing `http://localhost:8501/oauth2callback`, subject to provider rules). Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, configure client ID, client secret, cookie secret and **allowed_emails**. Email allowlist is checked server-side after OIDC login; a user with a valid Google account but not on the allowlist is denied. OIDC is authentication only; restrict admin emails separately. Do not commit secrets. Configure the same secrets in hosting provider secret manager. Protect data files and database at infrastructure level too.

## Finwise data

The included `pipeline.py` uses Finwise REST `/v1/bars` and `universe.csv` with `ticker,sector,exchange`. The universe file contains **four pilot tickers**, not 1,592. Replace with a validated, licensed, full-universe reference export; the Finwise Pro tool rejected a 1,592-stock query because its group cap was 600. Split discovery by sector/exchange, and fetch bars in rate-limited batches. The local pipeline is sequential and will take time at full scale. Confirm the Finwise REST key, rate limits, price adjustment policy, license for team sharing, and sector taxonomy before production.

The pipeline currently excludes current-day candles (`date < today`), so a run after close will show the **previous trading session**. For a guaranteed same-day settled refresh, implement provider final-bar status verification; do not just remove the condition blindly. Run it next morning for a stable prior-session dashboard.

The pipeline's current `adv20_vnd` is based on `close * volume` as a **proxy**, not exchange-reported traded turnover. It uses raw price/volume (`adjustments=none`) by default; splits/rights can distort historical indicators. Verify before investment use.

## Team deployment

Host Streamlit on a private app host, with HTTPS, OIDC, a persistent disk or managed PostgreSQL for outputs, and a separate scheduled Python worker. On Streamlit Community Cloud, a local output directory is **not** durable shared storage and scheduled ingestion cannot be assumed. For a 5–15 user team, a small VPS or managed app + managed database is more reliable. The included version uses CSV outputs; PostgreSQL is an **upgrade path, not implemented**. Scheduled refresh is **not configured** by this package. Deploy only after licensing and credential checks.

## Data quality and risk

Flow Score is preliminary and does not include VNIndex-relative strength; VSA signals are heuristics; no backtest has been performed. Historical sector membership, corporate actions and missing bars require further validation. Screen and sector ranking honor the same exchange/industry/liquidity filters. An email allowlist is not a substitute for licensing rights to redistribute market data.
