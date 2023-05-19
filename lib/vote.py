from copy import deepcopy
from pathlib import Path
import imgkit
from io import BytesIO

from utils import get_config

import os
__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))

app_path = get_config()['wkhtmltoimage']['AppPath']
if app_path:
    app_path = Path(app_path)
    if not app_path.is_absolute():
        app_path = Path(os.getcwd()) / app_path
    config = imgkit.config(wkhtmltoimage=Path(__location__+'/vote/wkhtmltopdf/bin/wkhtmltoimage.exe'))
else:
    config = imgkit.config()

MAPS_WITH_BREAKS = get_config()['behavior']['MapPool'].split(',')
MAPS = [m for m in MAPS_WITH_BREAKS if m]
ACTIONS = ['available', 'chosen_by_you', 'chosen_by_opponent', 'final_pick']

HTML_MAP_ROW = """
  <tr>
    <td id="team1_allies{i}" class="{{team1_allies{i}}}"><div class="faction">Allies</div></td>
    <td id="team1_axis{i}" class="{{team1_axis{i}}}"><div class="faction">Axis</div></td>
    <td id="map{i}" class="index prevent-overflow"><div class="mapname">{mapname}</div></td>
    <td id="team2_allies{i}" class="{{team2_allies{i}}}"><div class="faction">Allies</div></td>
    <td id="team2_axis{i}" class="{{team2_axis{i}}}"><div class="faction">Axis</div></td>
  </tr>"""
HTML_EMPTY_ROW = """
  <tr>
    <td class="empty-row"></td>
  </tr>"""
with open(Path(__location__+'/vote/table.html'), 'r', encoding='utf-8') as f:
    rows = list()
    i = -1
    for mapname in MAPS_WITH_BREAKS:
        if not mapname:
            rows.append(HTML_EMPTY_ROW)
        else:
            i += 1
            rows.append(HTML_MAP_ROW.format(i=i, mapname=mapname))
    HTML_DOC = f.read().replace("BODY_HERE", "".join(rows))

class MapVote:

    def _translate_action(self, action):
        action_index = int(action[0])
        team_index = int(action[1])
        faction_index = int(action[2])
        map_index = int(action[3:])

        if faction_index == 0: faction = None
        elif faction_index == 1: faction = 'Allies'
        elif faction_index == 2: faction = 'Axis'
        
        map = MAPS[map_index]
        
        res = {
            'type': action_index, 'team_index': team_index,
            'faction_index': faction_index, 'faction': faction,
            'map_index': map_index, 'map': map
        }
        return res

    def get_last_team_index(self):
        if not self.progress: return None
        raw = self._translate_action(self.progress[-1])
        team_index = raw['team_index']
        return team_index

    def __init__(self, data=None, team1="TEAM 1", team2="TEAM 2"):
        self.team1 = {'allies': dict(), 'axis': dict()}
        self.team1['allies'] = {k: 'available' for k in MAPS}
        self.team1['axis'] = deepcopy(self.team1['allies'])
        self.team2 = deepcopy(self.team1)

        self.team1_name = str(team1)
        self.team2_name = str(team2)

        if not data: self.progress = list()
        else: self.progress = data.split(',')

        for action in self.progress:
            raw = self._translate_action(action)
            type_index = raw['type']
            team_index = raw['team_index']
            map_index = raw['map_index']
            faction = raw['faction']
            if faction: faction = faction.lower()

            if type_index == 1: status = 'chosen_by_you'
            elif type_index == 2: status = 'chosen_by_opponent'
            elif type_index == 3: status = 'final_pick'
            else: continue
            if team_index == 1: self.team1[faction][MAPS[map_index]] = status
            elif team_index == 2: self.team2[faction][MAPS[map_index]] = status


    def __str__(self):
        columns = list()
        for row in (self.team1['allies'], self.team1['axis'], self.team2['allies'], self.team2['axis']):
            column = ['0'] * len(MAPS)
            for i, value in enumerate(row.values()):
                if value == 'available': status = '0'
                elif value == 'chosen_by_you': status = '1'
                elif value == 'chosen_by_opponent': status = '2'
                elif value == 'final_pick': status = '3'
                column[i] = status
            column = ''.join(column)
            columns.append(column)
        return ','.join(columns)


    def update(self, team, faction, map, status):
        faction = str(faction).lower()
        if faction in ['allies', 'us', '1']: faction = 'allies'
        elif faction in ['axis', 'ger', '2']: faction = 'axis'
        else: raise ValueError('faction needs to be either allies or axis')

        map_index = [m.lower() for m in MAPS].index(map.lower())
        map = MAPS[map_index]

        status = str(status)
        if status == '0': status = 'available'
        elif status == '1': status = 'chosen_by_you'
        elif status == '2': status = 'chosen_by_opponent'
        elif status == '3': status = 'final_pick'
        elif status not in ['available', 'chosen_by_you', 'chosen_by_opponent', 'final_pick']: raise ValueError('status %s is unknown' % status)
        action = ACTIONS.index(status)

        team = int(team)
        if team == 1: self.team1[faction][map] = status
        elif team == 2: self.team2[faction][map] = status
        else: raise ValueError('Expected 1 or 2, received %s for team' % team)

        self.add_progress(team=team, faction=1 if faction == 'allies' else 2, map=MAPS.index(map), action=action)

    def add_progress(self, team: int, faction: int, map: int, action: int):
        code = str(action)+str(team)+str(faction)+str(map)
        self.progress.append(code)

    def ban(self, team, faction, map):
        team = int(team)
        self.update(team, faction, map, 'chosen_by_you')

        faction = str(faction).lower()
        if faction in ['allies', 'us', '1']: faction = 'axis'
        elif faction in ['axis', 'ger', '2']: faction = 'allies'
        self.update(2 if team == 1 else 1, faction, map, 'chosen_by_opponent')

    def final_pick(self, team, faction, map):
        team = int(team)
        self.update(team, faction, map, 'final_pick')

        faction = str(faction).lower()
        if faction in ['allies', 'us']: faction = 'axis'
        elif faction in ['axis', 'ger']: faction = 'allies'
        self.update(2 if team == 1 else 1, faction, map, 'final_pick')


    def render(self):
        statuses = dict()

        for team, data in enumerate([self.team1, self.team2]):
            team += 1
            for faction, column in data.items():
                for i, status in enumerate(column.values()):
                    key = f'team{team}_{faction}{i}'
                    statuses[key] = status

        statuses['team1_name'] = self.team1_name
        statuses['team2_name'] = self.team2_name

        html = HTML_DOC.format(**statuses)
        imgkit.from_string(html, 'output.png', config=config, css=Path(__location__+'/vote/table.css'), options={'format': 'png', 'quiet': ''})
        with open('output.png', 'rb') as f:
            img = BytesIO(f.read())

        return img



if __name__ == "__main__":
    vote = MapVote(data='4200,1221,2111')
    print(vote.team1)
    print(vote.team2)
    print(vote)
    vote.ban(team=1, faction='allies', map='SME')
    vote.ban(team=2, faction='axis', map='Foy')
    vote.final_pick(team=1, faction='allies', map='Hill 400')
    print(vote)
    vote.render()
    
    