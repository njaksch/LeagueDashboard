import logging
import socket
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
import requests
from flask import Flask, render_template, send_file
from waitress import serve

matplotlib.use('Agg')

PORT = 5000
COLOR_FONT = '#CECECE'
COLOR_BACKGROUND = '#1E1E1E'

URL_LIVEGAME: str = 'https://127.0.0.1:2999/liveclientdata/allgamedata'
URL_VERSION: str = 'https://ddragon.leagueoflegends.com/api/versions.json'
URL_ITEMS: str = 'https://ddragon.leagueoflegends.com/cdn/{}/data/en_US/item.json'
URL_SPLASH: str = 'https://ddragon.leagueoflegends.com/cdn/{}/img/champion/{}.png'

TEAMS = ['ORDER', 'CHAOS']
POSITIONS = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']
SPECIAL_NAMES = {
    'Kogmaw': 'KogMaw',
    'Nunu&Willump': 'Nunu',
    'Wukong': 'MonkeyKing',
    'RenataGlasc': 'Renata',
    'Reksai': 'RekSai'
}

logging.basicConfig(filename='/tmp/loldb.log', level=logging.WARN, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
# noinspection PyUnresolvedReferences
requests.packages.urllib3.disable_warnings()

current_patch: str = requests.get(url=URL_VERSION, verify=False).json()[0]
last_data = None
list_diff: list[int] = [0]
list_time: list[float] = [0.0]


class Summoner:
    def __init__(self, championname: str, team: str, position: str, rank=0, item_gold=0, summoner_name=''):
        self.championName: str = championname
        self.team: str = team
        self.position: str = position.lower()
        self.item_gold: int = item_gold
        self.summoner_name: str = summoner_name
        self.rank: int = rank

    @staticmethod
    def getList(game_json) -> list:
        def formatChampionName(name: str) -> str:
            try:
                spos = name.index('\'')
                formatted = name[0:spos] + name[spos + 1].lower() + name[spos + 2:]

            except ValueError:
                formatted = name.replace(' ', '').replace('.', '').replace('\'', '')

            if SPECIAL_NAMES.__contains__(formatted):
                return SPECIAL_NAMES[formatted]

            return formatted

        summoners: list[Summoner] = []
        item_json = requests.get(url=URL_ITEMS.format(current_patch), verify=False).json()

        goldlist = []
        for playerID in range(len(game_json['allPlayers'])):
            player_json = game_json['allPlayers'][playerID]
            gold = 0

            for slot in player_json['items']:
                item_id = str(slot['itemID'])
                gold += item_json['data'][item_id]['gold']['total']

            goldlist.append(gold)

            try:
                summoners[playerID].item_gold = gold

            except IndexError:
                summoner = Summoner(
                    championname=formatChampionName(player_json['championName']),
                    team=player_json['team'],
                    position=player_json['position'],
                    item_gold=gold,
                    summoner_name=player_json['summonerName'])
                summoners.append(summoner)

        goldlist.sort(reverse=True)
        for i in range(len(summoners)):
            summoners[i].rank = goldlist.index(summoners[i].item_gold) + 1

        return summoners

    @staticmethod
    def sortPositions(summoners) -> list:
        summoners_sorted: list[Summoner] = []

        for teamID in range(len(TEAMS)):
            for positionID in range(len(POSITIONS)):
                for summonerID in range(len(summoners)):
                    summoner: Summoner = summoners[summonerID]
                    team = TEAMS[teamID]
                    position = POSITIONS[positionID]

                    if summoner.team == team and summoner.position == position:
                        summoners_sorted.append(summoner)
                        break

        return summoners_sorted

    @staticmethod
    def sortMostGold(summoners) -> list:
        summoners_sorted: list[Summoner] = []
        while len(summoners) > 0:
            max_gold: int = summoners[0].item_gold
            max_summoner: Summoner = summoners[0]

            for i in range(1, len(summoners)):
                summoner: Summoner = summoners[i]

                if summoner not in summoners_sorted:
                    if summoner.item_gold > max_gold:
                        max_gold = summoner.item_gold
                        max_summoner = summoner

            summoners_sorted.append(max_summoner)
            summoners.remove(max_summoner)

        return summoners_sorted


class Dashboard:
    def __init__(self, summoners: list[Summoner]):
        self.summoners = summoners

    @staticmethod
    def getData(summoners):
        data = []
        dashboard_data = []
        team_gold = [0, 0]
        team_size = int(len(summoners) / 2)

        for i in range(team_size):
            row = {
                'position': summoners[i].position,
                'nameOrder': summoners[i].championName,
                'rankOrder': summoners[i].rank,
                'splashOrder': URL_SPLASH.format(current_patch, summoners[i].championName),
                'nameChaos': summoners[i + team_size].championName,
                'rankChaos': summoners[i + team_size].rank,
                'splashChaos': URL_SPLASH.format(current_patch, summoners[i + team_size].championName),
                'goldOrder': '{:,}'.format(summoners[i].item_gold),
                'goldChaos': '{:,}'.format(summoners[i + team_size].item_gold),
                'goldDiff': '{:,}'.format(summoners[i].item_gold - summoners[i + team_size].item_gold)
            }

            if row['position'] == '':
                row['position'] = 'empty'

            team_gold[0] += summoners[i].item_gold
            team_gold[1] += summoners[i + team_size].item_gold
            dashboard_data.append(row)

        team_gold_diff = team_gold[0] - team_gold[1]
        team_data = {
            'order': '{:,}'.format(team_gold[0]),
            'chaos': '{:,}'.format(team_gold[1]),
            'diff': '{:,}'.format(team_gold_diff)
        }

        gold_data = []
        summoners = Summoner.sortMostGold(summoners)

        for i in range(len(summoners)):
            # TODO: detect summoner instead of hardcoded line
            if summoners[i].summoner_name == 'waayne':
                color = 'yellow'
            elif summoners[i].team == TEAMS[0]:
                color = 'blue'
            else:
                color = 'red'
            row = {
                'color': color,
                'rank': i + 1,
                'champion': summoners[i].championName,
                'splash': URL_SPLASH.format(current_patch, summoners[i].championName),
                'gold': '{:,}'.format(summoners[i].item_gold)
            }
            gold_data.append(row)

        data.append(dashboard_data)
        data.append(team_data)
        data.append(gold_data)

        return data


def getTeamGoldDiffImage() -> BytesIO:
    plt.clf()
    fig = plt.figure(facecolor=COLOR_BACKGROUND)
    axes = plt.axes()
    axes.set_facecolor(COLOR_BACKGROUND)
    axes.xaxis.label.set_color(COLOR_FONT)
    axes.yaxis.label.set_color(COLOR_FONT)
    axes.spines['bottom'].set_color(COLOR_FONT)
    axes.spines['top'].set_color(COLOR_FONT)
    axes.spines['right'].set_color(COLOR_FONT)
    axes.spines['left'].set_color(COLOR_FONT)
    axes.tick_params(axis='x', colors=COLOR_FONT)
    axes.tick_params(axis='y', colors=COLOR_FONT)
    plt.plot(list_time, list_diff, color='y', linewidth=2.5, linestyle='-')
    plt.plot([0, 120], [0, 0], color='k', linewidth=1, linestyle='-')

    if max(list_time) == 0:
        plt.xlim(0, 1)
    else:
        plt.xlim(0, max(list_time))

    if max(list_time) == 0:
        plt.ylim(-100, 100)
    else:
        plt.ylim(min(list_diff), max(list_diff))

    plt.xlabel('Minute')
    plt.ylabel('Gold Difference')
    img = BytesIO()
    plt.savefig(img)
    img.seek(0)
    plt.close(fig)

    return img


@app.route('/')
def index():
    global last_data
    global list_diff
    global list_time

    try:
        game_json = requests.get(url=URL_LIVEGAME, verify=False).json()
        summoners = Summoner.getList(game_json)
        summoners_pos_sorted = Summoner.sortPositions(summoners)
        last_data = Dashboard.getData(summoners if len(summoners_pos_sorted) == 0 else summoners_pos_sorted)
        game_time = game_json['gameData']['gameTime'] / 60
        team_gold_diff = int((last_data[1]['diff'].replace(',', '')))

        if list_diff[-1] != team_gold_diff:
            list_diff.append(team_gold_diff)
            list_time.append(game_time)

        return render_template('main.html', dashboardData=last_data[0], teamData=last_data[1], goldData=last_data[2])

    except requests.exceptions.ConnectionError:
        if last_data is not None:
            return render_template('main.html', dashboardData=last_data[0], teamData=last_data[1],
                                   goldData=last_data[2])
        return render_template('error.html')

    except KeyError:
        list_diff = [0]
        list_time = [0]
        return render_template('loading.html')


@app.route('/teamGoldDiff.png')
def diffImage():
    return send_file(getTeamGoldDiffImage(), mimetype='image/png')


if __name__ == '__main__':
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    errorcode = s.connect_ex(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()

    if errorcode != 0:
        print('Could not start webserver')
        exit(1)

    print('League Dashboard booted...')
    print(f'Open https://{local_ip}:{PORT}/ in your browser.')

    serve(app, host="0.0.0.0", port=PORT)
