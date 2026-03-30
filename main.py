import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import asyncio
import os
from dotenv import load_dotenv
from discord.ui import View, Button

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn -loglevel quiet'  # Adjust these if needed
}

ytdl = YoutubeDL(ytdl_format_options)

queues = {}

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

async def play_next(ctx):
    server_id = ctx.guild.id
    try:
        # Check if there are any songs left in the queue
        if queues[server_id]:
            next_song_url = queues[server_id].pop(0)  # Get next song from the queue
            print(f"Playing next song: {next_song_url}")
            player = await YTDLSource.from_url(next_song_url, loop=bot.loop, stream=False)
            
            # Check if the bot is still connected and playing
            if ctx.voice_client:
                ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
                await ctx.send(f"🎶 Now playing: {player.title}\n{get_queue_message(server_id)}", view=PlayerControls(ctx))  # Show queue and buttons
            else:
                # If the bot gets disconnected, we handle it
                await ctx.send("Bot disconnected from the voice channel unexpectedly. Reconnecting...")
                await join(ctx)  # Reconnect to the channel
                await play_next(ctx)  # Retry playing the next song
        else:
            await ctx.voice_client.disconnect()  # Disconnect if no more songs in the queue
            await ctx.send("Queue finished. Left the voice channel.")
    except Exception as e:
        print(f"Error in play_next: {e}")
        await ctx.send(f"Error occurred while playing the song: {e}")

class PlayerControls(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)  # Timeout set to None to keep buttons active
        self.ctx = ctx

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice and interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Music paused.", ephemeral=True)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice and interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Music resumed.", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped!", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        if guild_id in queues:
            queues[guild_id].clear()
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("🛑 Stopped and left the channel.", ephemeral=True)

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
        await ctx.send("Joined the voice channel!")
    else:
        await ctx.send("You're not in a voice channel!")

def get_queue_message(server_id):
    """ Helper function to return the current queue as a string. """
    if server_id in queues and queues[server_id]:
        queue_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(queues[server_id])])
        return f"Current Queue:\n{queue_list}"
    return "The queue is empty!"

@bot.command()
async def play(ctx, *, url):
    server_id = ctx.guild.id

    # Initialize the queue if it's the first song for the server
    if server_id not in queues:
        queues[server_id] = []

    # If no one is connected to voice, make the bot join
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You're not in a voice channel!")
            return

    # If the bot is already playing a song, add the new song to the queue
    if ctx.voice_client.is_playing():
        queues[server_id].append(url)  # Add song to queue
        await ctx.send(f"✅ Added to queue: {url}\n{get_queue_message(server_id)}")
    else:
        # Play the song immediately if nothing is playing
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=False)
        ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f"🎶 Now playing: {player.title}\n{get_queue_message(server_id)}", view=PlayerControls(ctx))  # Show queue and buttons

@bot.command()
async def skip(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped the song.")
        if queues[ctx.guild.id]:
            await play_next(ctx)  # Automatically play the next song in the queue
    else:
        await ctx.send("❌ Nothing is playing.")

@bot.command()
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused the music.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed the music.")

@bot.command()
async def stop(ctx):
    """Stop the music and clear the queue"""
    server_id = ctx.guild.id
    if ctx.voice_client:
        ctx.voice_client.stop()
        if server_id in queues:
            queues[server_id].clear()
        await ctx.send("🛑 Stopped the music and cleared the queue.")

@bot.command()
async def queue(ctx):
    """Show the current queue"""
    server_id = ctx.guild.id
    if server_id in queues and queues[server_id]:
        q = '\n'.join([f"{i+1}. {url}" for i, url in enumerate(queues[server_id])])
        await ctx.send(f"📜 Current Queue:\n{q}")
    else:
        await ctx.send("📭 The queue is currently empty.")

@bot.command()
async def leave(ctx):
    """Leave the voice channel"""
    server_id = ctx.guild.id
    if server_id in queues:
        queues[server_id].clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel and cleared the queue.")


bot.run(TOKEN)
