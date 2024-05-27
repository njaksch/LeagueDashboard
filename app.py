import json as j
import logging
import os
import socket
import sys
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
import requests
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
COLOR_FONT = CONFIG["DIAGRAMM_FONT"]
COLOR_BACKGROUND = CONFIG["DIAGRAMM_BACKGROUND"]

app = Flask(__name__)
matplotlib.use("agg")
requests.packages.urllib3.disable_warnings()

logging.basicConfig(
    filename="loldb.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)

try:
    version: str = requests.get(url=URL_VERSION, verify=False).json()[0]
    champions = requests.get(url=URL_CHAMPIONS.format(version), verify=False).json()
except requests.exceptions:
    print("Could not reach riot api. Exiting...")
    exit(1)


def championNameToId(name: str) -> str:
    for champion in champions["data"]:
        if champions["data"][champion]["name"] == name:
            return champions["data"][champion]["id"]


class Package:
    def __init__(self, json) -> None:

        def sortByPosition() -> list:
            summonersSorted: list[Summoner] = []

            for teamID in range(len(TEAMS)):
                for positionID in range(len(POSITIONS)):
                    for summonerID in range(len(self.summoners)):
                        summoner: Summoner = self.summoners[summonerID]
                        team = TEAMS[teamID]
                        position = POSITIONS[positionID]

                        if (
                            summoner.team.upper() == team
                            and summoner.position == position
                        ):
                            summonersSorted.append(summoner)
                            break

            return summonersSorted

        def sortMostGold() -> list:
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

        self.json = json
        self.summoners = self.getList()

        sortedbypos = sortByPosition()
        if len(sortedbypos) > 0:
            self.summoners = sortedbypos

        self.data = Data(self.summoners)
        self.gameMode = json["gameData"]["gameMode"]
        self.gameTime = float(json["gameData"]["gameTime"]) / 60

    def getList(self) -> list:
        summoners: list[Summoner] = []
        itemJson = requests.get(url=URL_ITEMS.format(version), verify=False).json()

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
            if self.json["activePlayer"]["summonerName"] == playerJson["summonerName"]:
                global TEAMS
                if playerJson["team"] == "ORDER":
                    TEAMS = ["ORDER", "CHAOS"]
                else:
                    TEAMS = ["CHAOS", "ORDER"]

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


class Data:
    def __init__(self, summoners: list):
        self.dashboard = []
        self.teamData = []
        teamGold = [0, 0]
        teamSize = int(len(summoners) / 2)

        for i in range(teamSize):
            row = {
                "position": summoners[i].position,
                "nameChaos": summoners[i].championName,
                "rankChaos": summoners[i].rank,
                "splashChaos": URL_SPLASH.format(version, summoners[i].championName),
                "nameOrder": summoners[i + teamSize].championName,
                "rankOrder": summoners[i + teamSize].rank,
                "splashOrder": URL_SPLASH.format(
                    version, summoners[i + teamSize].championName
                ),
                "goldChaos": "{:,}".format(summoners[i].itemGold),
                "goldOrder": "{:,}".format(summoners[i + teamSize].itemGold),
                "goldDiff": "{:,}".format(
                    summoners[i + teamSize].itemGold - summoners[i].itemGold
                ),
            }

            if row["position"] == "":
                row["position"] = "empty"

            teamGold[0] += summoners[i].itemGold
            teamGold[1] += summoners[i + teamSize].itemGold
            self.dashboard.append(row)

        teamGoldDiff = teamGold[1] - teamGold[0]
        self.teamData = {
            "order": "{:,}".format(teamGold[1]),
            "chaos": "{:,}".format(teamGold[0]),
            "diff": "{:,}".format(teamGoldDiff),
        }


p = None
lastDiff: list[int] = [0]
lastTime: list[float] = [0.0]


def isInverted() -> bool:
    return TEAMS[0] == "CHAOS"


@app.route("/")
def index():
    def getTeamColors():
        if isInverted():
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
            json = requests.get(url=URL_LIVEGAME, verify=False).json()

        p = Package(json)

        teamGoldDiff = int((p.data.teamData["diff"].replace(",", "")))

        if lastDiff[-1] != teamGoldDiff:
            lastDiff.append(teamGoldDiff)
            lastTime.append(p.gameTime)

        return render_template(
            "main.html",
            dashboardData=p.data.dashboard,
            teamData=p.data.teamData,
            teamColors=getTeamColors(),
        )

    except requests.exceptions.ConnectionError or UndefinedError:
        if "-debug" in sys.argv[1:]:
            return render_template(
                "main.html",
                dashboardData=p.data.dashboard,
                teamData=p.data.teamData,
                teamColors=getTeamColors(),
            )
        if len(lastTime) <= 1:
            return render_template("error.html")
        else:
            return render_template(
                "main.html",
                dashboardData=p.data.dashboard,
                teamData=p.data.teamData,
                teamColors=getTeamColors(),
            )

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
            if isInverted():
                color = "b"
            linewidth = 0.5
        elif y > 0:
            color = "b"
            if isInverted():
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


def get_local_ip():
    try:
        # Hier wird ein Dummy-Socket zu einer externen Adresse erstellt
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Es wird keine tatsächliche Verbindung zu dieser Adresse hergestellt
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception as ex:
        return f"Error retrieving local ip address: {ex}"


def get_external_ip():
    try:
        response = requests.get("https://api.ipify.org?format=json")
        response.raise_for_status()
        ip_info = response.json()
        external_ip = ip_info["ip"]
        return external_ip
    except requests.RequestException as ex:
        return f"Error retrieving external ip address: {ex}"


if __name__ == "__main__":
    try:
        print("League Dashboard booted...")
        print("You can now open")
        print(f"- http://127.0.0.1:{PORT}/")
        print(f"- http://{get_local_ip()}:{PORT}/")
        print(f"- http://{get_external_ip()}:{PORT}/")
        print("in your browser.")
        serve(app, host=HOST, port=PORT)
    except OSError as e:
        if e.errno == 98:
            print(f"The port {PORT} on {HOST} is already in use. Exiting...")
            exit(1)
