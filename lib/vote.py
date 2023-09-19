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
    ChoseMiddleGround = 6
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
class MiddleGroundVote(IntEnum):
    No = 0
    Yes = 1
    Skipped = 2
    def bool_or_none(self):
        if self.value == 0:
            return False
        elif self.value == 1:
            return True
        else:
            return None

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
        self.maps = {
            Team.One: {
                Faction.Allies: {k: MapState.Available for k in MAPS},
                Faction.Axis: {k: MapState.Available for k in MAPS}
            },
            Team.Two: {
                Faction.Allies: {k: MapState.Available for k in MAPS},
                Faction.Axis: {k: MapState.Available for k in MAPS}
            }
        }

        self.mg_vote = {
            Team.One: None,
            Team.Two: None,
        }

        self.names = {
            Team.One: str(team1),
            Team.Two: str(team2),
        }

        if not data:
            self.progress = list()
        else:
            self.progress = data.split(',')

        for action in self.progress:
            raw = self._translate_action(action)
            team = raw['team']
            faction = raw['faction']
            action = raw['action']

            if 0 < action <= 3:
                self.maps[team][faction][raw['map']] = MapState(raw['action'])
            elif action == Action.ChoseMiddleGround:
                self.mg_vote[team] = MiddleGroundVote(raw['map_index'])

    def __str__(self):
        columns = list()
        for team in self.maps.values():
            for row in team.values():
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
        self.maps[team][faction][map] = state

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

    def vote_middleground(self, team: Team, vote: MiddleGroundVote):
        team = Team(team)
        vote = MiddleGroundVote(vote)
        self.add_progress(team, Faction.Unknown, map_index=vote.value, action=Action.ChoseMiddleGround)
        self.mg_vote[team] = vote

        if vote == MiddleGroundVote.No and self.mg_vote[team.other()] is None:
            self.add_progress(team.other(), Faction.Unknown, map_index=MiddleGroundVote.Skipped.value, action=Action.ChoseMiddleGround)

    def render(self):
        states = dict()

        for team, data in self.maps.items():
            for faction, column in data.items():
                for i, state in enumerate(column.values()):
                    key = f'team{team}_{faction.name}{i}'
                    states[key] = state.name

        states['team1_name'] = self.names[1]
        states['team2_name'] = self.names[2]

        html = HTML_DOC.format(**states)
        imgkit.from_string(html, 'output.png', config=config, css=Path(__location__+'/vote/table.css'), options={'format': 'png', 'quiet': ''})
        with open('output.png', 'rb') as f:
            img = BytesIO(f.read())

        return img



if __name__ == "__main__":
    vote = MapVote(data='4200,1221,2111')
    print(vote.maps[1])
    print(vote.maps[2])
    print(vote)
    vote.ban(team=Team.One, faction=Faction.Allies, map='SME')
    vote.ban(team=Team.Two, faction=Faction.Axis, map='Foy')
    vote.final_pick(team=1, faction=Faction.Allies, map='Hill 400')
    print(vote)
    vote.render()
    
    