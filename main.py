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

queues = {}  # guild_id: list of queries

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class PlayerControls(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Pausado", ephemeral=True)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Reanudado", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Saltado", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: Button):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        if interaction.guild.id in queues:
            queues[interaction.guild.id].clear()
        await interaction.response.send_message("🛑 Detenido y desconectado", ephemeral=True)


async def play_next(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or not queues[guild_id]:
        return

    query = queues[guild_id].pop(0)

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            url = info['entries'][0]['url']
            title = info['entries'][0]['title']

        vc = ctx.voice_client
        if vc:
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTS)
            vc.play(source, after=lambda e: asyncio.create_task(play_next(ctx)))
            await ctx.send(f"▶️ Reproduciendo: **{title}**", view=PlayerControls(ctx))
    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await ctx.send("❌ Error al reproducir. Inténtalo de nuevo.")


@bot.hybrid_command(name="play", description="Reproduce una canción")
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ Debes estar en un canal de voz.")

    guild_id = ctx.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    queues[guild_id].append(query)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send(f"🔍 Buscando **{query}**...")
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        await play_next(ctx)
    else:
        await ctx.send(f"✅ Añadido a la cola: **{query}**")


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
            queues[ctx.guild.id] = []
        await ctx.send("🛑 Detenido y desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal.")


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot conectado como {bot.user}")


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN")
