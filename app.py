import os, json, threading, queue, io
from flask import Flask, render_template, jsonify, request, send_file, Response, stream_with_context
from datetime import datetime
from dotenv import load_dotenv

from event_fetcher import EventFetcher
from excel_exporter import export_to_excel
from sharepoint_uploader import SharePointUploader

load_dotenv()

app = Flask(__name__)

# ── Global state (in-memory; persists until restart) ──────────────────────────
state = {
    "events": [],
    "last_run": None,
    "is_running": False,
}
sse_clients: list[queue.Queue] = []

DEFAULT_VENUES = [
    "CFG Bank Arena",
    "Coop Arena – Copenhagen",
    "Detroit Lions – Ford Field",
    "FCK – Parken Stadium Copenhagen",
    "Hamilton First Ontario Centre Arena",
    "Intuit Dome – Los Angeles",
    "Kansas City Chiefs – Arrowhead Stadium",
    "Las Vegas Raiders – Allegiant Stadium",
    "Live Nation – major US/Europe venues",
    "LA Clippers – Intuit Dome",
    "Mercedes-Benz Stadium – Atlanta",
    "Philadelphia Eagles – Lincoln Financial Field",
    "Phoenix Suns – Footprint Center",
    "SoFi Stadium – Los Angeles",
    "Tennessee Titans – Nissan Stadium",
    "Mediolanum Forum – Milan",
    "Inter Miami CF – Chase Stadium Fort Lauderdale",
    "Arizona Cardinals – State Farm Stadium Glendale",
]

# ── SSE helpers ────────────────────────────────────────────────────────────────
def push(msg: dict):
    dead = []
    for q in sse_clients:
        try:
            q.put_nowait(msg)
        except queue.Full:
            dead.append(q)
    for q in dead:
        sse_clients.remove(q)

@app.route("/stream")
def stream():
    q: queue.Queue = queue.Queue(maxsize=200)
    sse_clients.append(q)

    def generate():
        try:
            while True:
                try:
                    msg = q.get(timeout=55)
                except queue.Empty:
                    yield "data: {\"type\":\"ping\"}\n\n"
                    continue
                if msg == "__CLOSE__":
                    break
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            if q in sse_clients:
                sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template(
        "index.html",
        default_venues=DEFAULT_VENUES,
        anthropic_ok=bool(os.getenv("ANTHROPIC_API_KEY")),
        sharepoint_ok=bool(os.getenv("SP_SITE_URL")),
    )

@app.route("/api/status")
def api_status():
    return jsonify({
        "is_running": state["is_running"],
        "event_count": len(state["events"]),
        "last_run": state["last_run"],
        "anthropic_ok": bool(os.getenv("ANTHROPIC_API_KEY")),
        "sharepoint_ok": bool(os.getenv("SP_SITE_URL")),
    })

@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    if state["is_running"]:
        return jsonify({"error": "Already running"}), 429

    body = request.get_json(force=True)
    venues = [v.strip() for v in body.get("venues", DEFAULT_VENUES) if v.strip()]
    months = int(body.get("months", 3))

    def run():
        state["is_running"] = True
        state["events"] = []
        push({"type": "start", "total_venues": len(venues)})

        try:
            fetcher = EventFetcher(api_key=os.getenv("ANTHROPIC_API_KEY"))
            all_events = []
            batch_size = 4
            batches = [venues[i : i + batch_size] for i in range(0, len(venues), batch_size)]

            for idx, batch in enumerate(batches):
                push({
                    "type": "progress",
                    "pct": int((idx / len(batches)) * 90),
                    "msg": f"Searching {len(batch)} venues (batch {idx+1}/{len(batches)}): {', '.join(batch)}",
                })
                events = fetcher.fetch(batch, months)
                all_events.extend(events)
                push({"type": "batch_done", "new_events": events, "total": len(all_events)})

            state["events"] = sorted(all_events, key=lambda e: e.get("event_date", "9999"))
            state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            push({"type": "done", "count": len(state["events"]), "last_run": state["last_run"]})

        except Exception as exc:
            push({"type": "error", "msg": str(exc)})
        finally:
            state["is_running"] = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return jsonify({"status": "started"})

@app.route("/api/events")
def api_events():
    return jsonify({
        "events": state["events"],
        "last_run": state["last_run"],
        "count": len(state["events"]),
    })

@app.route("/api/export/excel")
def api_export_excel():
    if not state["events"]:
        return jsonify({"error": "No events loaded"}), 400
    buf = export_to_excel(state["events"])
    fname = f"events_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@app.route("/api/sharepoint/upload", methods=["POST"])
def api_sharepoint_upload():
    if not state["events"]:
        return jsonify({"error": "No events loaded"}), 400
    required = ["SP_TENANT_ID", "SP_CLIENT_ID", "SP_CLIENT_SECRET", "SP_SITE_URL"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        return jsonify({"error": f"Missing env vars: {', '.join(missing)}"}), 400
    try:
        buf = export_to_excel(state["events"])
        fname = f"events_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        uploader = SharePointUploader(
            tenant_id=os.getenv("SP_TENANT_ID"),
            client_id=os.getenv("SP_CLIENT_ID"),
            client_secret=os.getenv("SP_CLIENT_SECRET"),
            site_url=os.getenv("SP_SITE_URL"),
            folder_path=os.getenv("SP_FOLDER_PATH", "Shared Documents/Events"),
        )
        web_url = uploader.upload(buf, fname)
        return jsonify({"success": True, "url": web_url, "filename": fname})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
