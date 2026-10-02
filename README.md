# Pollution Reporter — Phase 1 demo

A runnable Flask demo of the concept in *Pollution Reporting App — Plan & Structure*: photo in →
AI classifies it → report saved to a shared database → visible to everyone on a public map/feed.
This covers Phase 1 end-to-end, plus a few cheap Phase 2 slices (real GPS/pin location capture,
category + date filtering, and a "flag as inaccurate" button).

## What's implemented

- **Upload flow** — photo (camera or file picker), GPS or click-to-pin location, optional note.
- **AI classification** — the photo is sent to Claude with a forced tool call, so it must return
  one of the fixed categories plus `confidence`, `description`, `severity` as structured data
  (never free-text prose that would need re-parsing).
- **Confidence handling** — at/above the threshold (default 0.6) the report saves immediately;
  below it (or category `Other / unclear`), the reporter is shown a confirm screen to pick the
  category themselves before it's saved — matching the flowchart's "low confidence → manual pick"
  branch.
- **Shared database** — one SQLite `reports` table (`db.py`), matching the field list in the
  concept doc (photo path, lat/lon, category, confidence, description, severity, status,
  flag_count, etc.), plus a `note` field for the optional reporter note from the user flow.
- **Public map/feed** (`/`) — Leaflet map + card list, filterable by category and date, with a
  flag button that auto-marks a report `flagged` after 3 flags.
- **Offline-friendly demo** — if no Claude credentials are configured, the app falls back to a
  mock classifier so the whole flow still works without any setup. The app also seeds 5 sample
  reports (with generated placeholder photos) on first run so the map isn't empty.

## Not implemented (explicitly out of scope for this demo)

Per the roadmap in the concept doc, these are Phase 2/3 items intentionally left out:
hotspot clustering of duplicate reports, stats dashboards, accounts/submission history, and
automatic face/plate blurring. The moderation note about deciding whether to round public GPS
coordinates is also left as a follow-up decision, not implemented here.

## Setup

```bash
cd pollution-report-demo
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Enable real AI classification (optional)

Without this, the app still runs — it just uses the mock classifier and says so in the report
description.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

(Or run `ant auth login` if you use the Anthropic CLI — the app picks up that credential too.)

### Run

```bash
python app.py
```

Open `http://localhost:5050` on your computer, or `http://<your-lan-ip>:5050` on your phone (same
Wi-Fi) to test the camera capture and GPS location flow for real.

## AI classification details

- Model: `claude-haiku-4-5` (cheapest current vision-capable model — set `CLASSIFIER_MODEL` env
  var to override, e.g. for a more capable model on trickier photos).
- The photo is resized to max 1280px and re-encoded as JPEG *before* being sent, both to save
  upload/storage space and to keep the API call cheap and fast.
- Structured output is enforced with a forced tool call (`tool_choice`), not by asking the model
  to "return JSON" in prose — this is what keeps thousands of reports consistently categorized.

**Approximate cost per report:** a ~1280×960 compressed photo is roughly 1,600–1,800 image
tokens, plus a short prompt. At Haiku 4.5 pricing ($1.00 / $5.00 per 1M input/output tokens),
one classification call costs on the order of **$0.002–0.003** — i.e. roughly $2–3 per 1,000
reports. Cheap enough for a class project, but worth knowing before opening submissions up
publicly without any rate limiting.

## Project layout

```
app.py          Flask routes: upload, AI-classify, confirm-low-confidence, map/feed, flag
classifier.py   Claude API call + fixed category list + mock fallback
db.py           SQLite schema, queries, demo seed data
templates/      Jinja templates (map/feed, upload form, low-confidence confirm screen)
static/         CSS + uploaded/seeded photos
```
