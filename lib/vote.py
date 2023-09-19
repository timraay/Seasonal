from copy import deepcopy
from pathlib import Path
import imgkit
from io import BytesIO
from enum import IntEnum, Enum

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
    <td id="team1_Allies{i}" class="{{team1_Allies{i}}}"><div class="faction">Allies</div></td>
    <td id="team1_Axis{i}" class="{{team1_Axis{i}}}"><div class="faction">Axis</div></td>
    <td id="map{i}" class="index prevent-overflow"><div class="mapname">{mapname}</div></td>
    <td id="team2_Allies{i}" class="{{team2_Allies{i}}}"><div class="faction">Allies</div></td>
    <td id="team2_Axis{i}" class="{{team2_Axis{i}}}"><div class="faction">Axis</div></td>
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

class Action(IntEnum):
    BannedMap = 1
    WasDeniedMap = 2
    FinalPick = 3
    WonCoinflip = 4
    HasFirstBan = 5
class Team(IntEnum):
    One = 1
    Two = 2
    def other(self):
        return Team.Two if self == 1 else Team.One
class Faction(IntEnum):
    Unknown = 0
    Allies = 1
    Axis = 2
    def other(self):
        if self == 0:
            raise TypeError("Faction cannot be unknown")
        return Faction.Axis if self == 1 else Faction.Allies
    def __str__(self):
        return self.name
class MapState(IntEnum):
    Available = 0
    Banned = 1
    Denied = 2
    FinalPick = 3

class MapVote:

    def _translate_action(self, act: str):
        action = Action(int(act[0]))
        team = Team(int(act[1]))
        faction = Faction(int(act[2]))
        map_index = int(act[3:])
        
        map = MAPS[map_index]
        
        return dict(
            action=action,
            team=team,
            faction=faction,
            map_index=map_index,
            map=map
        )

    def get_last_team(self):
        if not self.progress:
            return None
        raw = self._translate_action(self.progress[-1])
        return raw['team']

    def __init__(self, data=None, team1="TEAM 1", team2="TEAM 2"):
        self.team1 = {Faction.Allies: dict(), Faction.Axis: dict()}
        self.team1[Faction.Allies] = {k: MapState.Available for k in MAPS}
        self.team1[Faction.Axis] = deepcopy(self.team1[Faction.Allies])
        self.team2 = deepcopy(self.team1)

        self.team1_name = str(team1)
        self.team2_name = str(team2)

        if not data:
            self.progress = list()
        else:
            self.progress = data.split(',')

        for action in self.progress:
            raw = self._translate_action(action)
            team = raw['team']
            faction = raw['faction']

            if not (0 < raw['action'] <= 3):
                continue
            
            if team == Team.One:
                self.team1[faction][raw['map']] = MapState(raw['action'])
            elif team == Team.Two:
                self.team2[faction][raw['map']] = MapState(raw['action'])

    def __str__(self):
        columns = list()
        for row in (self.team1[Faction.Allies], self.team1[Faction.Axis], self.team2[Faction.Allies], self.team2[Faction.Axis]):
            column = ['0'] * len(MAPS)
            for i, value in enumerate(row.values()):
                column[i] = str(value.value)
            column = ''.join(column)
            columns.append(column)
        return ','.join(columns)


    def update(self, team: Team, faction: Faction, map: str, action: Action):
        map_index = [m.lower() for m in MAPS].index(map.lower())
        map = MAPS[map_index]

        state = MapState(action)

        self.add_progress(team=team, faction=faction, map_index=map_index, action=action)
        if team == 1:
            self.team1[faction][map] = state
        elif team == 2:
            self.team2[faction][map] = state

    def add_progress(self, team: Team, faction: Faction, map_index: int, action: Action):
        team = Team(team)
        faction = Faction(faction)
        action = Action(action)
        code = str(action.value)+str(team.value)+str(faction.value)+str(map_index)
        self.progress.append(code)

    def ban(self, team: Team, faction: Faction, map: str):
        team = Team(team)
        faction = Faction(faction)
        self.update(team, faction, map, Action.BannedMap)
        self.update(team.other(), faction.other(), map, Action.WasDeniedMap)

    def final_pick(self, team: Team, faction: Faction, map: str):
        team = Team(team)
        faction = Faction(faction)
        self.update(team, faction, map, Action.FinalPick)
        self.update(team.other(), faction.other(), map, Action.FinalPick)

    def render(self):
        states = dict()

        for team, data in enumerate([self.team1, self.team2]):
            team += 1
            for faction, column in data.items():
                for i, state in enumerate(column.values()):
                    key = f'team{team}_{faction.name}{i}'
                    states[key] = state.name

        states['team1_name'] = self.team1_name
        states['team2_name'] = self.team2_name

        html = HTML_DOC.format(**states)
        imgkit.from_string(html, 'output.png', config=config, css=Path(__location__+'/vote/table.css'), options={'format': 'png', 'quiet': ''})
        with open('output.png', 'rb') as f:
            img = BytesIO(f.read())

        return img



if __name__ == "__main__":
    vote = MapVote(data='4200,1221,2111')
    print(vote.team1)
    print(vote.team2)
    print(vote)
    vote.ban(team=Team.One, faction=Faction.Allies, map='SME')
    vote.ban(team=Team.Two, faction=Faction.Axis, map='Foy')
    vote.final_pick(team=1, faction=Faction.Allies, map='Hill 400')
    print(vote)
    vote.render()
    
    