import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from discord.ui import View, Button

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

queues = {}  # guild_id: list of urls/queries

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ytdl_format_options).extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else yt_dlp.YoutubeDL(ytdl_format_options).prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


async def play_next(ctx):
    server_id = ctx.guild.id
    try:
        if server_id in queues and queues[server_id]:
            next_song = queues[server_id].pop(0)
            player = await YTDLSource.from_url(next_song, loop=bot.loop, stream=True)

            if ctx.voice_client:
                ctx.voice_client.play(player, after=lambda e: asyncio.create_task(play_next(ctx)))
                await ctx.send(f"🎶 Now playing: **{player.title}**", view=PlayerControls(ctx))
            else:
                await ctx.send("Bot disconnected. Reconnecting...")
                await join(ctx)
                await play_next(ctx)
        else:
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
            await ctx.send("✅ Queue finished. Left the voice channel.")
    except Exception as e:
        print(f"Error in play_next: {e}")
        await ctx.send("❌ Error playing the next song.")


class PlayerControls(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Paused", ephemeral=True)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Resumed", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: Button):
        guild_id = interaction.guild.id
        if guild_id in queues:
            queues[guild_id].clear()
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("🛑 Stopped and disconnected.", ephemeral=True)


@bot.hybrid_command(name="play", description="Reproduce una canción")
async def play(ctx, *, url: str):
    server_id = ctx.guild.id
    if server_id not in queues:
        queues[server_id] = []

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            return await ctx.send("❌ Debes estar en un canal de voz.")

    queues[server_id].append(url)

    if not ctx.voice_client.is_playing():
        await ctx.send(f"🔍 Reproduciendo: **{url}**")
        await play_next(ctx)
    else:
        await ctx.send(f"✅ Añadido a la cola: **{url}**")


@bot.hybrid_command(name="skip")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Canción saltada.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")


@bot.hybrid_command(name="stop")
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
        await ctx.send("🛑 Detenido y desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")


@bot.hybrid_command(name="pause")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Pausado.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")


@bot.hybrid_command(name="resume")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Reanudado.")
    else:
        await ctx.send("❌ No hay nada pausado.")


@bot.hybrid_command(name="leave")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
        await ctx.send("👋 Desconectado del canal de voz.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")


@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        print(f"✅ Bot conectado como {bot.user}")
    except Exception as e:
        print(f"Error sincronizando: {e}")


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN en las variables de entorno de Railway")
