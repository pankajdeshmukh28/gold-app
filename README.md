# 🪙 Gold — US vs India

A tiny personal app that answers: *"Should I buy gold at Costco today, or is it cheaper in India?"*

- Fetches **US retail gold bar price** (Costco → APMEX fallback)
- Fetches **international gold spot** + **USD→INR** rate
- Computes **India per-gram price** with **3% GST**
- Publishes a **mobile-friendly dashboard** on GitHub Pages
- Sends a **Telegram notification** when the US price drops

Everything runs on free infrastructure: GitHub Actions runs a cron every 2 hours, writes `docs/data.json`, and GitHub Pages serves the dashboard. No servers, no database, no hosting bills.

---

## Architecture

```
GitHub Actions (cron every 2h)
  └─ scripts/fetch_prices.py
      ├─ fetch USD→INR          (open.er-api.com — free)
      ├─ fetch gold spot USD/oz (goldprice.org — free)
      ├─ fetch US retail        (Costco → APMEX fallback)
      ├─ compute verdict        (US $/g vs India $/g incl. 3% GST)
      ├─ write docs/data.json, docs/history.json
      └─ if drop detected → Telegram message
         │
         ├─ commit back to repo
         │
GitHub Pages (docs/)
  └─ index.html  (mobile-first dashboard, reads data.json via fetch)
```

Accuracy is **directional**, not financial-grade. See [Accuracy caveats](#accuracy-caveats) below.

---

## One-Time Setup (≈ 20 minutes)

### 1. Get a Telegram bot + chat ID (5 min, free)

**Create the bot:**
1. Open Telegram, search for **`@BotFather`**
2. Send `/newbot` and follow the prompts (pick any name + a unique username ending in `bot`)
3. BotFather gives you an **HTTP API token**, e.g. `7234567890:AAHxxx...` — save it.

**Get your chat ID:**
1. Start a chat with your new bot — send it any message (e.g. "hi") so it knows who you are.
2. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser.
3. Find the number in `"chat":{"id": 123456789 ...}` — that's your **chat ID**.

### 2. Push to GitHub

```bash
cd /Users/pankajdeshmukh/workspace/gold-app
git init
git add .
git commit -m "chore: initial scaffold"
# Create a new repo on github.com, then:
git remote add origin git@github.com:<you>/<repo-name>.git
git branch -M main
git push -u origin main
```

### 3. Add GitHub Secrets + Variables

On your new repo, go to **Settings → Secrets and variables → Actions**.

**Add these `Secrets`** (encrypted, never logged):

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the token from BotFather |
| `TELEGRAM_CHAT_ID` | your chat ID |

**Optional `Variables`** (plain, visible, override `scripts/config.py` defaults):

| Name | Default | Notes |
|---|---|---|
| `COSTCO_PRODUCT_URL` | (1-oz PAMP Suisse example) | **Replace with the Costco gold bar URL you actually want to track** |
| `COSTCO_SKU_GRAMS` | `31.1035` | grams in the SKU (31.1035 = 1 troy oz) |
| `APMEX_FALLBACK_URL` | (a 1-oz PAMP Suisse APMEX page) | used when Costco is unavailable |
| `INDIA_GST_RATE` | `0.03` | 3% GST on gold |
| `PRICE_DROP_THRESHOLD_PCT` | `0.5` | notify only if US price drops by ≥ 0.5% |

### 4. Enable GitHub Pages

**Settings → Pages**:
- **Source:** `Deploy from a branch`
- **Branch:** `main` / folder `/docs`
- Save

Your dashboard will be live at `https://<you>.github.io/<repo-name>/` within a minute.

### 5. Kick off the first run

**Settings → Actions → General** — make sure workflows are enabled.

Then **Actions → Fetch gold prices → Run workflow** (manual dispatch). After ~1 minute:
- `docs/data.json` should be populated
- The dashboard URL should show real numbers
- No Telegram message yet (first run — no previous price to compare)

From then on, the cron runs every 2 hours. If the US price drops ≥ 0.5% between runs, you'll get a Telegram message.

---

## Local Development

```bash
cd /Users/pankajdeshmukh/workspace/gold-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: set env vars to test Telegram locally
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."

python -m scripts.fetch_prices
```

Then open `docs/index.html` in a browser (use a simple local server so `fetch()` works):

```bash
cd docs && python3 -m http.server 8080
# visit http://localhost:8080
```

---

## Project Structure

```
gold-app/
├── .github/workflows/fetch-prices.yml  # cron + commit workflow
├── scripts/
│   ├── fetch_prices.py    # entry point
│   ├── config.py          # all tunables (env-driven)
│   ├── notifier.py        # Telegram impl
│   ├── state.py           # last price + history persistence
│   └── sources/
│       ├── fx.py          # USD→INR
│       ├── gold_spot.py   # international spot
│       ├── costco.py      # Costco scraper (primary)
│       └── apmex.py       # APMEX scraper (fallback)
├── docs/                  # GitHub Pages root
│   ├── index.html         # mobile dashboard
│   ├── data.json          # latest reading (written by CI)
│   ├── state.json         # drop-detection state
│   └── history.json       # recent readings for the sparkline
├── requirements.txt
└── README.md
```

---

## Accuracy Caveats

This is a **directional** tool — not a financial calculator. Known approximations:

- **India side** is computed as `spot_usd × USDINR ÷ 31.1035 × (1 + GST)` and displayed per 10g (the Indian market convention used by MCX and jewelers). This tracks the international benchmark + GST, but **does not include** Indian local retail premiums (import duty ~10%, making charges, jeweler margin — can add 5–15% to real retail).
- **10g vs tola**: Modern Indian pricing uses 10 grams as the standard quote unit. The traditional "tola" is ~11.66g and still used for coins. We use 10g to match MCX / news-headline convention. If you want the traditional tola value, multiply the per-gram figures by 11.664.
- **US side** is a retail bar price (Costco or APMEX), which already includes that retailer's premium over spot.
- So the reported "% cheaper" leans toward **understating** how much cheaper the US really is vs. *Indian retail jewelry*, but is roughly right vs. *Indian digital gold / ETFs / coins*.
- **FX rate** is mid-market (no forex spread). Your actual money conversion may cost 0.5–2% more.
- **3% GST** is a simplification of India's current gold GST (3% on jewelry, some categories differ).

For personal "is it a good deal today?" signaling, this is fine. For real financial decisions, cross-check with your bank and a jeweler.

---

## Tuning

Most things are tunable without code changes:

| Tune | How |
|---|---|
| Track a different Costco SKU | Set `COSTCO_PRODUCT_URL` + `COSTCO_SKU_GRAMS` in GH Actions variables |
| Change cron cadence | Edit `.github/workflows/fetch-prices.yml`, line `cron: "17 */2 * * *"` (currently every 2h, offset by 17 min) |
| Quieter notifications | Raise `PRICE_DROP_THRESHOLD_PCT` (e.g. `1.0` for ≥1% drops only) |
| Different GST | Set `INDIA_GST_RATE` (e.g. `0.05`) |
| Swap notifier channel | Subclass `Notifier` in `scripts/notifier.py`, return your impl from `get_default_notifier()` |

---

## Troubleshooting

**Dashboard shows "Could not load data.json"**  
First run hasn't happened yet, or Pages hasn't picked up the latest commit. Wait 1–2 min after a successful Actions run.

**Banner says "Fell back to APMEX"**  
Costco returned a login wall or the scraper couldn't find the price. APMEX is serving as your US price — still directional-accurate. If you want to force back to Costco, see [Fixing Costco scraping](#fixing-costco-scraping).

**No Telegram messages arriving**  
Check:
1. Bot token and chat ID are set as GH Secrets (not Variables).
2. You sent the bot at least one message from your account (bots can't DM users who haven't initiated).
3. `PRICE_DROP_THRESHOLD_PCT` isn't too high — try lowering to `0.1` temporarily to force a test notification.
4. Run the workflow manually; in the Actions log, look for `[notify] sent drop alert` vs `[notify] skipped`.

**Actions job fails on "git push"**  
Settings → Actions → General → Workflow permissions → set to **Read and write permissions**.

### Fixing Costco scraping

Costco often gates precious-metal pricing behind a member login. If you want *exact* Costco numbers, you'd need to:

1. Log into costco.com in a real browser.
2. Export your session cookie (`costco.com` cookies — specifically `C_LOC`, `sessionId`, etc.).
3. Add them as a GH secret like `COSTCO_COOKIE` and pass into `requests.get(..., cookies={...})` in `scripts/sources/costco.py`.
4. Re-export every ~30 days when the session expires.

This is intentionally *not* built in — fragile and moderate effort. The APMEX fallback is the pragmatic path.

---

## Cost

| Item | Cost |
|---|---|
| GitHub Actions | Free (2000 min/month on private repos; this uses ~5 min/month) |
| GitHub Pages | Free |
| Telegram bot | Free |
| APIs (er-api, goldprice) | Free, no key |
| **Total** | **$0/month** |

---

Built directionally, shipped fast.
