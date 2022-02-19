from typing import Union
import urllib.parse
from markupsafe import Markup
from flask import Response, render_template, request, session, redirect, abort
import user_service
import list_service
import anime_service
import relation_service
from app import app


# Url encoder
@app.template_filter('urlencode')
def urlencode_filter(s):
    if isinstance(s, Markup):
        s = s.unescape()
    s = s.encode('utf8')
    s = urllib.parse.quote_plus(s)
    return Markup(s)


# /
@app.route("/")
def index() -> str:
    return render_template("index.html")


# /list
@app.route("/list", methods=["GET"])
def list_get() -> Union[str, Response]:
    user_service.check_user()

    tag = request.args["tag"] if "tag" in request.args else ""
    status = request.args["status"] if "status" in request.args else "All"
    list_data = list_service.get_list_data(session["user_id"], status, tag)

    return render_template("list.html", list_data=list_data, status=status)


@app.route("/list", methods=["POST"])
def list_post() -> Union[str, Response]:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])

    tag = request.args["tag"] if "tag" in request.args else ""
    status = request.args["status"] if "status" in request.args else "All"
    list_data = list_service.get_list_data(session["user_id"], status, tag)

    # Handle list data change
    for anime in list_data:
        if request.form.get(f"remove_{anime['id']}"):
            list_service.remove_from_list(session["user_id"], anime["id"])
        else:
            list_service.handle_change(
                anime["id"],
                None,
                request.form.get(f"episodes_watched_{anime['id']}"),
                request.form.get(f"status_{anime['id']}"),
                request.form.get(f"score_{anime['id']}")
            )

    return list_get()


# /animes
@app.route("/animes", methods=["GET"])
def animes_get() -> str:
    list_ids = []
    if "user_id" in session:
        list_ids = list_service.get_list_ids(session["user_id"])

    query = request.args["query"] if "query" in request.args else ""
    page = 0
    if "page" in request.args and request.args["page"].isdigit():
        page = int(request.args["page"])

    anime_count = anime_service.anime_count(query)
    page = max(0, min(anime_count - 50, page))
    prev_page = max(page - 50, 0)
    next_page = min(page + 50, max(0, anime_count - 50))
    animes = anime_service.get_animes(page, query)

    # Base url and current url
    base_url = "/animes?" if not query else f"/animes?query={query}&"
    current_url = base_url if page == 0 else f"{base_url}page={page}"

    return render_template(
        "animes.html",
        animes=animes,
        query=query,
        list_ids=list_ids,
        current_url=current_url,
        prev_url=f"{base_url}page={prev_page}",
        next_url=f"{base_url}page={next_page}",
        show_prev=prev_page != page,
        show_next=next_page != page
    )


@app.route("/animes", methods=["POST"])
def animes_post() -> str:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])
    list_service.add_to_list(session["user_id"], int(request.form["anime_id"]))
    return animes_get()


# /anime/id
@app.route("/anime/<int:anime_id>", methods=["GET"])
def anime_get(anime_id) -> str:
    anime = anime_service.get_anime(anime_id)
    if not anime:
        return render_template("anime.html", anime=anime)

    user_data = {"in_list": False, "score": None}
    if "user_id" in session:
        new_data = list_service.get_user_anime_data(
            session["user_id"], anime_id
        )
        user_data = new_data if new_data else user_data

    related_anime = relation_service.get_anime_related_anime(anime_id)

    return render_template(
        "anime.html", anime=anime, user_data=user_data, related_anime=related_anime
    )


@app.route("/anime/<int:anime_id>", methods=["POST"])
def anime_post(anime_id) -> str:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])

    anime = anime_service.get_anime(anime_id)
    if not anime:
        return anime_get(anime_id)

    # Anime is removed from list
    if request.form["submit"] == "Remove from list":
        list_service.remove_from_list(session["user_id"], anime_id)
        return anime_get(anime_id)

    # Anime is added to list
    if request.form["submit"] == "Add to list":
        list_service.add_to_list(session["user_id"], anime_id)

    # Handle anime user data change
    list_service.handle_change(
        anime["id"],
        request.form.get("times_watched"),
        request.form.get("episodes_watched"),
        request.form.get("status"),
        request.form.get("score")
    )

    return anime_get(anime_id)


# /related
@app.route("/related", methods=["GET"])
def related_get() -> Union[str, Response]:
    user_service.check_user()
    related_anime = relation_service.get_user_related_anime(session["user_id"])
    return render_template("relations.html", related_anime=related_anime)


@app.route("/related", methods=["POST"])
def related_post() -> Union[str, Response]:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])
    list_service.add_to_list(session["user_id"], int(request.form["anime_id"]))
    return related_get()


# /profile
@app.route("/profile", methods=["GET"])
def profile_get() -> str:
    user_service.check_user()
    counts = list_service.get_counts(session["user_id"])
    tag_counts = list_service.get_tag_counts(session["user_id"])
    return render_template("profile.html", counts=counts, tag_counts=tag_counts)


@app.route("/profile", methods=["POST"])
def profile_post() -> str:
    user_service.check_user()
    user_service.check_csrf(request.form["csrf_token"])

    # Import from myanimelist
    if "mal_import" in request.files:
        file = request.files["mal_import"]
        if list_service.import_from_myanimelist(file):
            return profile_get()
        abort(Response("Error parsing XML file", 415))

    # "Show hidden" setting change
    new_show_hidden = True if request.form.get("show hidden") else False
    if new_show_hidden != session["show_hidden"]:
        session["show_hidden"] = new_show_hidden
        user_service.set_show_hidden(new_show_hidden)
    return profile_get()


# /login
@app.route("/login", methods=["GET", "POST"])
def login() -> Union[str, Response]:
    error = False
    username = ""
    password = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        error = not user_service.login(username, password)
        if not error:
            return redirect("/")

    return render_template("login.html", error=error, username=username, password=password)


# /register
@app.route("/register", methods=["GET", "POST"])
def register() -> Union[str, Response]:
    errors = []
    username = ""
    password1 = ""
    password2 = ""
    if request.method == "POST":
        username = request.form["username"]
        password1 = request.form["password1"]
        password2 = request.form["password2"]
        errors = user_service.register(username, password1, password2)
        if not errors:
            return redirect("/")

    return render_template(
        "register.html",
        errors=errors,
        username=username,
        password1=password1,
        password2=password2
    )


# /logout
@app.route("/logout")
def logout() -> Response:
    user_service.logout()
    return redirect("/")
