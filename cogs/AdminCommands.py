# cogs/AdminCommands.py - Contains commands for managing challeges, including challenege setup and shutdown.

import discord
from discord.ext import commands
from .utils import (
    save_challenge_data,
    load_challenge_data,
    load_config,
    save_config,
    display_leaderboard,
    end_challenge,
    calculate_average_rating,
)
from .db_utils import db_init, fetch_config, insert_challenge, fetch_challenge_data
import logging
import datetime
from discord.ui import Modal, TextInput
from discord import TextStyle

# Initialize logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("flask.app").setLevel(logging.ERROR)

# Initialize connection to database
con = db_init()
config = fetch_challenge_data(con)


class AttachmentsButton(discord.ui.View):
    def __init__(self, attachment_url):
        super().__init__()
        button = discord.ui.Button(label="📎 Attachment", style=discord.ButtonStyle.url, url=attachment_url)
        self.add_item(button)

# Modal Class to handle the setchallenge
title = f"Set a Challenge for Day {config['day']}" if config is not None and 'day' in config else "Set a Challenge"
class SetChallengeModal(discord.ui.Modal, title = title):
    def __init__(self, bot, config):
        super().__init__()
        self.bot = bot
        self.config = config

    description_input = discord.ui.TextInput(
        style=discord.TextStyle.long,
        label="Description",
        required=True,
        max_length=2000,
        placeholder="Description of the challenge",
    ) 

    answer_input = discord.ui.TextInput(
        style=discord.TextStyle.short,
        label="Answer",
        required=True,
        placeholder="Answer to the challenge",
    )

    attachment_input = discord.ui.TextInput(
        style=discord.TextStyle.short,
        label="Attachment",
        required=False,
        placeholder="Optional: Attach a single URL for files related to the challenge"
    )

    hints_input = discord.ui.TextInput(
        style=discord.TextStyle.short,
        label="Hints",
        required=True,
        placeholder="Hints for the challenge",
    )

    writeup_input = discord.ui.TextInput(
        style=discord.TextStyle.long,
        label="Write-up",
        required=False,  # Since it's optional
        max_length=2000,
        placeholder="Optional: Describe how to solve the challenge",
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            description = self.description_input.value
            answer = self.answer_input.value
            attachment = self.attachment_input.value
            hints = self.hints_input.value
            writeup = self.writeup_input.value

            insert_challenge(con, (interaction.user.id, description, answer, attachment, hints, writeup))
            
            challenge_data = fetch_challenge_data(con)

            challenge_ping = "@everyone"  # Maybe in the future I will change this to a specific role during setup process
            
            embed = discord.Embed(title=f"Day: {challenge_data['day']} Challenge")
            embed.add_field(name="Description:",
                            value=f"```{challenge_data['description']}```")
            embed.set_footer(text=f"Challenge submitted by {interaction.user.name}")
            challenge_channel = self.bot.get_channel(int(self.config["channel_id"]))

            if len(challenge_data['attachment']) == 0:  # idk, for what reason is None reurning false positives ?_?
                await challenge_channel.send(challenge_ping)
                await challenge_channel.send(embed=embed)
            else:
                await challenge_channel.send(challenge_ping)
                await challenge_channel.send(embed=embed, view=AttachmentsButton(challenge_data["attachment"]))

            await interaction.response.send_message(
                f"Challenge set successfully for Day {challenge_data['day']}!", ephemeral=True
            )   
       
        except Exception as e:
            logging.error(f"Error in on_submit: {e}")
            if "Scheme" in str(e):
                await interaction.response.send_message("Invalid URL scheme. Please provide a valid URL with 'http', 'https', or 'discord' scheme.", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"Failed to set challenge. Please check logs.", ephemeral=True
                )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logging.error(f"Error in SetChallengeModal: {error}")
        await interaction.response.send_message(f"Failed to set challenge.\nError: {error}", ephemeral=True)


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            self.config = fetch_config(con)
        except Exception as e:
            logging.error(f"Error loading config: {e}")

    @discord.app_commands.command(
        name="setchallenge", description="Create a new challenge"
    )
    async def setchallenge(self, interaction: discord.Interaction) -> None:
        try:
            self.config = fetch_config(con)
            
            if self.config is None:
                await interaction.response.send_message(
                "Failed to fetch config, Did you run `/setup`?", ephemeral=True
            )
                return

            if (
                discord.utils.get(
                    interaction.guild.roles, id=self.config["ctf_creators"]
                )
                in interaction.user.roles
            ):
                modal = SetChallengeModal(self.bot, self.config)
                await interaction.response.send_modal(modal)
            else:
                await interaction.response.send_message(
                    "You don't have permission to set a challenge!", ephemeral=True
                )
        except Exception as e:
            logging.error(f"Error in setchallenge: {e}")
            await interaction.response.send_message(
                "Failed to set challenge. Please check logs.", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error in setchallenge: {e}")
            await interaction.response.send_message(
                "Failed to set challenge. Please check logs.", ephemeral=True
            )

    @discord.app_commands.command(
        name="shutdown", description="Shutdowns active challenge"
    )
    async def shutdown(self, interaction: discord.Interaction) -> None:
        try:
            self.config = fetch_config(con)
            if self.config  is None:
                await interaction.response.send_message("Failed to fetch config, Did you run `/setup`?")
                return 

            if (
                discord.utils.get(
                    interaction.guild.roles, id=int(self.config["ctf_creators"])
                )
                not in interaction.user.roles
            ):
                await interaction.response.send_message(
                    "You don't have permission to shutdown the challenge!",
                    ephemeral=True,
                )
                return

            challenge_data = fetch_challenge_data(con)
            if not challenge_data:
                await interaction.response.send_message(
                    "No active challenge to shut down.", ephemeral=True
                )
                return

            challenge_channel = self.bot.get_channel(
                int(self.config["leaderboard_channel_id"])
            )
            if challenge_data["leaderboard"]:
                await display_leaderboard(self.bot)
            else:
                await challenge_channel.send("No one has solved the challenge yet.")

            await challenge_channel.send(
                f"Correct answer for Day-{challenge_data['day']} was: ||`{challenge_data['answer']}`||"
            )
            if challenge_data['writeup']:
                await challenge_channel.send(
                    f"Official Writeup: {challenge_data['writeup']}"
                )
            else:
                await challenge_channel.send(
                    f"No official writeup for Day-{challenge_data['day']}"
                )
            avg = calculate_average_rating()
            if avg is not None:
                await challenge_channel.send(
                    f"The average rating for the challenge is: {avg:.2f}"
                )
            else:
                await challenge_channel.send("No ratings received for the challenge.")
            save_challenge_data({})
            await interaction.response.send_message(
                "Challenge has been shut down and leaderboard has been printed.",
                ephemeral=True,
            )
        except Exception as e:
            logging.error(f"Error in shutdown: {e}")
            await interaction.response.send_message(
                "Failed to shutdown challenge. Please check logs.", ephemeral=True
            )


async def setup(bot) -> None:
    await bot.add_cog(AdminCommands(bot))
