import discord
from discord.ext import commands
from discord import app_commands, Interaction

from lib.channels import get_predictions
from utils import get_name

class predictions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="predictions", description="See your current prediction score")
    @app_commands.describe(
        user="The user whose score to see, yourself by default"
    )
    async def see_predictions(self, interaction: Interaction, user: discord.Member = None):
        user = user or interaction.user

        predictions = get_predictions(interaction.guild.id)
        sorted_predictions = sorted(predictions.items(), key=lambda x: x[1][0]*1000 - x[1][1], reverse=True)

        fmt = "`{: <5} {: <25} {: <5} {: <5} {: <4} {: <5}`"
        embed = discord.Embed(description=fmt.format("RANK", "USERNAME", "RIGHT", "WRONG", "SUM", "RATE"))
        author = "You have not yet made any predictions!" if user == interaction.user else f"{get_name(user)} has not yet made any predictions!"

        includes_user = user.id not in predictions
        for i, (user_id, (won, lost)) in enumerate(sorted_predictions):
            is_self = user_id == user.id

            if i < 20 or is_self:
                member = interaction.guild.get_member(user_id)
                rank = "#" + str(i+1)
                name = get_name(member).replace('`', '') if member else "Unknown user"
                sum = won + lost
                rate = won / sum
                pct = "100%" if won == sum else f"{round(rate*100, 1)}%"
                embed.description += ("\n" + fmt.format(rank, name[:25], won, lost, sum, pct))
                if is_self:
                    author = f"You have guessed right {won} times!" if user == interaction.user else f"{name} has guessed right {won} times!"
                    includes_user = True

                    if i == 0:
                        author = "🏆 " + author
                    elif i == 1:
                        author = "🥈 " + author
                    elif i == 2:
                        author = "🥉 " + author

            elif includes_user:
                break
            
            elif i == 20:
                embed.description += "\n..."
        
        embed.set_author(
            name=author,
            icon_url=user.avatar.url
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
    

            

        
        
                

async def setup(bot):
    await bot.add_cog(predictions(bot))