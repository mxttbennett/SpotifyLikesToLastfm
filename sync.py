import json
import os
import subprocess
import sys
import time

import pylast
import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "loved_songs.log")

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.environ["SPOTIFY_CLIENT_ID"],
    client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
    redirect_uri="http://127.0.0.1:8888/callback",
    scope="user-library-read",
    cache_handler=CacheFileHandler(os.path.join(HERE, ".spotify_token")),
    open_browser=False,
))
network = pylast.LastFMNetwork(
    api_key=os.environ["LASTFM_API_KEY"],
    api_secret=os.environ["LASTFM_API_SECRET"],
    session_key=os.environ["LASTFM_SESSION_KEY"],
)

def clean_titles(tracks):
    out = subprocess.run(["node", os.path.join(HERE, "clean.mjs")], input=json.dumps(tracks),
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def saved_tracks():
    offset = 0
    while items := sp.current_user_saved_tracks(limit=50, offset=offset)["items"]:
        yield from (i["track"] for i in items)
        offset += 50


if sys.argv[1:] == ["--fix-loved"]:
    with open(LOG_FILE, encoding="utf-8") as f:
        count = sum(1 for _ in f)
    tracks = [t for _, t in zip(range(count), saved_tracks())]
    pairs = [{"artist": t["artists"][0]["name"], "title": t["name"]} for t in tracks]
    fixed = 0
    for pair, clean in zip(pairs, clean_titles(pairs)):
        if clean == pair["title"]:
            continue
        network.get_track(pair["artist"], pair["title"]).unlove()
        network.get_track(pair["artist"], clean).love()
        fixed += 1
        print(f"Relabelled {pair['title']} -> {clean}")
        time.sleep(0.5)
    print(f"Relabelled {fixed} of {count} loved tracks")
    sys.exit()

logged = set()
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, encoding="utf-8") as f:
        logged = {line.strip() for line in f}

# Skips rather than stops at a logged track, so an interrupted backfill resumes where it left off.
new = [t for t in saved_tracks() if f"{t['artists'][0]['name']} - {t['name']} - {t['id']}" not in logged]

pairs = [{"artist": t["artists"][0]["name"], "title": t["name"]} for t in new]
loved = 0
for track, pair, clean in zip(new, pairs, clean_titles(pairs) if pairs else []):
    artist, title = pair["artist"], pair["title"]
    try:
        network.get_track(artist, clean).love()
        loved += 1
        print(f"Loved {clean} by {artist}")
    except pylast.WSError as e:
        # Logged anyway: an unloveable track would otherwise block every later run.
        print(f"Skipped {clean} by {artist}: {e}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{artist} - {title} - {track['id']}\n")
    time.sleep(0.25)

print(f"Loved {loved} new tracks")
