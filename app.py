import json as j
import logging
import os
import sys
from io import BytesIO

import matplotlib.pyplot as plt
import requests as r
from flask import Flask, render_template, send_file
from jinja2.exceptions import UndefinedError
from waitress import serve

# Server
HOST = "0.0.0.0"

# URLs
URL_LIVEGAME = "https://127.0.0.1:2999/liveclientdata/allgamedata"
URL_VERSION = "https://ddragon.leagueoflegends.com/api/versions.json"
URL_ITEMS = "https://ddragon.leagueoflegends.com/cdn/{}/data/en_US/item.json"
URL_SPLASH = "https://ddragon.leagueoflegends.com/cdn/{}/img/champion/{}.png"
URL_CHAMPIONS = "http://ddragon.leagueoflegends.com/cdn/{}/data/en_US/champion.json"

# Constants
TEAMS = ["ORDER", "CHAOS"]
POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

# Config
CONFIG = j.load(open("config.json", "r"))
PORT = CONFIG["PORT"]
COLOR_FONT = CONFIG["COLOR_FONT"]
COLOR_BACKGROUND = CONFIG["COLOR_BACKGROUND"]

invertTeamColors = False

app = Flask(__name__)
r.packages.urllib3.disable_warnings()

logging.basicConfig(
    filename="loldb.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)

try:
    version: str = r.get(url=URL_VERSION, verify=False).json()[0]
    champions = r.get(url=URL_CHAMPIONS.format(version), verify=False).json()
except:
    print("Could not reach riot api. Exiting...")
    exit(1)


def championNameToId(name: str) -> str:
    for champion in champions["data"]:
        if champions["data"][champion]["name"] == name:
            return champions["data"][champion]["id"]


class Package:
    def __init__(self, json) -> None:
        self.json = json
        self.summoners = self.getList()
        sortedbypos = self.sortByPosition()

        if len(sortedbypos) > 0:
            self.summoners = sortedbypos

        data = self.getData()
        self.dashboard = data[0]
        self.teamGold = data[1]
        self.gameMode = json["gameData"]["gameMode"]
        self.gameTime = float(json["gameData"]["gameTime"]) / 60

    def getList(self) -> list:
        summoners: list[Summoner] = []
        itemJson = r.get(url=URL_ITEMS.format(version), verify=False).json()

        goldlist = []
        for playerID in range(len(self.json["allPlayers"])):
            playerJson = self.json["allPlayers"][playerID]
            gold = 0

            # add up equip gold
            for slot in playerJson["items"]:
                item_id = str(slot["itemID"])
                gold += itemJson["data"][item_id]["gold"]["total"]

            goldlist.append(gold)

            # check if swap is needed
            global invertTeamColors
            invertTeamColors = (
                    self.json["activePlayer"]["summonerName"] == playerJson["summonerName"]
                    and playerJson["team"] == "CHAOS"
            )

            try:
                summoners[playerID].itemGold = gold

            except IndexError:
                summoner = Summoner(
                    championname=championNameToId(playerJson["championName"]),
                    team=playerJson["team"],
                    position=playerJson["position"],
                    itemGold=gold,
                    summonerName=playerJson["summonerName"],
                )
                summoners.append(summoner)

        # apply summoner ranks sorted by item gold descending
        goldlist.sort(reverse=True)
        for i in range(len(summoners)):
            summoners[i].rank = goldlist.index(summoners[i].itemGold) + 1

        return summoners

    def getData(self):
        data = []
        dashboard = []
        teamGold = [0, 0]
        teamSize = int(len(self.summoners) / 2)

        for i in range(teamSize):
            if invertTeamColors:
                row = {
                    "position": self.summoners[i].position,
                    "nameChaos": self.summoners[i].championName,
                    "rankChaos": self.summoners[i].rank,
                    "splashChaos": URL_SPLASH.format(
                        version, self.summoners[i].championName
                    ),
                    "nameOrder": self.summoners[i + teamSize].championName,
                    "rankOrder": self.summoners[i + teamSize].rank,
                    "splashOrder": URL_SPLASH.format(
                        version, self.summoners[i + teamSize].championName
                    ),
                    "goldChaos": "{:,}".format(self.summoners[i].itemGold),
                    "goldOrder": "{:,}".format(self.summoners[i + teamSize].itemGold),
                    "goldDiff": "{:,}".format(
                        self.summoners[i + teamSize].itemGold
                        - self.summoners[i].itemGold
                    ),
                }
            else:
                row = {
                    "position": self.summoners[i].position,
                    "nameOrder": self.summoners[i].championName,
                    "rankOrder": self.summoners[i].rank,
                    "splashOrder": URL_SPLASH.format(
                        version, self.summoners[i].championName
                    ),
                    "nameChaos": self.summoners[i + teamSize].championName,
                    "rankChaos": self.summoners[i + teamSize].rank,
                    "splashChaos": URL_SPLASH.format(
                        version, self.summoners[i + teamSize].championName
                    ),
                    "goldOrder": "{:,}".format(self.summoners[i].itemGold),
                    "goldChaos": "{:,}".format(self.summoners[i + teamSize].itemGold),
                    "goldDiff": "{:,}".format(
                        self.summoners[i].itemGold
                        - self.summoners[i + teamSize].itemGold
                    ),
                }

            if row["position"] == "":
                row["position"] = "empty"

            teamGold[0] += self.summoners[i].itemGold
            teamGold[1] += self.summoners[i + teamSize].itemGold
            dashboard.append(row)

        if invertTeamColors:
            teamGoldDiff = teamGold[1] - teamGold[0]
            teamData = {
                "order": "{:,}".format(teamGold[1]),
                "chaos": "{:,}".format(teamGold[0]),
                "diff": "{:,}".format(teamGoldDiff),
            }
        else:
            teamGoldDiff = teamGold[0] - teamGold[1]
            teamData = {
                "order": "{:,}".format(teamGold[0]),
                "chaos": "{:,}".format(teamGold[1]),
                "diff": "{:,}".format(teamGoldDiff),
            }

        data.append(dashboard)
        data.append(teamData)

        return data

    def sortByPosition(self) -> list:
        summonersSorted: list[Summoner] = []

        for teamID in range(len(TEAMS)):
            for positionID in range(len(POSITIONS)):
                for summonerID in range(len(self.summoners)):
                    summoner: Summoner = self.summoners[summonerID]
                    team = TEAMS[teamID]
                    position = POSITIONS[positionID]

                    if summoner.team.upper() == team and summoner.position == position:
                        summonersSorted.append(summoner)
                        break

        return summonersSorted

    def sortMostGold(self) -> list:
        summonersSorted: list[Summoner] = []
        while len(self.summoners) > 0:
            maxGold: int = self.summoners[0].itemGold
            maxSummoner: Summoner = self.summoners[0]

            for i in range(1, len(self.summoners)):
                summoner: Summoner = self.summoners[i]

                if summoner not in summonersSorted:
                    if summoner.itemGold > maxGold:
                        maxGold = summoner.itemGold
                        maxSummoner = summoner

            summonersSorted.append(maxSummoner)
            self.summoners.remove(maxSummoner)

        return summonersSorted


class Summoner:
    def __init__(
            self,
            championname: str,
            team: str,
            position: str,
            rank=0,
            itemGold=0,
            summonerName="",
    ):
        self.championName: str = championname
        self.team: str = team
        self.position: str = position.lower()
        self.itemGold: int = itemGold
        self.summonerName: str = summonerName
        self.rank: int = rank


p = None
lastDiff: list[int] = [0]
lastTime: list[float] = [0.0]


@app.route("/")
def index():
    def getTeamColors():
        if invertTeamColors:
            return {
                "left": "red",
                "right": "blue",
            }
        return {
            "left": "blue",
            "right": "red",
        }

    global p
    global lastDiff
    global lastTime

    try:
        if "-debug" in sys.argv[1:]:
            json = j.load(open(os.getcwd() + "/allgamedata.json", "r"))
        else:
            json = r.get(url=URL_LIVEGAME, verify=False).json()

        p = Package(json)

        teamGoldDiff = int((p.teamGold["diff"].replace(",", "")))

        if lastDiff[-1] != teamGoldDiff:
            lastDiff.append(teamGoldDiff)
            lastTime.append(p.gameTime)

        teamColors = getTeamColors()

        return render_template(
            "main.html",
            dashboardData=p.dashboard,
            teamData=p.teamGold,
            teamColors=teamColors,
        )

    except r.exceptions.ConnectionError or UndefinedError:
        if "-debug" in sys.argv[1:]:
            return render_template(
                "main.html", dashboardData=p.dashboard, teamData=p.teamGold
            )
        return render_template("error.html")

    except KeyError:
        lastDiff = [0]
        lastTime = [0]
        return render_template("loading.html")


@app.route("/teamGoldDiff.png")
def diffImage():
    plt.clf()
    fig = plt.figure(facecolor=COLOR_BACKGROUND)
    axes = plt.axes()
    axes.set_facecolor(COLOR_BACKGROUND)
    axes.xaxis.label.set_color(COLOR_FONT)
    axes.yaxis.label.set_color(COLOR_FONT)
    axes.spines["bottom"].set_color(COLOR_FONT)
    axes.spines["top"].set_color(COLOR_FONT)
    axes.spines["right"].set_color(COLOR_FONT)
    axes.spines["left"].set_color(COLOR_FONT)
    axes.tick_params(axis="x", colors=COLOR_FONT)
    axes.tick_params(axis="y", colors=COLOR_FONT)

    for y in range(-10000, 10000, 1000):
        if y < 0:
            color = "r"
            if invertTeamColors:
                color = "b"
            linewidth = 0.5
        elif y > 0:
            color = "b"
            if invertTeamColors:
                color = "r"
            linewidth = 0.5
        else:
            color = "k"
            linewidth = 1

        plt.plot([0, 120], [y, y], color=color, linewidth=linewidth, linestyle="-")

    if max(lastTime) == 0:
        plt.xlim(0, 1)
    else:
        plt.xlim(0, max(lastTime))

    if max(lastTime) == 0:
        plt.ylim(-100, 100)
    else:
        plt.ylim(min(lastDiff), max(lastDiff))

    plt.plot(lastTime, lastDiff, color="y", linewidth=2.5, linestyle="-")
    plt.xlabel("Minute")
    plt.ylabel("Gold Difference")
    img = BytesIO()
    plt.savefig(img)
    img.seek(0)
    plt.close(fig)

    return send_file(img, mimetype="image/png")


if __name__ == "__main__":
    try:
        serve(app, host=HOST, port=PORT)
    except OSError as e:
        if e.errno == 98:
            print(f"The port {PORT} on {HOST} is already in use. Exiting...")
            exit(1)

print("League Dashboard booted...")
print(f"Open http://{HOST}:{PORT}/ in your browser.")
