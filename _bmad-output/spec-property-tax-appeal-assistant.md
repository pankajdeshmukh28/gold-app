# Spec: Property tax appeal filing assistant (low-liability MVP)

_Date discussed: 2026-04-26_  
_Owner:_ Pankaj  
_Context:_ Brainstorm-derived product idea distilled into a standalone project spec suitable for scaffolding a **new repo** (separate from `gold-app`).

---

## Goal

Ship a **set-up-once personal/family ops assistant** that:

- Answers common questions about the **annual** property assessment appeal process.
- Helps **gather and organize evidence** into a repeatable “packet”.
- Generates **documentation + procedural checklists** to help the homeowner **file online** safely.
- Sends **minimal, high-stakes Telegram reminders** around the filing window.

**Explicit non-goals (V1):**

- Automated portal submission (“click submit”) without explicit human involvement.
- Representing outcomes (“you will save $X”; “your assessment is definitely wrong”).
- Handling **supplemental / escape assessments** unless added later.

---

## Jurisdiction anchor (California / Alameda County)

**Regular assessment appeal filing window (typical/stable):**

- Window opens **July 2**
- Deadline **September 15**
- Valuation lien date (**evidence anchored to**) **January 1**

Official references to keep in-repo as “sources of truth links”:

- Alameda County Assessor — homeowners calendar important dates (`https://www.acassessor.org/homeowners/calendar-important-dates/`)
- FAQ section on appeals (`https://www.acassessor.org/frequently-asked-questions/`)

**Operational note:** even with stable county dates, reminders should instruct users to **verify on official pages** yearly.

---

## Product principles

1. **Low liability:** education + organization, not advocacy or representation.
2. **Quiet-by-default:** a few pings per season, not noisy daily automation.
3. **Human-in-the-loop filing:** checklist-driven online filing; optional local automation only if deliberately chosen later.
4. **Reusable architecture:** intentionally similar to existing “cron + state + Telegram + static dashboard” pattern proven in `gold-app`.

---

## Liability & trust posture (MVP wording + behavior rules)

### Positioning statements (mandatory boilerplate)

- Not legal advice, not tax advice, not appraisal advice.
- Not affiliated with the county/state unless explicitly true.
- User responsible for correctness of numbers, filings, deadlines, uploads.

### Behavioral rules (“safe modes”)

- Don’t promise savings or likelihood of success.
- Don’t assert legal conclusions (“you qualify”, “illegal assessment”).
- Separate **facts sourced from county pages** from **templates/suggestions**.
- Prefer “here are common docs people include” vs “you must prove X”.
- Anything generated as narrative is **draft** and must be editable.

Recommended UX pattern:

- Separate channels: **(A) Official excerpts + links**, **(B) User-editable drafts**.

---

## User journeys

### Journey A — “Season mode” reminders (annual)

Milestones for Alameda annual appeals (timezone: PT):

| Milestone ID | Typical date | Intent |
|---|---|---|
| `EVIDENCE_START` | ~ Jun 1 | Start packet gathering; collect comps & condition docs |
| `WINDOW_OPEN` | Jul 2 | Confirm packet ready; begin online filing checklist |
| `DEADLINE_NUDGE_MID` | ~ Sep 1 | Mid-window push if not marked filed |
| `DEADLINE_URGENT` | ~ Sep 12 | Final push before deadline |

Post-season (optional): log outcome once known.

### Journey B — Packet builder (“documentation prep”)

User provides:

- Property basics (nickname, APN optional, county)
- Assessor notice snapshot (manual upload screenshot/PDF preferred)
- 3–6 comparable sale links OR manual CSV entries
- Optional condition narrative + photo list

System outputs artifacts (committed locally or exported zip):

- `FILING_CHECKLIST.md` — step-by-step online filing checklist
- `EVIDENCE_CHECKLIST.md` — what-to-gather checklist
- `COMP_SALES_TEMPLATE.csv` — structured comps table
- `COVER_LETTER_DRAFT.md` — editable draft (no outcome promises)
- `PACKET_SUMMARY.md` — 1-page summary for uploads

---

## Architecture (recommended for new repo)

### Components

1. **`processor` cron workflow (GitHub Actions)**
   - Reads `appeal/state.json`
   - If today hits a milestone and not suppressed, broadcasts Telegram reminders to subscribers/admin
   - Idempotent reminders via `last_sent_milestone_*` counters

2. **`bot-poller` workflow (Telegram)**
   - `/start`, `/stop`, `/help`
   - `/status` shows next milestones + verified links section
   - `/done filed` acknowledges completion for the season
   - `/snooze 7d` optional safety valve
   - Admin commands similar to household ops patterns (optional V2)

3. **Static dashboard (GitHub Pages)**
   - Renders markdown county pack + disclaimers prominently
   - Provides downloadable templates (or links to artifacts)

### Data files (minimal)

Suggested layout:

```
docs/
  county-packs/US-CA-ALAMEDA/
    FACTS.md            # citations + excerpts policy (link-first)
    FAQ.md              # curated Q&A framed as informational
    DISCLAIMER.md       # short + readable
public/
appeal-state.json       # milestones + acknowledgement flags
subs.json deny.json     # subscriber model (optional reuse of gold-app pattern)
```

Keep secrets out of git; store tokens in GH Actions secrets only.

---

## MVP feature list (shipping order)

### V0 (fastest usefulness)

- Alameda FACTS doc with official links + “verify yearly” checklist
- Season reminders (Jun 1, Jul 2, Sep 1, Sep 12)
- Telegram `/status`

### V1 (high leverage)

- Packet builder CLI or small wizard script:
  - composes markdown artifacts + optional PDF export step (defer PDF if needed)

### V2 (optional)

- Multi-property profiles
- Sibling coordination (roles + escalation)
- Outcome tracking (optional privacy controls)

---

## Branding decisions (explicit)

- Emoji marker should avoid ambiguous coin imagery if used in Telegram; prefer a neutral visual identity.

---

## Open questions before repo creation

1. Confirmation of the **preferred online filing entry URL** user will anchor to (stored in FACTS/FILING checklist).
2. Whether packet artifacts live:
   - in-repo (`docs/generated/…`) vs
   - user-local exports only (`out/`) for privacy reasons

---

## Next steps checklist (engineering)

1. Create new repo (separate from `gold-app`).
2. Copy infra pattern: Actions cron + telegram broadcast + GH Pages.
3. Author `DISCLAIMER.md` + `FAQ.md` + county pack for Alameda.
4. Implement idempotent reminders + acknowledgement flags.
5. Dogfood season 2026; iterate once after first real filing UX.
