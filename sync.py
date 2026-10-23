import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
DATA = ROOT / "data"
MEMBERS_FILE = ROOT / "members.csv"
GAMES_FILE = DATA / "games.json"
LEADERBOARD_FILE = DATA / "leaderboard.json"
SYNC_FILE = DATA / "user_sync.json"
START_DATE = os.getenv("JEXCA_START_DATE", "2026-10-22")
INITIAL_RATING = 1200
K_FACTOR = 32
ALLOWED_SPEEDS = {"rapid", "blitz"}
ALLOWED_STATUSES = {"mate", "resign", "stalemate", "draw", "timeout", "outoftime", "variantEnd"}


def read_members():
    members = {}
    with MEMBERS_FILE.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("approved", "").strip().lower() not in {"yes", "y", "true", "1"}:
                continue
            username = row.get("lichess_username", "").strip().lower()
            if not username or username == "examplelichessuser":
                continue
            members[username] = {
                "member_id": row.get("member_id", "").strip(),
                "name": row.get("display_name", "").strip(),
                "username": row.get("lichess_username", "").strip(),
            }
    return members


def api_games(username, since_ms):
    # Official Lichess user-games export. NDJSON gives one JSON game per line.
    url = f"https://lichess.org/api/games/user/{quote(username)}?since={since_ms}&max=300&rated=true&moves=false&clocks=false&evals=false&opening=false&finished=true"
    request = Request(url, headers={"Accept": "application/x-ndjson", "User-Agent": "JEXCA-Chess-Club/1.0 (community leaderboard)"})
    with urlopen(request, timeout=45) as response:
        body = response.read().decode("utf-8")
    games = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            games.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return games


def load_old_games():
    if not GAMES_FILE.exists():
        return {}
    try:
        with GAMES_FILE.open(encoding="utf-8") as f:
            items = json.load(f)
        return {g["id"]: g for g in items if g.get("id")}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def fetch_all_members(members, old_games):
    # Track each member separately so newly approved members are backfilled from START_DATE.
    try:
        with SYNC_FILE.open(encoding="utf-8") as f:
            sync_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        sync_state = {}

    all_games = dict(old_games)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int(datetime.fromisoformat(START_DATE).replace(tzinfo=timezone.utc).timestamp() * 1000)
    for index, (username, member) in enumerate(members.items()):
        # Re-fetch the previous 48 hours to catch delayed completion; IDs deduplicate games.
        last_success = int(sync_state.get(username, 0) or 0)
        since_ms = max(start_ms, last_success - 48 * 60 * 60 * 1000) if last_success else start_ms
        if index:
            time.sleep(1.2)
        try:
            fetched = api_games(member["username"], since_ms)
            for game in fetched:
                if game.get("id"):
                    all_games[game["id"]] = game
            sync_state[username] = now_ms
            print(f"Fetched {len(fetched)} games for {member['username']}")
        except Exception as exc:
            print(f"WARNING: could not fetch games for {member['username']}: {exc}")
    with SYNC_FILE.open("w", encoding="utf-8") as f:
        json.dump(sync_state, f, ensure_ascii=False, indent=2)
    return all_games


def get_player(game, color):
    player = (game.get("players") or {}).get(color) or {}
    user = player.get("user") or {}
    return (user.get("name") or user.get("id") or "").lower(), player


def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def build_leaderboard(members, games_by_id):
    ratings = {speed: {username: INITIAL_RATING for username in members} for speed in ALLOWED_SPEEDS}
    stats = {speed: {username: {"played": 0, "wins": 0, "draws": 0, "losses": 0} for username in members} for speed in ALLOWED_SPEEDS}
    eligible = []

    for game in games_by_id.values():
        if game.get("variant", "standard") != "standard":
            continue
        speed = game.get("speed")
        if speed not in ALLOWED_SPEEDS:
            continue
        if game.get("status") not in ALLOWED_STATUSES:
            continue
        white_user, _ = get_player(game, "white")
        black_user, _ = get_player(game, "black")
        if white_user not in members or black_user not in members or white_user == black_user:
            continue
        winner = game.get("winner")
        if winner == "white":
            white_score, black_score = 1.0, 0.0
        elif winner == "black":
            white_score, black_score = 0.0, 1.0
        else:
            white_score = black_score = 0.5
        eligible.append((int(game.get("createdAt", 0)), game, speed, white_user, black_user, white_score, black_score))

    eligible.sort(key=lambda item: (item[0], item[1].get("id", "")))
    processed = []
    for created_at, game, speed, white, black, ws, bs in eligible:
        rw, rb = ratings[speed][white], ratings[speed][black]
        ew, eb = expected_score(rw, rb), expected_score(rb, rw)
        ratings[speed][white] = round(rw + K_FACTOR * (ws - ew))
        ratings[speed][black] = round(rb + K_FACTOR * (bs - eb))
        for username, score in ((white, ws), (black, bs)):
            stats[speed][username]["played"] += 1
            if score == 1:
                stats[speed][username]["wins"] += 1
            elif score == 0.5:
                stats[speed][username]["draws"] += 1
            else:
                stats[speed][username]["losses"] += 1
        white_member, black_member = members[white], members[black]
        processed.append({
            "id": game["id"],
            "date": datetime.fromtimestamp(created_at / 1000, timezone.utc).isoformat(),
            "speed": speed,
            "white": white_member["name"],
            "white_username": white_member["username"],
            "black": black_member["name"],
            "black_username": black_member["username"],
            "result": "1-0" if ws == 1 else "0-1" if bs == 1 else "½-½",
            "url": f"https://lichess.org/{game['id']}",
        })

    board = {}
    for speed in sorted(ALLOWED_SPEEDS):
        board[speed] = []
        for username, member in members.items():
            board[speed].append({**member, "rating": ratings[speed][username], **stats[speed][username]})
        board[speed].sort(key=lambda row: (-row["rating"], -row["wins"], row["name"].lower()))
        for rank, row in enumerate(board[speed], start=1):
            row["rank"] = rank
    return {"updated_at": datetime.now(timezone.utc).isoformat(), "start_date": START_DATE, "rating_method": "JEXCA Elo; initial rating 1200; K=32", "leaderboards": board, "games": list(reversed(processed[-100:]))}


def main():
    DATA.mkdir(exist_ok=True)
    members = read_members()
    if not members:
        raise SystemExit("No approved members found. Edit members.csv and set approved=yes.")
    old_games = load_old_games()
    all_games = fetch_all_members(members, old_games)
    with GAMES_FILE.open("w", encoding="utf-8") as f:
        json.dump(list(all_games.values()), f, ensure_ascii=False, separators=(",", ":"))
    leaderboard = build_leaderboard(members, all_games)
    with LEADERBOARD_FILE.open("w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)
    print(f"Members: {len(members)} | games stored: {len(all_games)} | eligible JEXCA games: {sum(len(x) for x in leaderboard['leaderboards'].values()) // 2}")


if __name__ == "__main__":
    main()
