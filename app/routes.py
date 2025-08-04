from __future__ import annotations
from flask import (
    Blueprint, current_app, render_template,
    request, jsonify, abort, url_for, redirect
)

bp = Blueprint("main", __name__)

# -------- Helpers --------
def hf():
    h = getattr(current_app, "hf", None)
    if h is None:
        abort(500, description=current_app.config.get("HF_INIT_ERROR", "HF not initialized"))
    return h

def to_int(val, default, min_=1, max_=1000):
    try:
        v = int(val)
        return max(min_, min(max_, v))
    except Exception:
        return default


# -------- Pages --------
@bp.route("/")
def index():
    """
    Startseite mit Suche.
    Params:
      q     : Query (optional)
      lang  : 'arabic' | 'english' | 'both' (default)
      limit : max Treffer (default 50)
      page  : 1-basierte Seite (nur UI-Pagination)
      per   : Einträge pro Seite (default 20)
    """
    q = (request.args.get("q") or "").strip()
    lang = (request.args.get("lang") or "both").lower()
    limit = to_int(request.args.get("limit"), 50, 1, 500)
    page = to_int(request.args.get("page"), 1, 1, 10**6)
    per_page = to_int(request.args.get("per"), 20, 1, 200)

    results = []
    total = 0
    if q:
        results = hf().search(q, lang=lang, limit=limit)
        total = len(results)
        # UI-Pagination (clientseitig auf der Ergebnisliste)
        start = (page - 1) * per_page
        end = start + per_page
        results = results[start:end]

    return render_template(
        "index.html",
        q=q, lang=lang, limit=limit,
        results=results, total=total,
        page=page, per_page=per_page
    )


@bp.route("/hadith/<hid>")
def hadith_detail(hid: str):
    """
    Detailseite eines Hadiths.
    Optional:
      similar : Anzahl ähnlicher Hadithe (UI, default 0 = aus)
    """
    item = hf().get(hid)
    if not item:
        abort(404, description=f"Hadith not found: {hid}")

    k = to_int(request.args.get("similar"), 0, 0, 50)
    similars = hf().similar(hid, topk=k) if k > 0 else []

    return render_template("hadith.html", item=item, similars=similars)


@bp.route("/about")
def about():
    return render_template("about.html")


# -------- JSON APIs (praktisch für Notebooks/Skripte) --------
@bp.route("/api/health")
def api_health():
    ok = getattr(current_app, "hf", None) is not None
    return jsonify({"ok": ok, "error": current_app.config.get("HF_INIT_ERROR", "")}), (200 if ok else 500)


@bp.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    lang = (request.args.get("lang") or "both").lower()
    limit = to_int(request.args.get("limit"), 50, 1, 1000)
    data = hf().search(q, lang=lang, limit=limit)
    return jsonify(data)


@bp.route("/api/hadith/<hid>")
def api_hadith(hid: str):
    item = hf().get(hid)
    if not item:
        abort(404, description=f"Hadith not found: {hid}")
    return jsonify(item)


@bp.route("/api/similar/<hid>")
def api_similar(hid: str):
    topk = to_int(request.args.get("topk"), 10, 1, 100)
    data = hf().similar(hid, topk=topk)
    return jsonify(data)


# -------- Fehlerseiten --------
@bp.app_errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not_found", "detail": str(e)}), 404
    return render_template("errors/404.html", error=e), 404


@bp.app_errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "server_error", "detail": str(e)}), 500
    return render_template("errors/500.html", error=e), 500
