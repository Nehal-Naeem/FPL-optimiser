import requests

TEAM_ID = 7425041
GAMEWEEK = 2

bootstrap = requests.get(
    "https://fantasy.premierleague.com/api/bootstrap-static/"
).json()

picks = requests.get(
    f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/event/{GAMEWEEK}/picks/"
).json()

players = {
    p["id"]: p
    for p in bootstrap["elements"]
}

teams = {
    t["id"]: t
    for t in bootstrap["teams"]
}

positions = {
    p["id"]: p["singular_name_short"]
    for p in bootstrap["element_types"]
}

for pick in picks["picks"]:
    player = players[pick["element"]]

    print(
        player["web_name"],
        teams[player["team"]]["name"],
        positions[player["element_type"]],
        player["now_cost"] / 10
    )