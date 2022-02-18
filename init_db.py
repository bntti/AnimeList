import json
import sys
import anime_service
import database


def add_animes_and_synonyms(data):
    anime_count = len(data["data"])
    for i, anime_data in enumerate(data["data"]):
        if i % (anime_count // 10) == 0:
            print(f"{100 * i / anime_count:.0f}% done")

        # Get MyAnimeList link from anime sources
        myanimelist_link = ""
        for source in anime_data["sources"]:
            if "myanimelist.net" in source:
                myanimelist_link = source

        # Ignore some animes
        if myanimelist_link == "":
            continue

        anime = {
            "title": anime_data["title"],
            "episodes": anime_data["episodes"],
            "link": myanimelist_link,
            "picture": anime_data["picture"],
            "thumbnail": anime_data["thumbnail"],
            "hidden": "hentai" in anime_data["tags"]
        }
        anime_id = anime_service.add_anime(anime)

        # Add synonyms
        for synonym in anime_data["synonyms"]:
            database.add_synonym(anime_id, synonym)


def add_relations(data):
    anime_count = len(data["data"])
    for i, anime_data in enumerate(data["data"]):
        if i % (anime_count // 10) == 0:
            print(f"{100 * i / anime_count:.0f}% done")

        # Get MyAnimeList link from anime sources
        myanimelist_link = ""
        for source in anime_data["sources"]:
            if "myanimelist.net" in source:
                myanimelist_link = source

        # Ignore some animes
        if myanimelist_link == "":
            continue

        anime_id = anime_service.get_anime_id(myanimelist_link)
        for relation in anime_data["relations"]:
            if "myanimelist.net" in relation:
                related_id = anime_service.get_anime_id(relation)
                if related_id:
                    database.add_relation(anime_id, related_id)


def import_data():
    print("Opening file 'anime-offline-database-minified.json'")
    try:
        with open("anime-offline-database-minified.json", "r", encoding="utf-8") as file:
            print("Loading data form file")
            data = json.load(file)
    except FileNotFoundError:
        print("Download 'anime-offline-database-minified.json' from here:")
        print("https://github.com/manami-project/anime-offline-database/")
        sys.exit(0)

    print("Initializing tables")
    database.init_tables()

    print("Adding animes and synonyms to database")
    add_animes_and_synonyms(data)

    print("Adding related anime")
    add_relations(data)

    print("Committing changes")
    database.database.session.commit()

    print("Done!")
    sys.exit(0)


import_data()