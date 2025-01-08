import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import os
import asyncio
from dotenv import load_dotenv
import discord
import ctypes
import ctypes.util

# Manually load Opus
# discord.opus.load_opus('/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.dylib')
# discord.opus.load_opus(None)
# print(f"Is Opus loaded? {discord.opus.is_loaded()}")

# Dynamically find and load the Opus library
libopus_path = ctypes.util.find_library('opus')
if libopus_path:
    discord.opus.load_opus(libopus_path)
else:
    raise RuntimeError("Opus library not found. Please install libopus-dev.")

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Directory containing audio files
AUDIO_DIRECTORY = os.path.join(os.path.dirname(__file__), "AudioFolder")

print(AUDIO_DIRECTORY)

# Ensure the directory exists
if not os.path.exists(AUDIO_DIRECTORY):
    raise FileNotFoundError(f"Audio directory not found at: {AUDIO_DIRECTORY}")

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True  # Enable Message Content Intent
intents.voice_states = True  # Ensure voice state tracking is enabled
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command(name="join")
async def join_channel(ctx):
    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to use this command!")
        return

    channel = ctx.author.voice.channel
    await channel.connect()
    await ctx.send(f"""
                Joined **{channel.name}**!
                Fenrys says nyan ~ 
                Type !playaudio for selection menu
                """)


@bot.command(name="leave")
async def leave_channel(ctx):
    global active_controllers

    if ctx.voice_client:
        # Remove the active controller for the channel
        if ctx.voice_client.channel.id in active_controllers:
            del active_controllers[ctx.voice_client.channel.id]

        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

        
active_controllers = {}
@bot.command(name="playaudio")
async def play_audio(ctx):
    global active_controllers

    guild_id = ctx.guild.id  # Server (guild) ID
    channel_id = ctx.voice_client.channel.id if ctx.voice_client else None

    # Check if someone else is already controlling the bot in this guild and channel
    if channel_id and channel_id in active_controllers:
        current_controller = active_controllers[channel_id]
        if current_controller != ctx.author.id:
            await ctx.send(f"🔒 The bot is currently controlled by **{bot.get_user(current_controller).name}**. Please wait until they release control.")
            return

    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to use this command!")
        return

    # Assign the current user as the active controller
    if ctx.voice_client:
        active_controllers[ctx.voice_client.channel.id] = ctx.author.id

    # Get list of audio files in the directory
    audio_files = [f for f in os.listdir(AUDIO_DIRECTORY) if f.lower().endswith(('.mp4', '.mp3'))]

    if not audio_files:
        await ctx.send("No audio files found in the directory.")
        return

    print(f"Filtered audio files: {audio_files}")  # Debugging

    # Track the invoking user and playback state
    selected_file_path = None
    current_playback_position = 0
    is_paused = False

    await ctx.send(f"🔊 **{ctx.author.name}** is controlling playback. Select an audio file below.")

    # Dropdown to select an audio file
    class AudioSelect(Select):
        def __init__(self):
            options = [
                discord.SelectOption(label=file, value=file) for file in audio_files
            ]
            super().__init__(placeholder="Select an audio file to play...", options=options)

        async def callback(self, interaction):
            nonlocal selected_file_path, current_playback_position, is_paused
            if interaction.user.id != active_controllers.get(ctx.voice_client.channel.id):
                await interaction.response.send_message("You are not allowed to use this control.", ephemeral=True)
                return

            selected_file = self.values[0]
            selected_file_path = os.path.join(AUDIO_DIRECTORY, selected_file)
            current_playback_position = 0
            is_paused = False
            print(f"Selected file: {selected_file}, Full path: {selected_file_path}")  # Debugging

            await interaction.response.send_message(f"File selected: {selected_file}. Press Start to play.", ephemeral=True)

    # Buttons for controlling playback
    start_button = Button(label="Start", style=discord.ButtonStyle.green)
    pause_button = Button(label="Pause", style=discord.ButtonStyle.gray)
    fast_forward_button = Button(label="+5s", style=discord.ButtonStyle.blurple)
    replay_button = Button(label="Replay", style=discord.ButtonStyle.blurple)

    # Button click events
    async def start_callback(interaction):
        nonlocal selected_file_path, current_playback_position, is_paused
        if interaction.user.id != active_controllers.get(ctx.voice_client.channel.id):
            await interaction.response.send_message("You are not allowed to use this control.", ephemeral=True)
            return

        if not selected_file_path:
            await interaction.response.send_message("No file selected. Please select a file first.", ephemeral=True)
            return

        if not ctx.voice_client:
            vc = await ctx.author.voice.channel.connect()
        else:
            vc = ctx.voice_client

        if vc.is_playing():
            vc.stop()

        # Play the selected file from the current position
        print(f"Starting playback: {selected_file_path} from position {current_playback_position}")  # Debugging
        vc.play(
            discord.FFmpegPCMAudio(
                selected_file_path,
                before_options=f"-ss {current_playback_position}"
            ),
            after=lambda e: print(f"Finished playing: {e}")
        )
        is_paused = False
        await interaction.response.send_message("Playback started!", ephemeral=True)


    async def pause_callback(interaction):
        nonlocal current_playback_position, is_paused
        if interaction.user.id != active_controllers.get(ctx.voice_client.channel.id):
            await interaction.response.send_message("You are not allowed to use this control.", ephemeral=True)
            return
        vc = ctx.voice_client
        if vc and vc.is_playing() and not is_paused:
            vc.stop()
            # Save the current playback position
            current_playback_position += 5  # Adjust based on expected time before stopping
            is_paused = True
            print(f"Paused at position: {current_playback_position}")
            await interaction.response.send_message("Playback paused.", ephemeral=True)
        elif is_paused:
            await interaction.response.send_message("Playback is already paused.", ephemeral=True)
        else:
            await interaction.response.send_message("No audio is playing.", ephemeral=True)

    async def fast_forward_callback(interaction):
        nonlocal selected_file_path, current_playback_position
        if interaction.user.id != active_controllers.get(ctx.voice_client.channel.id):
            await interaction.response.send_message("You are not allowed to use this control.", ephemeral=True)
            return
        if not selected_file_path:
            await interaction.response.send_message("No file selected. Please select a file first.", ephemeral=True)
            return

        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()

        # Fast forward by 5 seconds
        current_playback_position += 5
        print(f"Fast-forwarding to position: {current_playback_position}")

        vc.play(
            discord.FFmpegPCMAudio(
                selected_file_path,
                before_options=f"-ss {current_playback_position}"
            ),
            after=lambda e: print(f"Finished playing: {e}")
        )

        await interaction.response.send_message("Fast-forwarded by 5 seconds!", ephemeral=True)

    async def replay_callback(interaction):
        nonlocal selected_file_path, current_playback_position, is_paused
        if interaction.user.id != active_controllers.get(ctx.voice_client.channel.id):
            await interaction.response.send_message("You are not allowed to use this control.", ephemeral=True)
            return
        if not selected_file_path:
            await interaction.response.send_message("No file selected. Please select a file first.", ephemeral=True)
            return

        if not ctx.voice_client:
            vc = await ctx.author.voice.channel.connect()
        else:
            vc = ctx.voice_client

        if vc.is_playing():
            vc.stop()

        print(f"Replaying: {selected_file_path}")  # Debugging
        vc.play(discord.FFmpegPCMAudio(selected_file_path), after=lambda e: print(f"Finished playing: {e}"))
        current_playback_position = 0
        is_paused = False
        await interaction.response.send_message("Replaying the file from the beginning.", ephemeral=True)

    # Assign callbacks to buttons
    start_button.callback = start_callback
    pause_button.callback = pause_callback
    fast_forward_button.callback = fast_forward_callback
    replay_button.callback = replay_callback

    # Create a view for the dropdown and buttons
    view = View(timeout=1200)
    view.add_item(AudioSelect())
    view.add_item(start_button)
    view.add_item(pause_button)
    view.add_item(fast_forward_button)
    view.add_item(replay_button)

    # Send the message with dropdown and buttons
    await ctx.send("Select an audio file and control playback:", view=view)

@bot.event
async def on_voice_state_update(member, before, after):
    # If the bot is alone in the channel, disconnect
    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    if voice_client and len(voice_client.channel.members) == 1:
        await voice_client.disconnect()

bot.run(BOT_TOKEN)

