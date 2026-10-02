"""Pollution Reporting App - Phase 1 demo.

Photo in -> AI classifies it -> saved to a shared SQLite database ->
visible to everyone on a public map/feed. See README.md for setup.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, flash, redirect, render_template, request, session, url_for
from PIL import Image, UnidentifiedImageError

import classifier
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DEFAULT_MAP_CENTER = {"lat": 51.399, "lng": -3.612}  # arbitrary demo default; anywhere works

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

db.init_db()
db.seed_demo_data_if_empty()


@app.after_request
def ensure_reporter_cookie(response):
    """Anonymous per-device id, used only to tag a reporter's own submissions."""
    if not request.cookies.get("reporter_id"):
        response.set_cookie(
            "reporter_id", str(uuid.uuid4()), max_age=60 * 60 * 24 * 365, samesite="Lax"
        )
    return response


@app.route("/")
def index():
    category_filter = request.args.get("category") or None
    since = request.args.get("since") or None
    reports = db.list_reports(category=category_filter, since=since)
    return render_template(
        "index.html",
        reports=reports,
        reports_json=json.dumps(reports),
        categories=classifier.CATEGORIES,
        selected_category=category_filter,
        since=since or "",
        map_center=DEFAULT_MAP_CENTER,
        total_count=db.count_reports(),
    )


@app.route("/report/new", methods=["GET", "POST"])
def new_report():
    if request.method == "GET":
        return render_template(
            "upload.html", categories=classifier.CATEGORIES, map_center=DEFAULT_MAP_CENTER
        )

    photo = request.files.get("photo")
    if not photo or photo.filename == "":
        flash("Please choose or take a photo.", "error")
        return redirect(url_for("new_report"))

    lat_raw = request.form.get("latitude")
    lng_raw = request.form.get("longitude")
    if not lat_raw or not lng_raw:
        flash("Location is required — allow location access or drop a pin on the map.", "error")
        return redirect(url_for("new_report"))
    try:
        lat, lng = float(lat_raw), float(lng_raw)
    except ValueError:
        flash("That location wasn't valid — try again.", "error")
        return redirect(url_for("new_report"))

    note = (request.form.get("note") or "").strip()[:500]

    filename = f"{uuid.uuid4()}.jpg"
    save_path = os.path.join(UPLOAD_DIR, filename)
    try:
        img = Image.open(photo.stream)
        img = img.convert("RGB")
        img.thumbnail((1280, 1280))  # compress before storage
        img.save(save_path, "JPEG", quality=80, optimize=True)
    except UnidentifiedImageError:
        flash("That file didn't look like an image — try a different photo.", "error")
        return redirect(url_for("new_report"))

    result = classifier.classify_photo(save_path)

    pending = {
        "photo_path": f"uploads/{filename}",
        "latitude": lat,
        "longitude": lng,
        "note": note,
        **result,
    }

    confident_enough = (
        result["confidence"] >= classifier.CONFIDENCE_THRESHOLD
        and result["category"] != "Other / unclear"
    )
    if confident_enough:
        _save_report(pending)
        flash(f'Report saved — classified as "{result["category"]}".', "success")
        return redirect(url_for("index"))

    session["pending_report"] = pending
    flash("The AI wasn't fully confident — please confirm the category below.", "warning")
    return redirect(url_for("confirm_report"))


@app.route("/report/confirm", methods=["GET", "POST"])
def confirm_report():
    pending = session.get("pending_report")
    if not pending:
        return redirect(url_for("new_report"))

    if request.method == "POST":
        category = request.form.get("category")
        if category not in classifier.CATEGORIES:
            flash("Please choose a valid category.", "error")
            return redirect(url_for("confirm_report"))
        pending["category"] = category
        pending["confidence"] = 1.0  # human-confirmed
        _save_report(pending)
        session.pop("pending_report", None)
        flash("Report saved with your confirmed category.", "success")
        return redirect(url_for("index"))

    return render_template("confirm.html", pending=pending, categories=classifier.CATEGORIES)


@app.route("/report/<report_id>/flag", methods=["POST"])
def flag_report(report_id):
    db.increment_flag(report_id)
    flash("Thanks — this report has been flagged for review.", "success")
    return redirect(request.referrer or url_for("index"))


def _save_report(data: dict) -> None:
    reporter_id = request.cookies.get("reporter_id") or str(uuid.uuid4())
    db.insert_report(
        {
            "id": str(uuid.uuid4()),
            "photo_path": data["photo_path"],
            "latitude": data["latitude"],
            "longitude": data["longitude"],
            "category": data["category"],
            "confidence": data["confidence"],
            "description": data.get("description", ""),
            "severity": data.get("severity", "medium"),
            "note": data.get("note", ""),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "reporter_id": reporter_id,
            "status": "active",
            "flag_count": 0,
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
