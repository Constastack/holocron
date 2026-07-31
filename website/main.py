import os
import secrets
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, session, url_for

import db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


# ---------- Public pages ----------

@app.route("/")
def index():
    articles = db.get_articles(limit=5)
    upcoming_events = db.get_events(upcoming_only=True)[:5]
    return render_template("index.html", articles=articles, events=upcoming_events)


@app.route("/clanek/<slug>")
def article_detail(slug):
    article = db.get_article_by_slug(slug)
    if article is None:
        abort(404)
    return render_template("article.html", article=article)


@app.route("/kalendar")
def calendar():
    events = db.get_events(upcoming_only=True)
    return render_template("calendar.html", events=events)


# ---------- Admin auth ----------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        submitted = request.form.get("password", "")
        if ADMIN_PASSWORD and secrets.compare_digest(submitted, ADMIN_PASSWORD):
            session["is_admin"] = True
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        error = "Špatné heslo."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ---------- Admin dashboard ----------

@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


# ---------- Admin: articles ----------

@app.route("/admin/clanky")
@admin_required
def admin_articles():
    articles = db.get_articles()
    return render_template("admin_articles.html", articles=articles, editing=None)


@app.route("/admin/clanky/pridat", methods=["GET", "POST"])
@admin_required
def admin_article_add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if title and body:
            db.create_article(title, body)
            return redirect(url_for("admin_articles"))
    return render_template("admin_article_form.html", article=None)


@app.route("/admin/clanky/<int:article_id>/upravit", methods=["GET", "POST"])
@admin_required
def admin_article_edit(article_id):
    article = db.get_article_by_id(article_id)
    if article is None:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if title and body:
            db.update_article(article_id, title, body)
            return redirect(url_for("admin_articles"))
    return render_template("admin_article_form.html", article=article)


@app.route("/admin/clanky/<int:article_id>/smazat", methods=["POST"])
@admin_required
def admin_article_delete(article_id):
    db.delete_article(article_id)
    return redirect(url_for("admin_articles"))


# ---------- Admin: calendar ----------

@app.route("/admin/turnaje")
@admin_required
def admin_events():
    events = db.get_events()
    return render_template("admin_events.html", events=events)


@app.route("/admin/turnaje/pridat", methods=["GET", "POST"])
@admin_required
def admin_event_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        event_date = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()
        format_ = request.form.get("format", "").strip()
        link = request.form.get("link", "").strip()
        if name and event_date:
            db.create_event(name, event_date, location, format_, link)
            return redirect(url_for("admin_events"))
    return render_template("admin_event_form.html", event=None)


@app.route("/admin/turnaje/<int:event_id>/upravit", methods=["GET", "POST"])
@admin_required
def admin_event_edit(event_id):
    event = db.get_event(event_id)
    if event is None:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        event_date = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()
        format_ = request.form.get("format", "").strip()
        link = request.form.get("link", "").strip()
        if name and event_date:
            db.update_event(event_id, name, event_date, location, format_, link)
            return redirect(url_for("admin_events"))
    return render_template("admin_event_form.html", event=event)


@app.route("/admin/turnaje/<int:event_id>/smazat", methods=["POST"])
@admin_required
def admin_event_delete(event_id):
    db.delete_event(event_id)
    return redirect(url_for("admin_events"))


db.init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
