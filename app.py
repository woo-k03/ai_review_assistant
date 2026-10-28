# Flask web app: PDF upload, background reviews, and review history (no login).
# Run with: py app.py   (demo mode with no Ollama: $env:DEMO_MODE="1"; py app.py)
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from flask import Flask, g, jsonify, render_template, request
from pypdf import PdfReader

from reviewer import review_proposal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "reviews.db"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Database table for reviews
SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    solicitation_name TEXT,
    proposal_name TEXT,
    status TEXT NOT NULL,            -- running | done | error
    overall INTEGER,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
"""


# Open a new database connection
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


# One database connection per request
def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


# Close the request's connection when it ends
@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Create the table, and mark reviews left "running" by a restart as failed
def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "UPDATE reviews SET status='error', error='Interrupted by a server restart.', "
            "finished_at=? WHERE status='running'", (now(),))


# Current time as a UTC text timestamp
def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Main page (the whole app lives here)
@app.route("/")
def index():
    return render_template("index.html")


# Pull plain text out of an uploaded PDF or .txt file
def extract_text(file_storage) -> str:
    name = file_storage.filename or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "pdf":
        try:
            reader = PdfReader(file_storage.stream)
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            raise ValueError(f"Couldn't open {name}. Is it a valid PDF?")
    elif ext in ("txt", "md"):
        text = file_storage.read().decode("utf-8", errors="replace")
    else:
        raise ValueError(f"{name}: only PDF or .txt files are supported.")
    text = text.strip()
    if len(text) < 50:
        raise ValueError(f"{name} has almost no readable text (scanned PDF?).")
    return text


# Turn a database row into a JSON-friendly dict
def row_to_dict(row, with_result=False):
    d = {
        "id": row["id"],
        "title": row["title"],
        "solicitation_name": row["solicitation_name"],
        "proposal_name": row["proposal_name"],
        "status": row["status"],
        "overall": row["overall"],
        "error": row["error"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
    }
    if with_result:
        d["result"] = json.loads(row["result_json"]) if row["result_json"] else None
    return d


# Background job: run the model and save the result (or the error)
def run_review(review_id, solicitation, proposal):
    conn = connect()
    try:
        result = review_proposal(solicitation, proposal)
        conn.execute(
            "UPDATE reviews SET status='done', overall=?, result_json=?, finished_at=? WHERE id=?",
            (result["overall"], json.dumps(result), now(), review_id))
    except Exception as exc:
        conn.execute(
            "UPDATE reviews SET status='error', error=?, finished_at=? WHERE id=?",
            (f"{type(exc).__name__}: {exc}"[:500], now(), review_id))
    finally:
        conn.commit()
        conn.close()


# Start a new review from two uploaded files
@app.route("/api/reviews", methods=["POST"])
def create_review():
    sol_file = request.files.get("solicitation")
    prop_file = request.files.get("proposal")
    if not sol_file or not sol_file.filename or not prop_file or not prop_file.filename:
        return jsonify(error="Attach both the solicitation and the proposal."), 400
    try:
        solicitation = extract_text(sol_file)
        proposal = extract_text(prop_file)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    title = request.form.get("title", "").strip() or os.path.splitext(prop_file.filename)[0]
    db = get_db()
    cur = db.execute(
        "INSERT INTO reviews (title, solicitation_name, proposal_name, status, created_at) "
        "VALUES (?,?,?, 'running', ?)",
        (title[:200], sol_file.filename, prop_file.filename, now()))
    db.commit()
    review_id = cur.lastrowid
    threading.Thread(target=run_review, args=(review_id, solicitation, proposal), daemon=True).start()
    return jsonify(id=review_id), 202


# List past reviews, newest first
@app.route("/api/reviews", methods=["GET"])
def list_reviews():
    rows = get_db().execute("SELECT * FROM reviews ORDER BY id DESC LIMIT 200").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


# Get one review with its full result
@app.route("/api/reviews/<int:review_id>", methods=["GET"])
def get_review(review_id):
    row = get_db().execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    if not row:
        return jsonify(error="Not found."), 404
    return jsonify(row_to_dict(row, with_result=True))


# Delete one review
@app.route("/api/reviews/<int:review_id>", methods=["DELETE"])
def delete_review(review_id):
    db = get_db()
    cur = db.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Not found."), 404
    return jsonify(ok=True)


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)