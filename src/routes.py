import urllib.parse
from typing import Union

from flask import Response, abort, flash, redirect, render_template, request, session
from markupsafe import Markup

from app import app
from repositories import (
    anime_repository,
    list_repository,
    relation_repository,
    tag_repository,
    user_repository,
)
from services import list_service, user_service


# Url encoder
@app.template_filter("urlencode")
def url_encode(string: str) -> Markup:
    if isinstance(string, Markup):
        string = string.unescape()
    string = string.encode("utf8")
    string = urllib.parse.quote_plus(string)
    return Markup(string)


# /
@app.route("/")
def index() -> str:
    return render_template("index.html")


# /list
@app.route("/list/<path:username>", methods=["GET"])
def list_get(username: str) -> Union[str, Response]:
    data = user_repository.get_user_data(username)
    if not data:
        return "<h1>No user found<h1>"
    user_id, _ = user_repository.get_user_data(username)
    own_profile = "user_id" in session and session["user_id"] == user_id

    tag = request.args["tag"] if "tag" in request.args else ""
    status = request.args["status"] if "status" in request.args else "All"
    list_data = list_repository.get_list_data(user_id, status, tag)
    base_url = f"/list/{url_encode(username)}?"
    status_url = f"{base_url}status={status}"
    base_url = base_url if not tag else f"{base_url}tag={tag}&"

    return render_template(
        "list.html",
        base_url=base_url,
        status_url=status_url,
        tag=tag,
        username=username,
        own_profile=own_profile,
        list_data=list_data,
        status=status,
    )


@app.route("/list/<path:username>", methods=["POST"])
def list_post(username: str) -> Union[str, Response]:
    data = user_repository.get_user_data(username)
    if not data:
        return list_get(username)
    user_id, _ = user_repository.get_user_data(username)

    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])
    if "user_id" not in session or session["user_id"] != user_id:
        abort(403)

    tag = request.args["tag"] if "tag" in request.args else ""
    status = request.args["status"] if "status" in request.args else "All"
    list_data = list_repository.get_list_data(user_id, status, tag)

    # Handle list data change
    for anime in list_data:
        if request.form.get(f"remove_{anime['id']}"):
            list_repository.remove_from_list(user_id, anime["id"])
        else:
            list_service.handle_change(
                anime["id"],
                None,
                request.form.get(f"episodes_watched_{anime['id']}"),
                request.form.get(f"status_{anime['id']}"),
                request.form.get(f"score_{anime['id']}"),
            )

    flash("List updated")
    return list_get(username)


# /tags
@app.route("/tags")
def tags_get() -> str:
    popular_tags = tag_repository.get_popular_tags()
    tag_counts = tag_repository.get_tag_counts()
    return render_template(
        "tags.html", popular_tags=popular_tags, tag_counts=tag_counts
    )


# /topanime
@app.route("/topanime", methods=["GET"])
def topanime_get() -> str:
    list_ids = []
    if "user_id" in session:
        list_ids = list_repository.get_list_ids(session["user_id"])

    related = request.args["related"] if "related" in request.args else ""
    tag = request.args["tag"].lower() if "tag" in request.args else ""
    query = request.args["query"] if "query" in request.args else ""
    page = 0
    if "page" in request.args and request.args["page"].isdigit():
        page = int(request.args["page"])

    if not related:
        anime_count = anime_repository.anime_count(query, tag)
        top_anime = anime_repository.get_top_anime(page, query, tag)
    else:
        user_service.check_user()
        anime_count = relation_repository.related_anime_count(session["user_id"])
        top_anime = relation_repository.get_related_anime(page, session["user_id"])
        tag = ""
        query = ""
    page = max(0, min(anime_count - 50, page))
    prev_page = max(page - 50, 0)
    next_page = min(page + 50, max(0, anime_count - 50))

    # Base url and current url
    base_url = "/topanime?" if not query else f"/topanime?query={query}&"
    if tag:
        base_url += f"tag={url_encode(tag)}&"
    if related:
        base_url += "related=on&"
    current_url = base_url if page == 0 else f"{base_url}page={page}"

    return render_template(
        "topanime.html",
        top_anime=top_anime,
        query=query,
        tag=tag,
        related=related,
        list_ids=list_ids,
        current_url=current_url,
        prev_url=f"{base_url}page={prev_page}",
        next_url=f"{base_url}page={next_page}",
        show_prev=prev_page != page,
        show_next=next_page != page,
    )


@app.route("/topanime", methods=["POST"])
def topanime_post() -> str:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])
    list_repository.add_to_list(session["user_id"], int(request.form["anime_id"]))
    flash("Anime added to list")
    return topanime_get()


# /anime/id
@app.route("/anime/<int:anime_id>", methods=["GET"])
def anime_get(anime_id: int) -> str:
    anime = anime_repository.get_anime(anime_id)
    if not anime:
        return render_template("anime.html", anime=anime)

    user_data = {"in_list": False, "score": None}
    if "user_id" in session:
        new_data = list_repository.get_user_anime_data(session["user_id"], anime_id)
        user_data = new_data if new_data else user_data

    related_anime = relation_repository.get_anime_related_anime(anime_id)
    anime_tags = tag_repository.get_tags(anime_id)

    return render_template(
        "anime.html",
        anime=anime,
        user_data=user_data,
        related_anime=related_anime,
        tags=anime_tags,
    )


@app.route("/anime/<int:anime_id>", methods=["POST"])
def anime_post(anime_id: int) -> str:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])

    anime = anime_repository.get_anime(anime_id)
    if not anime:
        return anime_get(anime_id)

    # Anime is removed from list
    if request.form["submit"] == "Remove from list":
        list_repository.remove_from_list(session["user_id"], anime_id)
        flash("Anime removed from list")
        return anime_get(anime_id)

    # Anime is added to list
    if request.form["submit"] == "Add to list":
        flash("Anime added to list")
        list_repository.add_to_list(session["user_id"], anime_id)

    # Handle anime user data change
    list_service.handle_change(
        anime["id"],
        request.form.get("times_watched"),
        request.form.get("episodes_watched"),
        request.form.get("status"),
        request.form.get("score"),
    )

    if request.form["submit"] != "Add to list":
        flash("Updated anime data")

    return anime_get(anime_id)


# /profile
@app.route("/profile/<path:username>", methods=["GET"])
def profile_get(username: str) -> str:
    data = user_repository.get_user_data(username)
    if not data:
        return "<h1>No user found<h1>"
    user_id, _ = data
    own_profile = "user_id" in session and session["user_id"] == user_id
    counts = list_repository.get_counts(user_id)
    tags = request.args["tags"] if "tags" in request.args else ""
    if tags != "top":
        sorted_tags = list_repository.get_watched_tags(user_id)
    else:
        sorted_tags = list_repository.get_popular_tags(user_id)
    return render_template(
        "profile.html",
        tags=tags,
        own_profile=own_profile,
        username=username,
        list_url=f"/list/{url_encode(username)}",
        counts=counts,
        sorted_tags=sorted_tags,
    )


@app.route("/profile/<path:username>", methods=["POST"])
def profile_post(username: str) -> str:
    data = user_repository.get_user_data(username)
    if not data:
        return profile_get(username)
    user_id, _ = data

    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])
    if "user_id" not in session or session["user_id"] != user_id:
        abort(403)

    # Import from myanimelist
    if "mal_import" in request.files:
        file = request.files["mal_import"]
        list_service.import_from_myanimelist(file)
        return profile_get(username)

    # "Show hidden" setting change
    new_show_hidden = bool(request.form.get("show hidden"))
    if new_show_hidden != session["show_hidden"]:
        session["show_hidden"] = new_show_hidden
        user_repository.set_show_hidden(new_show_hidden)
        flash("Settings updated")

    return profile_get(username)


# /login
@app.route("/login", methods=["GET", "POST"])
def login() -> Union[str, Response]:
    username = ""
    password = ""
    previous_url = request.referrer
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        success = user_service.login(username, password)
        if success:
            flash("Logged in")
            return redirect(request.form["previous_url"])
        flash("Wrong username or password", "error")

    return render_template(
        "login.html", username=username, password=password, previous_url=previous_url
    )


# /register
@app.route("/register", methods=["GET", "POST"])
def register() -> Union[str, Response]:
    username = ""
    password1 = ""
    password2 = ""
    if request.method == "POST":
        username = request.form["username"]
        password1 = request.form["password1"]
        password2 = request.form["password2"]
        errors = user_service.register(username, password1, password2)
        if not errors:
            flash("Account created")
            return redirect("/")
        for error in errors:
            flash(error, "error")

    return render_template(
        "register.html", username=username, password1=password1, password2=password2
    )


# /logout
@app.route("/logout")
def logout() -> Response:
    user_service.logout()
    flash("Logged out")
    return redirect(request.referrer)
