"""SmartCity Connect - Flask API + static frontend. Postgres (Supabase) for data and photos."""
import os, time, hmac, secrets, logging
import psycopg2, psycopg2.extras
from flask import Flask, request, jsonify, send_from_directory, Response, redirect
from itsdangerous import URLSafeTimedSerializer, BadSignature

DB_URL = os.environ.get("DATABASE_URL")
SECRET = os.environ.get("SECRET_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not (DB_URL and SECRET and ADMIN_PASSWORD):
    raise RuntimeError("Missing environment variables: DATABASE_URL, SECRET_KEY, ADMIN_PASSWORD")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
signer = URLSafeTimedSerializer(SECRET, salt="smartcity-admin")
log = logging.getLogger("smartcity")

CATS = ["Pothole", "Garbage", "Broken streetlight", "Water leakage", "Drainage problem", "Other"]
STATUSES = ["Pending", "In Progress", "Resolved"]
ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PUB = ("id,category,description,round(lat::numeric,4)::float8 AS lat,round(lng::numeric,4)::float8 AS lng,"
       "status,admin_note,(photo IS NOT NULL) AS has_photo,created_at,updated_at")
ADM = ("id,category,description,lat,lng,address,status,admin_note,reporter_name,reporter_contact,"
       "(photo IS NOT NULL) AS has_photo,created_at,updated_at")


def run(sql, args=(), fetch=None):
    conn = psycopg2.connect(DB_URL, connect_timeout=10)
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            if fetch == "all":
                return cur.fetchall()
            if fetch == "one":
                return cur.fetchone()
    finally:
        conn.close()


def clean(r):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}


def init_db():
    run("""CREATE TABLE IF NOT EXISTS reports(
        id text PRIMARY KEY, category text NOT NULL, description text NOT NULL,
        lat double precision NOT NULL, lng double precision NOT NULL, address text,
        status text NOT NULL DEFAULT 'Pending', admin_note text,
        reporter_name text, reporter_contact text, photo bytea, photo_type text,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
    run("CREATE INDEX IF NOT EXISTS reports_created_idx ON reports(created_at DESC)")


try:
    init_db()
except Exception:
    log.exception("Database init failed - check DATABASE_URL")


@app.before_request
def force_https():
    if request.headers.get("X-Forwarded-Proto", "https") == "http":
        return redirect(request.url.replace("http://", "https://", 1), 301)


@app.after_request
def headers(r):
    r.headers["Strict-Transport-Security"] = "max-age=31536000"
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Permissions-Policy"] = "geolocation=(self)"
    r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return r


def err(msg, code=400):
    return jsonify(error=msg), code


@app.errorhandler(413)
def too_big(e):
    return err("Photo is too large (max 6 MB).", 413)


@app.errorhandler(Exception)
def boom(e):
    if hasattr(e, "code") and isinstance(e.code, int) and e.code < 500:
        return err(getattr(e, "description", "Request error"), e.code)
    log.exception("Server error")
    return err("Server error. Please try again in a moment.", 500)


def admin_only(f):
    from functools import wraps

    @wraps(f)
    def w(*a, **k):
        t = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        try:
            signer.loads(t, max_age=8 * 3600)
        except BadSignature:
            return err("Please log in as administrator.", 401)
        return f(*a, **k)
    return w


def image_type(b):
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"\x89PNG":
        return "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/api/reports")
def create_report():
    f = request.form
    if f.get("website"):  # honeypot for bots
        return jsonify(id="SC-000000")
    cat = f.get("category", "")
    desc = f.get("description", "").strip()
    if cat not in CATS:
        return err("Please choose a valid issue type.")
    if not 10 <= len(desc) <= 1000:
        return err("Description must be 10-1000 characters.")
    try:
        lat, lng = float(f.get("lat")), float(f.get("lng"))
    except (TypeError, ValueError):
        return err("Please choose a location on the map.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return err("Location is out of range.")
    addr, name, contact = f.get("address", "")[:200], f.get("name", "")[:80], f.get("contact", "")[:120]
    photo, ptype = None, None
    up = request.files.get("photo")
    if up:
        photo = up.read()
        ptype = image_type(photo)
        if not ptype:
            return err("Photo must be a JPG, PNG or WebP image.")
    for _ in range(5):
        rid = "SC-" + "".join(secrets.choice(ALPHA) for _ in range(6))
        try:
            run("INSERT INTO reports(id,category,description,lat,lng,address,reporter_name,reporter_contact,photo,photo_type)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (rid, cat, desc, lat, lng, addr, name, contact, psycopg2.Binary(photo) if photo else None, ptype))
            return jsonify(id=rid), 201
        except psycopg2.errors.UniqueViolation:
            continue
    return err("Could not create report ID, try again.", 500)


@app.get("/api/reports")
def list_reports():
    rows = run(f"SELECT {PUB} FROM reports ORDER BY created_at DESC LIMIT 300", fetch="all")
    return jsonify([clean(r) for r in rows])


@app.get("/api/reports/<rid>")
def get_report(rid):
    r = run(f"SELECT {PUB} FROM reports WHERE id=%s", (rid.strip().upper(),), "one")
    return jsonify(clean(r)) if r else err("No report found with that ID.", 404)


@app.get("/api/stats")
def stats():
    rows = run("SELECT status,category,count(*)::int n FROM reports GROUP BY status,category", fetch="all")
    out = {"total": 0, "pending": 0, "in_progress": 0, "resolved": 0, "by_category": {}}
    key = {"Pending": "pending", "In Progress": "in_progress", "Resolved": "resolved"}
    for r in rows:
        out["total"] += r["n"]
        out[key[r["status"]]] += r["n"]
        out["by_category"][r["category"]] = out["by_category"].get(r["category"], 0) + r["n"]
    return jsonify(out)


@app.get("/api/photo/<rid>")
def photo(rid):
    r = run("SELECT photo,photo_type FROM reports WHERE id=%s", (rid.upper(),), "one")
    if not r or not r["photo"]:
        return err("No photo.", 404)
    return Response(bytes(r["photo"]), mimetype=r["photo_type"], headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/admin/login")
def login():
    pw = (request.get_json(silent=True) or {}).get("password", "")
    if not hmac.compare_digest(pw.encode(), ADMIN_PASSWORD.encode()):
        time.sleep(1.5)
        return err("Incorrect password.", 401)
    return jsonify(token=signer.dumps("admin"))


@app.get("/api/admin/reports")
@admin_only
def admin_list():
    rows = run(f"SELECT {ADM} FROM reports ORDER BY created_at DESC LIMIT 500", fetch="all")
    return jsonify([clean(r) for r in rows])


@app.patch("/api/admin/reports/<rid>")
@admin_only
def admin_update(rid):
    d = request.get_json(silent=True) or {}
    if d.get("status") not in STATUSES:
        return err("Invalid status.")
    r = run("UPDATE reports SET status=%s, admin_note=%s, updated_at=now() WHERE id=%s RETURNING id",
            (d["status"], str(d.get("note", ""))[:300], rid.upper()), "one")
    return jsonify(ok=True) if r else err("Report not found.", 404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
