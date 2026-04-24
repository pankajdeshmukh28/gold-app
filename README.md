# 🟡 Gold — US vs India

A tiny personal app that answers: *"Should I buy gold at Costco today, or is it cheaper in India?"*

- Fetches **US retail gold bar price** (Costco → APMEX fallback)
- Fetches **international gold spot** + **USD→INR** rate
- Computes **India per-gram price** with **3% GST**
- Publishes a **mobile-friendly dashboard** on GitHub Pages
- Sends a **Telegram notification** when the US-vs-India savings grow (i.e. a better moment to buy)
- Sends a **weekly Telegram digest** every Sunday 9am PT — low / high / avg savings for the week
- Supports **multi-user subscriptions** — anyone can `/start` the bot to self-subscribe; admin controls (`/list`, `/kick`, `/block`, `/broadcast`) for moderation

Everything runs on free infrastructure: GitHub Actions runs a cron every 2 hours (plus a separate Sunday digest), writes `docs/data.json`, and GitHub Pages serves the dashboard. No servers, no database, no hosting bills.

---

## Architecture

```
GitHub Actions (cron every 2h)
  └─ scripts/fetch_prices.py
      ├─ fetch USD→INR          (open.er-api.com — free)
      ├─ fetch gold spot USD/oz (goldprice.org — free)
      ├─ fetch US retail        (Costco → APMEX fallback)
      ├─ fetch IBJA 999 rate    (benchmark used by Indian jewelers; fallback: spot × FX)
      ├─ compute verdict        (US all-in $/g vs India IBJA + 3% GST)
      ├─ write docs/data.json, docs/history.json
      └─ if drop detected → Telegram message
         │
         ├─ commit back to repo
         │
GitHub Pages (docs/)
  └─ index.html  (mobile-first dashboard, reads data.json via fetch)

GitHub Actions (Sunday 16:00 UTC — once weekly)
  └─ scripts/weekly_digest.py
      ├─ read docs/history.json (past 7 days)
      ├─ compute low / high / avg / trend-vs-last-Sunday (all in ₹/10g)
      └─ broadcast formatted "weekly pulse" to all subscribers

GitHub Actions (every 5 min — subscriber self-service)
  └─ scripts/telegram_bot.py
      ├─ getUpdates (polls Telegram for new messages)
      ├─ route /start /stop /help /status (public)
      ├─ route /list /kick /block /unblock /stats /broadcast (admin-only)
      └─ commit docs/subscribers.json + docs/deny_list.json
```

**Broadcast fan-out:** both the price-alert cron and the weekly digest use `BroadcastNotifier`, which iterates over subscribers + admin chat ID(s), respects Telegram's 30 msgs/sec rate limit, retries on `429`, and auto-prunes any chat that has blocked the bot.

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
| `SAVINGS_INCREASE_THRESHOLD_INR` | `500` | notify only if the buying-in-US savings grew by ≥ ₹500/10g since last run |

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

From then on, the cron runs every 2 hours. If the **buying-in-US savings** increase by ≥ ₹500/10g between runs (i.e. the US-over-India gap widened in your favour), you'll get a Telegram message. Direction matters — we stay quiet when the gap shrinks or when US gets more expensive, since those aren't "go buy now" signals.

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

## Sharing the bot (family & friends subscribe flow)

The bot is self-service. Anyone with the link can subscribe themselves — no tech setup, no chat-ID copy-paste.

### Invite flow (what you share)

Just send them a link to your bot:

```
https://t.me/<your-bot-username>
```

(Your bot's username is whatever you set up in BotFather, e.g. `t.me/GoldPulseBot`. It's case-insensitive.)

**What they experience:**
1. Tap the link → Telegram opens a chat with your bot.
2. They see a big blue **START** button (plus the bot's description text).
3. Tap START → within ~5 minutes they receive a welcome message confirming they're subscribed.
4. They're in. They'll get the same price alerts + weekly Sunday digest as you.

That's it — no copy/paste, no technical steps. You can share the link over iMessage / WhatsApp / email.

### Bot description (set once in BotFather)

Before sharing, set the bot's "About" and "Description" in BotFather (`/mybots` → your bot → `Edit Bot`). Suggested text:

```
Gold price alerts from <your name>. Pings you when Costco gold is saving you
meaningfully more INR/10g than India, plus a Sunday weekly pulse. Tap START
to subscribe. Confirms within a few minutes.
```

This text shows up **before** they tap START, so it manages expectations.

### Admin commands (you only)

Chat with your own bot and use these commands. Your chat ID (set in `TELEGRAM_CHAT_ID` secret) is the admin by default; add more via the `ADMIN_CHAT_IDS` GH Actions variable (comma-separated).

| Command | What it does |
|---|---|
| `/list` | List all subscribers (first name, @handle, join date, chat_id) |
| `/stats` | Totals: subscribers, new this week, blocked, admins |
| `/kick <chat_id>` or `/kick @username` | Remove a subscriber (they can re-subscribe) |
| `/block <chat_id>` or `/block @username` | Remove + add to deny-list (cannot re-subscribe) |
| `/unblock <chat_id>` | Lift a block |
| `/broadcast <message>` | Send a one-off message to all subscribers (e.g. "bot will be down tomorrow") |

### Subscriber commands (anyone)

| Command | What it does |
|---|---|
| `/start` | Subscribe |
| `/stop` | Unsubscribe |
| `/status` | Show the current savings snapshot |
| `/help` | Show help text |

### Safety rails

- **Subscriber cap** — `MAX_SUBSCRIBERS` (default 1000) prevents runaway growth if the bot link ever gets shared more broadly than intended. Raise/lower via GH Actions variable.
- **Deny list** — `/block` permanently prevents a chat from re-subscribing. Persisted in `docs/deny_list.json`.
- **Group-chat protection** — if someone adds the bot to a group, it replies with a polite "1:1 only" note and ignores commands.
- **Admin-only guard** — non-admins sending admin commands get a silent "unauthorized" reply; no info leaks about who the admin is.
- **Auto-prune** — if a subscriber blocks the bot, the next broadcast detects the `403 Forbidden` response and automatically removes them.

### Subscription latency

The bot polls Telegram every 5 min. So a new subscriber waits up to ~5 min between tapping START and receiving their welcome message. The BotFather description text sets this expectation upfront so they don't think the bot is broken.

---

## Optional: Real Costco pricing (local Mac + Playwright)

Costco is protected by Akamai Bot Manager, which blocks GitHub Actions IPs reliably. To get **actual Costco** prices (instead of the JM Bullion fallback), run a lightweight Playwright fetcher locally on your Mac via `launchd`. Your residential IP + a real Chromium instance beats Akamai consistently.

This is **purely additive** — the main cron workflow still drives the dashboard verdict and Telegram alerts. The Costco card appears on the dashboard only when `docs/costco.json` exists and is fresh (< 24h).

### One-time setup

```bash
cd /Users/pankajdeshmukh/workspace/gold-app

# Install Playwright + chromium (adds ~200MB to the repo's venv, not the repo itself)
.venv/bin/pip install -r requirements-local.txt
.venv/bin/playwright install chromium

# Verify it actually works before scheduling
.venv/bin/python -m scripts.fetch_costco_pw
# On success you'll see: [costco-pw] OK $XXXX.XX (...) -> docs/costco.json

# Install the launchd agent (runs once per day at 09:15 local; on first load too)
bash launchd/install.sh
```

### Monitor

```bash
tail -f logs/costco.out.log    # normal output
tail -f logs/costco.err.log    # errors (also shows if Akamai blocked)
launchctl list | grep gold     # verify the agent is loaded
```

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.gold-app.costco.plist
rm ~/Library/LaunchAgents/com.gold-app.costco.plist
```

### If Playwright gets blocked

Run once with a visible browser to solve any CAPTCHA manually — Akamai usually calms down after seeing a real human click:

```bash
COSTCO_PW_HEADFUL=true .venv/bin/python -m scripts.fetch_costco_pw
```

The cookies set during that session persist in Chromium's default profile and subsequent headless runs inherit the good reputation score.

---

## Project Structure

```
gold-app/
├── .github/workflows/
│   ├── fetch-prices.yml     # main cron (every 2h) + commit data + broadcast alerts
│   ├── weekly-digest.yml    # Sunday 9am PT weekly digest broadcast
│   └── bot-poller.yml       # every 5 min — handles /start /stop /admin commands
├── scripts/
│   ├── fetch_prices.py      # main cron entry point
│   ├── weekly_digest.py     # weekly Telegram digest entry point
│   ├── telegram_bot.py      # command processor (subscribe/unsubscribe/admin)
│   ├── fetch_costco_pw.py   # local-only Costco Playwright fetcher
│   ├── run_costco_local.sh  # launchd wrapper (pull, fetch, commit, push)
│   ├── config.py            # all tunables (env-driven)
│   ├── notifier.py          # Telegram impl (single + broadcast fan-out)
│   ├── state.py             # last price + history + subscribers persistence
│   └── sources/
│       ├── fx.py              # USD→INR
│       ├── gold_spot.py       # international spot
│       ├── costco.py          # Costco scraper (curl_cffi; usually bot-blocked in CI)
│       ├── jmbullion.py       # JM Bullion scraper (CI-reliable fallback)
│       └── us_retail_estimate.py  # spot × premium (final fallback)
├── launchd/
│   ├── com.gold-app.costco.plist.template  # macOS launchd agent
│   └── install.sh                          # renders + loads the agent
├── docs/                    # GitHub Pages root
│   ├── index.html           # mobile dashboard
│   ├── data.json            # main verdict (written by CI)
│   ├── costco.json          # optional, written by local Costco fetcher
│   ├── state.json           # drop-detection state + bot update offset
│   ├── history.json         # recent readings for the sparkline
│   ├── subscribers.json     # subscriber list (managed by telegram_bot.py)
│   └── deny_list.json       # blocked chat IDs (managed by telegram_bot.py)
├── requirements.txt         # CI deps
├── requirements-local.txt   # CI deps + Playwright (for local only)
└── README.md
```

---

## Accuracy Caveats

This is a **directional** tool — not a financial calculator. Known approximations:

- **India side** is the **IBJA 999 benchmark rate** (per 10g, published twice daily at [ibjarates.com](https://ibjarates.com/)) × `(1 + 3% GST)`. IBJA is the reference rate Indian jewelers and banks actually use — so it **already reflects** India's import duty (~10%) and local market premium. This is the price you'd pay buying gold *in India*, not the price of importing international gold into India.
- **Why not `spot + GST`?** That formula underestimates real Indian retail by ~10–20% because it ignores local market dynamics. We fall back to it only if IBJA is unreachable (and surface a warning in the UI when we do).
- **10g vs tola**: Modern Indian pricing uses 10 grams as the standard quote unit. The traditional "tola" is ~11.66g and still used for coins. We use 10g to match MCX / news-headline convention. If you want the traditional tola value, multiply the per-gram figures by 11.664.
- **US side** is a retail bar price (Costco or JM Bullion), which already includes that retailer's premium over spot.
- **FX rate** is mid-market (no forex spread). Your actual money conversion may cost 0.5–2% more.
- **3% GST** is a simplification of India's current gold GST (3% on bars/coins; jewelry also has making-charge GST layered on top — we don't model jewelry).
- **IBJA session**: we prefer the PM (closing) rate when available, fall back to AM.

For personal "is it a good deal today?" signaling, this is fine. For real financial decisions, cross-check with your bank and a jeweler.

---

## Tuning

Most things are tunable without code changes:

| Tune | How |
|---|---|
| Track a different Costco SKU | Set `COSTCO_PRODUCT_URL` + `COSTCO_SKU_GRAMS` in GH Actions variables |
| Change cron cadence | Edit `.github/workflows/fetch-prices.yml`, line `cron: "17 */2 * * *"` (currently every 2h, offset by 17 min) |
| Quieter notifications | Raise `SAVINGS_INCREASE_THRESHOLD_INR` (e.g. `1000` for ≥₹1,000/10g improvements only) |
| Louder notifications | Lower `SAVINGS_INCREASE_THRESHOLD_INR` (e.g. `250` — you'll get pinged more often) |
| Different GST | Set `INDIA_GST_RATE` (e.g. `0.05`) |
| Weekly digest day/time | Edit `.github/workflows/weekly-digest.yml`, line `cron: "0 16 * * 0"` (currently Sun 16:00 UTC = Sun 9am PT) |
| Preview the digest without sending | Run the **Weekly gold digest** workflow manually (GitHub → Actions → Run workflow) with `dry_run: true` — message is printed to the job logs |
| Subscriber cap | `MAX_SUBSCRIBERS` GH Actions variable (default 1000, set to 0 to disable) |
| Extra admins | `ADMIN_CHAT_IDS` GH Actions variable, comma-separated chat IDs — e.g. `123,456` |
| Bot poll frequency | Edit `.github/workflows/bot-poller.yml`, line `cron: "*/5 * * * *"` |
| Rate-limit pacing | `BROADCAST_SLEEP_SEC` (default 0.05s between sends) |
| Swap notifier channel | Subclass `Notifier` in `scripts/notifier.py`, return your impl from `get_default_notifier()` / `get_broadcast_notifier()` |

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
3. `SAVINGS_INCREASE_THRESHOLD_INR` isn't too high — try lowering to `1` temporarily (or trigger the workflow manually with `test_notify=true` to verify wiring without waiting for a market move).
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
