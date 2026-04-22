# Gold App — Build Progress

> **Living document.** Update after every substantive change. First point of reference when resuming work or updating context.

**Last updated:** 2026-04-21
**Owner:** Pankaj
**Status:** 🟢 Code is ship-ready — end-to-end smoke test PASSED locally. Only manual GitHub/Telegram setup steps remain (user actions).

---

## 1. What This App Does (1-paragraph)

A personal, directional tool that answers **"Should I buy gold at Costco today, or is it cheaper in India?"** Runs entirely on free infrastructure: a Python script executed by GitHub Actions every 2 hours fetches a US retail 1-oz gold bar price + international gold spot + USD→INR FX, computes the per-gram delta (with 3% India GST), writes `docs/data.json`, and sends a Telegram message if the US price dropped since last run. A mobile-first static dashboard served by GitHub Pages reads `data.json` and renders the verdict.

---

## 2. Scope Decisions & Pivots (chronological)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Scope pivoted from "diaspora product" → "solo tool, directional accuracy, ship-ASAP"** | User clarified n=1 audience mid-brainstorm. Dropped Role Playing, deep risk analysis, feature backlog polish. |
| 2 | **Notification channel: Telegram bot (not SMS)** | User initially wanted SMS for security; after security comparison (Telegram is technically *more* secure for this payload — TLS vs plaintext SMS, no PII transmitted), user picked Telegram for zero-cost + faster setup. `Notifier` abstraction in `scripts/notifier.py` makes future SMS swap a 10-line change. |
| 3 | **Hosting: GitHub Pages + GitHub Actions cron** | Zero servers, zero cost, auto-built history via git commits. User wanted phone-accessible dashboard; GH Pages + mobile-first HTML + "Add to Home Screen" achieves this without native app cost. |
| 4 | **US price strategy: Costco primary → JM Bullion fallback → spot×premium estimate** | Option [1] chosen by user. Tested: **Costco is blocked by Akamai Bot Manager (unsolvable without real browser)** — we detect this and fall through cleanly. APMEX also blocks (TLS) but `curl_cffi` works; however APMEX category URL returned antique coins, so pivoted to JM Bullion which renders real product cards server-side. Spot×premium estimate is the absolute last-resort so the app *never* goes dark. |
| 5 | **India price: derived, not scraped** | Formula: `spot_usd_per_oz × USD_INR ÷ 31.1035 × (1 + GST)`. User said "use any standard gold index" — since XAUINR is essentially this math anyway, computing it directly removes a scraping dependency and is exactly "directional". GST rate is configurable (default 3%). |
| 6 | **Privacy: obscured public URL (no auth)** | Solo user, no secrets in the UI. Just use an unguessable repo name. |

---

## 3. Architecture

```
┌────────────────────────────────────────────────────────────┐
│ GitHub Actions (cron "17 */2 * * *" — every 2h, offset 17m)│
│  1. Install deps                                            │
│  2. Run `python -m scripts.fetch_prices`                    │
│  3. If docs/{data,state,history}.json changed → commit+push │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ scripts/fetch_prices.py   (orchestrator)                    │
│  a. fx.py             → USD→INR (open.er-api.com free)      │
│  b. gold_spot.py      → XAU/USD/oz (goldprice.org → gold-api)│
│  c. US price fallback chain:                                │
│       costco.py       → tries Costco (blocked by Akamai)    │
│       jmbullion.py    → scrapes 1-oz bar category           │
│       us_retail_estimate.py → spot × (1 + premium)          │
│  d. compute_verdict() → US_$/g vs India_$/g (incl. GST)     │
│  e. state.py          → load prev US price, detect drop     │
│  f. notifier.py       → Telegram msg if drop ≥ threshold    │
│  g. writes docs/data.json + docs/history.json + state.json  │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ GitHub Pages (source: /docs)                                │
│  docs/index.html — mobile-first, no deps, dark theme        │
│    · fetches data.json + history.json                        │
│    · shows: verdict card, US $/g + India $/g, sparkline,    │
│      raw inputs, timestamp, source link                      │
│    · auto-refreshes every 60s                                │
└────────────────────────────────────────────────────────────┘
                         │
                         ▼
   URL: https://<user>.github.io/<repo>/  → Add to Home Screen
```

---

## 4. Tech Decisions

| Concern | Choice | Notes |
|---|---|---|
| HTTP client | **curl_cffi** (chrome124 impersonation) | Plain `requests` gets 403 from Akamai/Cloudflare. curl_cffi matches real Chrome TLS/JA3 fingerprint. Essential for scraping retail gold sites. |
| HTML parse | beautifulsoup4 | |
| Gold spot API | goldprice.org primary, gold-api.com fallback | Free, no auth, no key |
| FX API | open.er-api.com primary, frankfurter.app fallback | Free, no auth, no key |
| India GST | Configurable `INDIA_GST_RATE`, default 0.03 | 3% per user spec |
| Notifier | Telegram HTML-formatted messages | Abstracted via `Notifier` base class |
| State | Flat JSON files in `docs/` | No DB. Git commits = history. |
| CI | GitHub Actions, cron 2h, manual dispatch | `GITHUB_TOKEN` has write perms to push data |
| UI | Single `index.html` + vanilla JS, dark theme, mobile-first, no build step | Tailwind-style classes inline for portability |

---

## 5. File Layout

```
gold-app/
├── .github/workflows/fetch-prices.yml    ✅ cron + commit workflow
├── scripts/
│   ├── fetch_prices.py                   ✅ main orchestrator
│   ├── config.py                         ✅ env-driven config
│   ├── notifier.py                       ✅ Telegram impl
│   ├── state.py                          ✅ state + history
│   └── sources/
│       ├── fx.py                         ✅ USD→INR
│       ├── gold_spot.py                  ✅ international spot (curl_cffi)
│       ├── costco.py                     ✅ primary (detects Akamai)
│       ├── jmbullion.py                  ✅ fallback retailer scraper
│       └── us_retail_estimate.py         ✅ last-resort spot × premium
├── docs/                                 ← GitHub Pages root
│   ├── index.html                        ✅ mobile dashboard
│   ├── data.json                         ✅ placeholder (CI overwrites)
│   ├── state.json                        (created at runtime)
│   └── history.json                      ✅ placeholder []
├── requirements.txt                      ✅ requests, bs4, curl_cffi
├── .gitignore                            ✅
├── README.md                             ✅ full setup instructions
└── _bmad-output/
    ├── brainstorming/
    │   └── brainstorming-session-2026-04-21-1329.md  ✅ BMAD session artifact
    └── implementation-artifacts/
        └── PROGRESS.md                   ← you are here
```

---

## 6. Build Status

| # | Task | Status |
|---|---|---|
| 1 | Project skeleton + requirements + .gitignore | ✅ |
| 2 | FX module | ✅ (smoke tested — USD→INR = 93.60) |
| 3 | Gold spot module | ✅ (primary 403, fallback works — $4,756/oz) |
| 4 | Costco scraper w/ Akamai detection | ✅ (correctly detects bot block) |
| 5 | JM Bullion fallback scraper | ✅ (rewritten — replaces APMEX; finds real product cards) |
| 6 | US retail estimate (spot × premium) | ✅ |
| 7 | State + history manager | ✅ |
| 8 | Telegram notifier | ✅ (needs live test with real token) |
| 9 | `fetch_prices.py` orchestrator | ✅ |
| 10 | Mobile dashboard `index.html` | ✅ |
| 11 | GitHub Actions workflow | ✅ |
| 12 | README with manual-steps checklist | ✅ |
| 13 | **Full end-to-end smoke test** | ✅ PASSED — produced `US $156.62/g vs India $157.61/g, -0.63% (BUY_IN_US)` with real 2026-04-21 prices |
| 14 | **Git init + first push** | ⏳ pending — user action |
| 15 | **Telegram bot creation + chat ID** | ⏳ pending — user action |
| 16 | **GitHub repo + Secrets + Variables + Pages enablement** | ⏳ pending — user action |
| 17 | **First manual-dispatch workflow run** | ⏳ pending — user action |

### Smoke test output (2026-04-22 03:14 UTC)

```
[main] USD→INR = 93.6058
[gold_spot] primary source failed: HTTP Error 403
[main] spot gold = $4759.50/oz
[us_price] Costco bot-blocked (Akamai). Falling back to JM Bullion.
[main] US price = $4871.32 via jmbullion
[main] DONE. US is 0.63% cheaper than India
```

Verifies: FX source ✅ | gold spot fallback chain ✅ | Costco Akamai detection ✅ | JM Bullion scraping ✅ | verdict math ✅ | data.json written ✅ | first-run alert-suppression ✅ (no prev price).

---

## 7. Known Issues & Workarounds

### 7.1 Costco is behind Akamai Bot Manager

- Pure HTTP scrapers (including curl_cffi) get served a JS challenge page, not the product HTML.
- **Workaround in code:** `costco.py` detects the `sec-if-cpt-container` / akamai markers and raises `CostcoBotBlocked`, orchestrator falls through to JM Bullion.
- **"Real" fix (not implemented, documented in README):** use Playwright + stored Costco session cookie (~1–2 hr work, cookie re-export every ~30 days). Deferred — JM Bullion is directionally close.

### 7.2 goldprice.org primary returns 403

- Known and handled — `gold_spot.py` falls through to `gold-api.com` automatically. Not blocking.

### 7.3 Python 3.9 annotations compat — RESOLVED

- Replaced `list[str]` with `List[str]` from `typing`. Code now runs cleanly in both Python 3.9 (local dev) and 3.11 (GH Actions).

### 7.4 JM Bullion scraper fragility

- Scrapes HTML card structure for prices. If JM Bullion redesigns the category page, `_extract_candidates()` in `scripts/sources/jmbullion.py` may break.
- Mitigation: spot-based estimate (`us_retail_estimate.py`) is the final fallback, so the app degrades to directional accuracy rather than going dark.
- Revisit signal: if `source` in `data.json` flips to `"estimate"` for several consecutive runs.

---

## 8. Pre-Ship Manual Steps (User)

Full detail in `README.md` §1–5. Summary checklist:

- [ ] Create Telegram bot via `@BotFather`, save `TELEGRAM_BOT_TOKEN`
- [ ] Send bot any message, visit `https://api.telegram.org/bot<TOKEN>/getUpdates`, save `TELEGRAM_CHAT_ID`
- [ ] `git init` repo, push to GitHub (private or public)
- [ ] Repo Settings → Secrets: add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- [ ] Repo Settings → Variables: **(optional)** override `COSTCO_PRODUCT_URL`, etc.
- [ ] Repo Settings → Actions → General → Workflow permissions → **Read and write** (required for auto-commit)
- [ ] Repo Settings → Pages → Source: `Deploy from branch` `main` folder `/docs`
- [ ] Actions tab → "Fetch gold prices" → Run workflow (first run populates `data.json`)
- [ ] Open dashboard URL, confirm verdict renders, add to Home Screen on phone

---

## 9. Deferred / Future Work

| Item | Why deferred | Trigger to revisit |
|---|---|---|
| Actual Costco scraping (Playwright + cookie) | Akamai bypass requires browser automation + stored cookie refresh | If JM Bullion price drifts too far from real Costco or user specifically wants Costco accuracy |
| Multi-SKU tracking | Solo use, one question = one answer | If Pankaj buys different sizes regularly |
| Email/SMS notifier | Telegram works, cost-conscious | If Telegram reliability drops or user wants redundancy |
| Indian retail premium modeling (import duty, making charges, jeweler margin — adds 5–15%) | Spec said "3% GST" only; not trying to model full retail | If real-world arbitrage experience shows the signal is misleading |
| Threshold configurability in UI | Config-as-code is fine for solo use | If this is ever shared with another user |
| Auth / private URL | Personal info absent; public URL with obscurity is fine | If app ever includes personal holdings/portfolio data |

---

## 10. How to Resume This Work

Read this file first, then:

1. Check §6 **Build Status** for `⏳` rows — those are next steps.
2. Check §7 **Known Issues** for context on anything mysterious.
3. If data-source scraping breaks: read `scripts/sources/<failing>.py`, note that all scrapers use `curl_cffi` with `impersonate="chrome124"`. Adjust the extractor selectors/regex. Always test locally before pushing.
4. If user wants a new retail source added: follow the `jmbullion.py` pattern — return `(price_usd, source_url)` tuple, insert into fallback chain in `fetch_prices.fetch_us_price()`.
5. If user wants a new notifier: subclass `Notifier` in `scripts/notifier.py`, return it from `get_default_notifier()`.

**Always update this file when:**
- Scope changes
- New tech decision is made
- Build task completes or stalls
- New known issue surfaces
- Architecture shifts
