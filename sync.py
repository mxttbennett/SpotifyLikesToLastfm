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
MAX_UNLOVES = int(os.environ.get("MAX_UNLOVES_PER_RUN", "20"))
DRY_RUN = "--dry-run" in sys.argv[1:]

# Spotify's 429 Retry-After can be most of a day; failing lets the next hourly run try instead.
sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        redirect_uri="http://127.0.0.1:8888/callback",
        scope="user-library-read",
        cache_handler=CacheFileHandler(os.path.join(HERE, ".spotify_token")),
        open_browser=False,
    ),
    status_retries=0,
    requests_timeout=20,
)
network = pylast.LastFMNetwork(
    api_key=os.environ["LASTFM_API_KEY"],
    api_secret=os.environ["LASTFM_API_SECRET"],
    session_key=os.environ["LASTFM_SESSION_KEY"],
)


def clean_titles(tracks):
    if not tracks:
        return []
    out = subprocess.run(["node", os.path.join(HERE, "clean.mjs")], input=json.dumps(tracks),
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def saved_tracks():
    offset = 0
    while items := sp.current_user_saved_tracks(limit=50, offset=offset)["items"]:
        yield from (i["track"] for i in items)
        offset += 50


def log_line(artist, title, track_id):
    return f"{artist} - {title} - {track_id}"


def parse_log_line(line):
    artist, rest = line.split(" - ", 1)
    title, track_id = rest.rsplit(" - ", 1)
    return artist, title, track_id


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

logged = []
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, encoding="utf-8") as f:
        logged = [line.strip() for line in f if line.strip()]

liked = list(saved_tracks())
if not liked:
    sys.exit("Spotify returned no liked songs; refusing to treat every logged track as unliked")

liked_pairs = [{"artist": t["artists"][0]["name"], "title": t["name"]} for t in liked]
liked_cleans = clean_titles(liked_pairs)
liked_ids = {t["id"] for t in liked}
still_liked = {(p["artist"].casefold(), c.casefold()) for p, c in zip(liked_pairs, liked_cleans)}

# The log is the snapshot of what this script loved, so a logged id missing from Spotify was unliked.
unliked = [parse_log_line(line) for line in logged if parse_log_line(line)[2] not in liked_ids]
unliked_pairs = [{"artist": a, "title": t} for a, t, _ in unliked]
unloved = 0
dropped_ids = set()
if len(unliked) > MAX_UNLOVES:
    print(f"{len(unliked)} unliked tracks exceeds MAX_UNLOVES_PER_RUN={MAX_UNLOVES}; unloving none")
else:
    for (artist, _, track_id), clean in zip(unliked, clean_titles(unliked_pairs)):
        if (artist.casefold(), clean.casefold()) in still_liked:
            print(f"Kept {clean} by {artist}: still liked under another Spotify id")
        elif DRY_RUN:
            print(f"Would unlove {clean} by {artist}")
        else:
            try:
                network.get_track(artist, clean).unlove()
                unloved += 1
                print(f"Unloved {clean} by {artist}")
            except pylast.WSError as e:
                print(f"Skipped unloving {clean} by {artist}: {e}")
            time.sleep(0.25)
        dropped_ids.add(track_id)

if dropped_ids and not DRY_RUN:
    kept = [line for line in logged if parse_log_line(line)[2] not in dropped_ids]
    tmp = LOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(line + "\n" for line in kept)
    os.replace(tmp, LOG_FILE)

logged_set = set(logged)
new = [t for t in liked if log_line(t["artists"][0]["name"], t["name"], t["id"]) not in logged_set]

pairs = [{"artist": t["artists"][0]["name"], "title": t["name"]} for t in new]
loved = 0
for track, pair, clean in zip(new, pairs, clean_titles(pairs)):
    artist, title = pair["artist"], pair["title"]
    if DRY_RUN:
        print(f"Would love {clean} by {artist}")
        continue
    try:
        network.get_track(artist, clean).love()
        loved += 1
        print(f"Loved {clean} by {artist}")
    except pylast.WSError as e:
        # Logged anyway: an unloveable track would otherwise block every later run.
        print(f"Skipped {clean} by {artist}: {e}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line(artist, title, track["id"]) + "\n")
    time.sleep(0.25)

print(f"Loved {loved} new tracks, unloved {unloved}{' (dry run)' if DRY_RUN else ''}")
