"""My Festival REST API — M10 starter (CSC Rahti).

FI: Tämä on M10-tehtävän lähtöpohja. GET /api/artists on valmiina mallina;
    toteuta loput TODO-kohdat. Aja paikallisesti:  python app.py
    ja testaa:  python test_endpoints.py http://localhost:8080
EN: This is the M10 starter. GET /api/artists is done as an example;
    implement the remaining TODOs. Run locally:  python app.py
    and test:  python test_endpoints.py http://localhost:8080
"""
import os
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, request

app = Flask(__name__)

# FI: Kanta kulkee kontin mukana. Polun voi vaihtaa ympäristömuuttujalla.
# EN: The database ships inside the container. Override the path with an env var.
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "myfestival.db"))


DEFAULT_DURATION_MIN = 45


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # M8: sqlite3 ei valvo FK:ita oletuksena / FKs are off by default
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
def health():
    """FI: Rahti ja selain näkevät, että sovellus on pystyssä.
    EN: Lets Rahti and your browser see the app is up."""
    return jsonify(status="ok", endpoints=["/api/artists", "/api/days", "/api/stages",
                                           "/api/artists/<id>/events", "/api/timetable?day=YYYY-MM-DD",
                                           "POST /api/events", "DELETE /api/events/<id>"])


@app.get("/api/artists")
def get_artists():
    conn = get_db()
    rows = conn.execute("SELECT artist_id, name, country FROM Artist ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/days")
def get_days():
    """FI: Apuendpoint: festivaalipäivät (tarkistin hakee tästä day_id:n).
    EN: Helper endpoint: festival days (the checker reads day_id from here)."""
    conn = get_db()
    rows = conn.execute("SELECT day_id, date FROM Day ORDER BY date").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/stages")
def get_stages():
    """FI: Apuendpoint: lavat. EN: Helper endpoint: stages."""
    conn = get_db()
    rows = conn.execute("SELECT stage_id, name FROM Stage ORDER BY stage_id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/artists/<int:artist_id>/events")
def get_artist_events(artist_id):
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM Artist WHERE artist_id = ?", (artist_id,)).fetchone() is None:
            return jsonify(error="artist not found"), 404
        rows = conn.execute(
            """SELECT e.event_id, d.date AS day, s.name AS stage, e.start_dt AS starts
               FROM Event e
               JOIN Day d   ON d.day_id = e.day_id
               JOIN Stage s ON s.stage_id = e.stage_id
               WHERE e.artist_id = ?
               ORDER BY e.start_dt""",
            (artist_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/timetable")
def get_timetable():
    day = request.args.get("day")
    sql = """SELECT d.date AS date, s.name AS stage, a.name AS artist,
                    time(e.start_dt) AS starts, time(e.end_dt) AS ends
             FROM Event e
             JOIN Day d    ON d.day_id = e.day_id
             JOIN Stage s  ON s.stage_id = e.stage_id
             JOIN Artist a ON a.artist_id = e.artist_id"""
    params = ()
    if day is not None:
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return jsonify(error="day must be in format YYYY-MM-DD"), 400
        sql += " WHERE d.date = ?"
        params = (day,)
    sql += " ORDER BY e.start_dt, s.stage_id"
    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.post("/api/events")
def create_event():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="request body must be a JSON object"), 400

    missing = [f for f in ("artist_id", "stage_id", "day_id", "start_dt")
               if body.get(f) in (None, "")]
    if missing:
        return jsonify(error="missing field(s): " + ", ".join(missing)), 400

    for f in ("artist_id", "stage_id", "day_id"):
        # bool on int-aliasi Pythonissa, joten hylätään se erikseen
        if not isinstance(body[f], int) or isinstance(body[f], bool):
            return jsonify(error=f"{f} must be an integer"), 400

    try:
        datetime.strptime(str(body["start_dt"]), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return jsonify(error="start_dt must be in format YYYY-MM-DD HH:MM:SS"), 400

    conn = get_db()
    try:
        try:
            cur = conn.execute(
                """INSERT INTO Event (event_type_id, day_id, stage_id, artist_id,
                                      start_dt, end_dt, duration_min)
                   VALUES ((SELECT event_type_id FROM EventType WHERE code = 'performance'),
                           ?, ?, ?, ?, datetime(?, '+' || ? || ' minutes'), ?)""",
                (body["day_id"], body["stage_id"], body["artist_id"],
                 body["start_dt"], body["start_dt"], DEFAULT_DURATION_MIN, DEFAULT_DURATION_MIN),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            return jsonify(error=f"invalid data (unknown artist/stage/day or time slot already taken): {e}"), 400
        row = conn.execute(
            """SELECT event_id, event_type_id, day_id, stage_id, artist_id,
                      start_dt, end_dt, duration_min
               FROM Event WHERE event_id = ?""",
            (cur.lastrowid,),
        ).fetchone()
        return jsonify(dict(row)), 201
    finally:
        conn.close()


@app.delete("/api/events/<int:event_id>")
def delete_event(event_id):
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM Event WHERE event_id = ?", (event_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(error="event not found"), 404
        return "", 204
    finally:
        conn.close()


if __name__ == "__main__":
    # FI: Paikallinen kehityspalvelin. Rahdissa sovellusta ajaa gunicorn (ks. Dockerfile).
    # EN: Local dev server. On Rahti the app is run by gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
