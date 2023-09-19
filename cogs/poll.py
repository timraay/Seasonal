from typing import Dict, List
import discord
from discord import app_commands, Interaction, ui
from discord.ext import commands
from datetime import datetime
import re

from cogs.config import db
from cogs.match import ConfirmView
from lib.channels import NotFound
cur = db.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS "polls" (
	"guild_id"	INTEGER,
	"channel_id"	INTEGER,
	"message_id"	INTEGER,
	"votes"	TEXT,
	"question"	TEXT,
	PRIMARY KEY("message_id")
)''')
db.commit()


NUMBER_EMOJIS = [
    "0\ufe0f\u20e3",
    "1\ufe0f\u20e3",
    "2\ufe0f\u20e3",
    "3\ufe0f\u20e3",
    "4\ufe0f\u20e3",
    "5\ufe0f\u20e3",
    "6\ufe0f\u20e3",
    "7\ufe0f\u20e3",
    "8\ufe0f\u20e3",
    "9\ufe0f\u20e3",
    "\ud83d\udd1f"
]

POLLS: Dict[int, 'Poll'] = dict()

class Poll:
    def __init__(self, message: discord.Message, data: str, question: str):
        self.message = message
        self.data: Dict[int, List[int]]
        self.question = question
        self.load_data(data)
        POLLS[message.id] = self
    
    def load_data(self, data):
        res = dict()
        # 1:123,123,123,2:123,123,
        groups = re.split(r"(\d+):", data)
        del groups[0]
        while groups[:2]:
            choice = int(groups.pop(0))
            votes = groups.pop(0)
            votes = [int(vote) for vote in votes.split(',') if vote]
            res[choice] = votes
        self.data = res

    @classmethod
    def from_db(cls, message: discord.Message):
        cur.execute('''SELECT votes, question FROM polls WHERE message_id = ?''', (message.id,))
        data = cur.fetchone()
        if not data:
            raise NotFound("No poll associated with this message")
        return cls(message, *data)
    
    @classmethod
    def create(cls, message: discord.Message, num_choices: int, question: str):
        data = ""
        for i in range(1, num_choices + 1):
            data += f"{i}:"
        cur.execute('''INSERT INTO polls VALUES (?,?,?,?,?)''', (message.guild.id, message.channel.id, message.id, data, question))
        db.commit()
        return cls(message, data, question)
    
    @property
    def packed(self):
        output = ""
        for choice, votes in self.data.items():
            output += f"{choice}:"
            for vote in votes:
                output += f"{vote},"
        return output

    def save(self):
        cur.execute('''UPDATE polls SET
            votes = ?,
            question = ?
        WHERE message_id = ?''', (self.packed, self.question, self.message.id))
        db.commit()
    
    def delete(self):
        cur.execute('''DELETE FROM polls
        WHERE message_id = ?''', (self.message.id,))
        db.commit()
        if self.message.id in POLLS:
            del POLLS[self.message.id]
    
    def get_team_choice(self, role_id: int):
        for choice, votes in self.data.items():
            if role_id in votes:
                return choice
        return None
    
    @property
    def total_votes(self):
        return sum(len(votes) for votes in self.data.values())
    
    @property
    def voters(self):
        return [vote for votes in self.data.values() for vote in votes]

    def add_vote(self, role_id: int, choice: int):
        vote = self.get_team_choice(role_id)
        if vote is not None:
            index = self.data[vote].index(role_id)
            del self.data[vote][index]
        
        self.data[choice].append(role_id)
        self.save()


class poll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    PollGroup = app_commands.Group(name="poll", description="Polls", default_permissions=discord.Permissions())

    def _get_poll_view(self, num_choices: int):
        view = ui.View(timeout=None)
        async def on_press_1(interaction: Interaction):
            await self.user_make_vote(interaction, 1)
        async def on_press_2(interaction: Interaction):
            await self.user_make_vote(interaction, 2)
        async def on_press_3(interaction: Interaction):
            await self.user_make_vote(interaction, 3)
        async def on_press_4(interaction: Interaction):
            await self.user_make_vote(interaction, 4)
        async def on_press_5(interaction: Interaction):
            await self.user_make_vote(interaction, 5)
        async def on_press_6(interaction: Interaction):
            await self.user_make_vote(interaction, 6)
        async def on_press_7(interaction: Interaction):
            await self.user_make_vote(interaction, 7)
        async def on_press_8(interaction: Interaction):
            await self.user_make_vote(interaction, 8)
        async def on_press_9(interaction: Interaction):
            await self.user_make_vote(interaction, 9)
        async def on_press_10(interaction: Interaction):
            await self.user_make_vote(interaction, 10)
        
        callbacks = [on_press_1, on_press_2, on_press_3, on_press_4, on_press_5, on_press_6,
            on_press_7, on_press_8, on_press_9, on_press_10]

        for i in range(num_choices):
            button = ui.Button(style=discord.ButtonStyle.primary, emoji=NUMBER_EMOJIS[i+1])
            button.callback = callbacks[i]
            view.add_item(button)
        
        button = ui.Button(style=discord.ButtonStyle.gray, emoji="❓")
        button.callback = self.user_ask_vote_status
        view.add_item(button)

        return view

    @PollGroup.command(name="create", description="Create a poll here")
    async def poll_create(self, interaction: Interaction, question: str, choice1: str, choice2: str, choice3: str = None, choice4: str = None,
                          choice5: str = None, choice6: str = None, choice7: str = None, choice8: str = None, choice9: str = None, choice10: str = None):
        choices = [choice for choice in (choice1, choice2, choice3, choice4, choice5, choice6, choice7, choice8, choice9, choice10) if choice is not None]
        
        embed = discord.Embed(
            color=discord.Colour(3315710),
            description="\n".join(f"{NUMBER_EMOJIS[i]} {choice}" for i, choice in enumerate(choices, 1))
        )
        embed.set_author(name=question, icon_url="https://cdn.discordapp.com/attachments/729998051288285256/924971834343059496/unknown.png")
        embed.set_footer(text=f"0 votes • Only one vote per team. Press ❓ to see your team's vote.")

        view = self._get_poll_view(len(choices))
        
        await interaction.response.send_message(embed=embed, view=view)
        
        message = await interaction.original_response()
        Poll.create(message, len(choices), question)
    
    async def user_make_vote(self, interaction: Interaction, number: int):
        role = self.find_role(interaction.user)
        if not role:
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="You are not allowed to vote!", icon_url='https://cdn.discordapp.com/emojis/808045512393621585.png')
            embed.description = "Contact an Admin if you believe this is a mistake."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            poll = Poll.from_db(interaction.message)
        except NotFound:
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="This poll has expired!", icon_url='https://cdn.discordapp.com/emojis/808045512393621585.png')
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        vote = poll.get_team_choice(role.id)
        if vote:
            embed = discord.Embed(color=discord.Color.gold())
            embed.title = f"⚠️ You have already voted for **option {vote}**!"
            embed.description = f"Do you want to change your team's vote to **option {number}**?"

            async def on_confirm(_interaction: discord.Interaction):
                embed = discord.Embed(color=discord.Color(7844437))
                embed.set_author(name=f"Voted for option {number}!", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
                poll.add_vote(role.id, number)
                await _interaction.response.send_message(embed=embed, ephemeral=True)
            async def on_cancel(_interaction: discord.Interaction):
                embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
                embed.set_author(name="User cancelled the action", icon_url="https://cdn.discordapp.com/emojis/808045512393621585.png")
                await _interaction.response.send_message(embed=embed, ephemeral=True)

            await interaction.response.send_message(embed=embed, view=ConfirmView(on_confirm=on_confirm, on_cancel=on_cancel), ephemeral=True)
            return
        
        else:
            embed = discord.Embed(color=discord.Color(7844437))
            embed.set_author(name=f"Voted for option {number}!", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            poll.add_vote(role.id, number)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            embed = interaction.message.embeds[0]
            embed.set_footer(text=f"{poll.total_votes} votes • Only one vote per team. Press ❓ to see your team's vote.")
            await interaction.message.edit(embed=embed)

    async def user_ask_vote_status(self, interaction: Interaction):
        role = self.find_role(interaction.user)
        if not role:
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="You are not allowed to vote!", icon_url='https://cdn.discordapp.com/emojis/808045512393621585.png')
            embed.description = "Contact an Admin if you believe this is a mistake."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            poll = Poll.from_db(interaction.message)
        except NotFound:
            embed = discord.Embed(color=discord.Color.from_rgb(221, 46, 68))
            embed.set_author(name="This poll has expired!", icon_url='https://cdn.discordapp.com/emojis/808045512393621585.png')
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        vote = poll.get_team_choice(role.id)
        if vote:
            embed = discord.Embed(color=discord.Color(7844437))
            embed.set_author(name=f"Your current vote is option {vote}!", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
            embed.description = "To change your team's vote you can always press one of the buttons."
            embed.set_footer(text="Results will become visible once the poll has ended.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        else:
            embed = discord.Embed(
                title = "Your team has not yet voted!",
                description = "As long as the poll is still active you can cast your vote by pressing one of the buttons. You can change your choice later on."
            )
            embed.set_footer(text="Results will become visible once the poll has ended.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    def find_role(self, member: discord.Member):
        for role in member.roles:
            if role.name.endswith('*'):
                return role
        return None
    
    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        cur.execute('''SELECT votes FROM polls WHERE message_id = ?''', (payload.message_id,))
        if cur.fetchone():
            cur.execute('''DELETE FROM polls WHERE message_id = ?''', (payload.message_id,))
            db.commit()

    @commands.Cog.listener()    
    async def on_ready(self):
        cur.execute('''SELECT * FROM polls''')
        polls = cur.fetchall()
        for guild_id, channel_id, message_id, data, question in polls:
            guild = self.bot.get_guild(guild_id)
            channel = guild.get_channel(channel_id)
            try:
                message = await channel.fetch_message(message_id)
            except:
                print("Couldn't find poll", message_id, "in", channel.name)
            else:
                poll = Poll(message, data, question)
                view = self._get_poll_view(len(poll.data))
                await message.edit(view=view)

    async def poll_name_autocomplete(self, interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=poll.question if len(poll.question) < 100 else poll.question[:98]+'..', value=str(poll.message.id))
            for poll in POLLS.values() if
                poll.message.guild == interaction.guild
                and current.lower() in poll.question.lower()
        ]

    def get_results_embed(self, embed: discord.Embed, poll: Poll, show_teams: bool = False):
        embed = embed.copy()

        total_votes = len(poll.voters)
        highest_num_votes = max([len(votes) for votes in poll.data.values()])

        lines = list()
        for i, line in enumerate(embed.description.split('\n'), 1):
            votes = poll.data[i]
            num_votes = len(votes)
            percentage = (num_votes * 100 / total_votes) if total_votes else 0.0

            line = line.split(' ', 1)[1]
            vote_or_votes = "vote" if num_votes == 1 else "votes"
            if num_votes == highest_num_votes:
                line = f"✅ {line} | **__{num_votes} {vote_or_votes}__** " + "(__{:.1f}%__)".format(percentage)
            else:
                line = f"\🔳 {line} | **{num_votes} {vote_or_votes}** " + "({:.1f}%)".format(percentage)
            lines.append(line)

            if show_teams:
                roles = []
                for role_id in votes:
                    role = poll.message.guild.get_role(role_id)
                    if role.name.endswith('*'):
                        role = discord.utils.get(poll.message.guild.roles, name=role.name[:-1]) or role
                    roles.append(role)
                if roles:
                    line = "> " + ", ".join([role.mention for role in roles])
                    lines.append(line)
                lines.append('')

        embed.description = "\n".join(lines)
        return embed

    @PollGroup.command(name="end", description="End the poll and show the results")
    @app_commands.autocomplete(poll=poll_name_autocomplete)
    @app_commands.describe(
        reveal_teams="Whether to make each team's choice publically visible"
    )
    async def poll_results(self, interaction: Interaction, poll: str, reveal_teams: bool):
        poll: Poll = POLLS.get(int(poll), None)
        if poll is None or poll.message.guild != interaction.guild:
            raise commands.BadArgument("Unknown poll")
        
        embed = poll.message.embeds[0]

        embed_result = self.get_results_embed(embed, poll, show_teams=reveal_teams)
        embed_result.set_footer(text=f"{poll.total_votes} votes • The poll has ended. You can no longer vote.")
        await poll.message.edit(embed=embed_result, view=ui.View())
        poll.delete()

        embed_teams = self.get_results_embed(embed, poll, show_teams=True)
        embed_teams.remove_footer()
        embed_teams.color = discord.Color(7844437)
        embed_teams.description = f"[Jump to message]({poll.message.jump_url})\n\n" + embed_teams.description
        embed_teams.set_author(name=f"Ended poll!", icon_url="https://cdn.discordapp.com/emojis/809149148356018256.png")
        await interaction.response.send_message(embed=embed_teams, ephemeral=True)

    @PollGroup.command(name="interim", description="Silently show the poll's current results")
    @app_commands.autocomplete(poll=poll_name_autocomplete)
    async def poll_interim(self, interaction: Interaction, poll: str):
        poll: Poll = POLLS.get(int(poll), None)
        if poll is None or poll.message.guild != interaction.guild:
            raise commands.BadArgument("Unknown poll")
        
        embed = poll.message.embeds[0]
        embed = self.get_results_embed(embed, poll, show_teams=True)
                
        embed.description = f"[Jump to message]({poll.message.jump_url})\n\n" + embed.description
        embed.timestamp = datetime.now()
        embed.set_footer(text=f'{poll.total_votes} votes • To conclude the poll use "/poll end"')
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(poll(bot))