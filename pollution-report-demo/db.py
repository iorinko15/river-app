"""SQLite storage for pollution reports - the single `reports` table from the concept doc."""
from __future__ import annotations

import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reports.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

FLAG_HIDE_THRESHOLD = 3  # flag_count at which a report is auto-marked "flagged"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            photo_path TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            category TEXT NOT NULL,
            confidence REAL NOT NULL,
            description TEXT,
            severity TEXT NOT NULL,
            note TEXT,
            submitted_at TEXT NOT NULL,
            reporter_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            flag_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def insert_report(r: dict) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO reports
            (id, photo_path, latitude, longitude, category, confidence,
             description, severity, note, submitted_at, reporter_id, status, flag_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            r["id"], r["photo_path"], r["latitude"], r["longitude"], r["category"],
            r["confidence"], r.get("description", ""), r["severity"], r.get("note", ""),
            r["submitted_at"], r.get("reporter_id"), r.get("status", "active"),
            r.get("flag_count", 0),
        ),
    )
    conn.commit()
    conn.close()


def list_reports(category: str | None = None, since: str | None = None) -> list[dict]:
    conn = get_conn()
    query = "SELECT * FROM reports WHERE status != 'removed'"
    params: list = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if since:
        query += " AND date(submitted_at) >= date(?)"
        params.append(since)
    query += " ORDER BY submitted_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_reports() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"]
    conn.close()
    return n


def increment_flag(report_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE reports SET flag_count = flag_count + 1 WHERE id = ?", (report_id,))
    row = conn.execute("SELECT flag_count FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row and row["flag_count"] >= FLAG_HIDE_THRESHOLD:
        conn.execute("UPDATE reports SET status = 'flagged' WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()


# --- Demo seed data -------------------------------------------------------
# So the map/feed isn't empty on first run. Placeholder images are generated
# locally (no external assets) and clearly labelled as demo photos.

_SEED_SAMPLES = [
    ("Litter / plastic waste", "low",
     "Scattered plastic bottles and food wrappers along a footpath.", (196, 178, 60)),
    ("Oil or chemical spill", "high",
     "Rainbow-coloured sheen visible on the water surface near a drain outlet.", (45, 45, 55)),
    ("Air pollution (smoke, visible emissions)", "medium",
     "Dark smoke rising steadily from an industrial stack.", (110, 110, 118)),
    ("Illegal dumping (bulky waste, construction debris)", "medium",
     "Pile of construction rubble and an old mattress dumped by the roadside.", (150, 96, 46)),
    ("Sewage / wastewater", "high",
     "Grey wastewater discharging directly into a stream.", (86, 108, 92)),
]

_DEMO_CENTER = (51.399, -3.612)  # arbitrary coastal demo location


def seed_demo_data_if_empty() -> None:
    if count_reports() > 0:
        return
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    for i, (category, severity, description, color) in enumerate(_SEED_SAMPLES):
        filename = f"seed_{uuid.uuid4()}.jpg"
        _make_placeholder_image(os.path.join(UPLOAD_DIR, filename), category, color)
        insert_report(
            {
                "id": str(uuid.uuid4()),
                "photo_path": f"uploads/{filename}",
                "latitude": _DEMO_CENTER[0] + random.uniform(-0.01, 0.01),
                "longitude": _DEMO_CENTER[1] + random.uniform(-0.01, 0.01),
                "category": category,
                "confidence": round(random.uniform(0.75, 0.97), 2),
                "description": description,
                "severity": severity,
                "note": "",
                "submitted_at": (now - timedelta(days=i * 2, hours=i)).isoformat(),
                "reporter_id": "demo-seed",
                "status": "active",
                "flag_count": 0,
            }
        )


def _make_placeholder_image(path: str, label: str, color: tuple) -> None:
    img = Image.new("RGB", (640, 480), color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.multiline_text((20, 20), f"DEMO PHOTO\n{label}", fill=(255, 255, 255), font=font)
    img.save(path, "JPEG", quality=80)
