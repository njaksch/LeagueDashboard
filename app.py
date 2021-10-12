import logging
from io import BytesIO

import matplotlib.pyplot as plt
import requests
from flask import Flask, render_template, send_file

logging.basicConfig(filename='app.log', level=logging.WARN, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
requests.packages.urllib3.disable_warnings()

goldDiffData = [0]
gameTimeData = [0.0]


class Summoner:
    def __init__(self, champion, team, position, item_gold=0, summoner_name=''):
        self.champion = champion
        self.team = team
        self.position = position
        self.item_gold = item_gold
        self.summoner_name = summoner_name


def getSummonerList(game_json):
    summoners = []
    patch: str = requests.get(url='https://ddragon.leagueoflegends.com/api/versions.json', verify=False).json()[0]
    item_json = requests.get(url='http://ddragon.leagueoflegends.com/cdn/' + patch + '/data/en_US/item.json',
                             verify=False).json()
    for playerID in range(len(game_json['allPlayers'])):
        player_json = game_json['allPlayers'][playerID]
        gold = 0
        for slot in player_json['items']:
            item_id = str(slot['itemID'])
            gold += item_json['data'][item_id]['gold']['total']
        try:
            summoners[playerID].item_gold = gold
        except IndexError:
            summoner = Summoner(champion=player_json['championName'].lower().replace(' ', '_'),
                                team=player_json['team'], position=player_json['position'], item_gold=gold,
                                summoner_name=player_json['summonerName'])
            summoners.append(summoner)
    return summoners


def sortPositions(summonerList):
    sorted_summoners = []
    teams = ['ORDER', 'CHAOS']
    positions = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']
    for teamID in range(len(teams)):
        for positionID in range(len(positions)):
            for summonerID in range(len(summonerList)):
                summoner = summonerList[summonerID]
                team = teams[teamID]
                position = positions[positionID]
                if summoner.team == team and summoner.position == position:
                    sorted_summoners.append(summoner)
                    break
    return sorted_summoners


def sortMostGold(summonerList):
    sorted_summoners = []
    while len(summonerList) > 0:
        max_gold = summonerList[0].item_gold
        max_summoner = summonerList[0]
        for i in range(1, len(summonerList)):
            summoner = summonerList[i]
            if summoner not in sorted_summoners:
                if summoner.item_gold > max_gold:
                    max_gold = summoner.item_gold
                    max_summoner = summoner
        sorted_summoners.append(max_summoner)
        summonerList.remove(max_summoner)
    return sorted_summoners


def resetData():
    global goldDiffData
    global gameTimeData
    goldDiffData = [0]
    gameTimeData = [0]


def updateTeamGoldData(game_json: [int, slice], teamGoldDiff: int):
    game_time = game_json['gameData']['gameTime'] / 60
    if len(goldDiffData) == 0:
        logging.error('goldDiffData\'s length is 0')
        return False
    else:
        if goldDiffData[-1] != teamGoldDiff:
            goldDiffData.append(teamGoldDiff)
            gameTimeData.append(game_time)
            return True
        else:
            return False


def getTeamGoldDiffImage():
    plt.clf()
    plt.figure(facecolor='#1E1E1E')
    axes = plt.axes()
    axes.set_facecolor('#1E1E1E')
    axes.xaxis.label.set_color('#CECECE')
    axes.yaxis.label.set_color('#CECECE')
    axes.spines['bottom'].set_color('#CECECE')
    axes.spines['top'].set_color('#CECECE')
    axes.spines['right'].set_color('#CECECE')
    axes.spines['left'].set_color('#CECECE')
    axes.tick_params(axis='x', colors='#CECECE')
    axes.tick_params(axis='y', colors='#CECECE')
    plt.plot(gameTimeData, goldDiffData, color='r', linewidth=2.5, linestyle='-')
    plt.plot([0, 120], [0, 0], color='k', linewidth=1, linestyle='-')
    if max(gameTimeData) == 0:
        plt.xlim(0, 1)
    else:
        plt.xlim(0, max(gameTimeData))
    if max(gameTimeData) == 0:
        plt.ylim(-100, 100)
    else:
        plt.ylim(min(goldDiffData), max(goldDiffData))
    plt.xlabel('Minute')
    plt.ylabel('Gold Difference')
    img = BytesIO()
    plt.savefig(img)
    img.seek(0)
    return img


def getData(summoners):
    data = []
    dashboard_data = []
    team_gold = [0, 0]
    team_size = int(len(summoners) / 2)
    for i in range(team_size):
        row = {
            'position': summoners[i].position.lower(),
            'nameOrder': summoners[i].champion.lower().replace(' ', '_'),
            'nameChaos': summoners[i + team_size].champion.lower().replace(' ', '_'),
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
    summoners = sortMostGold(summoners)
    for i in range(len(summoners)):
        if summoners[i].summoner_name == 'waayne':
            color = 'yellow'
        elif summoners[i].team == 'ORDER':
            color = 'blue'
        else:
            color = 'red'
        row = {
            'color': color,
            'rank': i + 1,
            'name': summoners[i].champion.lower().replace(' ', '_'),
            'gold': '{:,}'.format(summoners[i].item_gold)
        }
        gold_data.append(row)
    data.append(dashboard_data)
    data.append(team_data)
    data.append(gold_data)
    return data


@app.route('/')
def index():
    try:
        game_json = requests.get(url='https://127.0.0.1:2999/liveclientdata/allgamedata', verify=False).json()
        summoners = sortPositions(getSummonerList(game_json))
        if len(summoners) == 0:
            summoners = getSummonerList(game_json)
        db = getData(summoners)
        updateTeamGoldData(game_json, int((db[1]['diff'].replace(',', ''))))
        return render_template('main.html', dashboardData=db[0], teamData=db[1], goldData=db[2])
    except requests.exceptions.ConnectionError:

        resetData()
        return render_template('error.html')
    except KeyError:
        resetData()
        return render_template('loading.html')


@app.route('/teamGoldDiff.png')
def diffImage():
    return send_file(getTeamGoldDiffImage(), mimetype='image/png', cache_timeout=1)


if __name__ == '__main__':
    from waitress import serve

    print('League Dashboard booted...')
    print('Open http://127.0.0.1:5000/ in your browser.')

    serve(app, host="0.0.0.0", port=5000)
