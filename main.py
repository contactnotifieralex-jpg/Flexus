import discord
from discord.ext import commands
from discord.ui import View, Button
import yt_dlp
import asyncio
import os
import random

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Cola global
queues = {}          # guild_id: list of queries
now_playing = {}     # guild_id: current title
loop_mode = {}       # guild_id: bool

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

# ==================== REPRODUCCIÓN ====================
async def play_next(guild):
    if guild.id not in queues or not queues[guild.id]:
        now_playing[guild.id] = None
        return

    query = queues[guild.id].pop(0)
    now_playing[guild.id] = query

    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}" if not query.startswith("http") else query, download=False)
            url = info['entries'][0]['url'] if 'entries' in info else info['url']
            title = info['entries'][0]['title'] if 'entries' in info else info['title']

        def after_play(error):
            if error:
                print(f"Error: {error}")
            asyncio.create_task(play_next(guild))

        vc.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTS), after=after_play)

        # Enviar mensaje con botones
        channel = discord.utils.get(bot.get_all_channels(), guild=guild, name="music") or guild.text_channels[0]
        embed = discord.Embed(title="▶️ Reproduciendo", description=title, color=0x1DB954)
        await channel.send(embed=embed, view=MusicView(guild))

    except Exception as e:
        print(f"Error reproduciendo: {e}")
        await play_next(guild)


# ==================== VISTA CON 10 BOTONES ====================
class MusicView(View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="▶️ Play", style=discord.ButtonStyle.green)
    async def play_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.guild.voice_client and not self.guild.voice_client.is_playing():
            await play_next(self.guild)
            await interaction.followup.send("▶️ Reanudando reproducción...", ephemeral=True)

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.grey)
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.followup.send("⏸️ Pausado", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.blurple)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.followup.send("⏭️ Canción saltada", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        vc = self.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
            queues[self.guild.id] = []
            now_playing[self.guild.id] = None
            await interaction.followup.send("⏹️ Reproducción detenida y desconectado", ephemeral=True)

    @discord.ui.button(label="🔀 Shuffle", style=discord.ButtonStyle.grey)
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if self.guild.id in queues and queues[self.guild.id]:
            random.shuffle(queues[self.guild.id])
            await interaction.followup.send("🔀 Cola mezclada", ephemeral=True)

    @discord.ui.button(label="🔁 Loop", style=discord.ButtonStyle.grey)
    async def loop_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        loop_mode[self.guild.id] = not loop_mode.get(self.guild.id, False)
        status = "activado" if loop_mode[self.guild.id] else "desactivado"
        await interaction.followup.send(f"🔁 Loop {status}", ephemeral=True)

    @discord.ui.button(label="📋 Queue", style=discord.ButtonStyle.grey)
    async def queue_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        q = queues.get(self.guild.id, [])
        if not q:
            await interaction.followup.send("Cola vacía", ephemeral=True)
            return
        text = "\n".join([f"{i+1}. {song}" for i, song in enumerate(q)])
        await interaction.followup.send(f"**Cola actual:**\n{text}", ephemeral=True)

    @discord.ui.button(label="🎵 Now", style=discord.ButtonStyle.grey)
    async def now_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        title = now_playing.get(self.guild.id, "Nada reproduciéndose")
        await interaction.followup.send(f"🎵 Ahora suena: **{title}**", ephemeral=True)

    @discord.ui.button(label="🔊 +", style=discord.ButtonStyle.green, row=1)
    async def vol_up(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        vc = self.guild.voice_client
        if vc and vc.source:
            vc.source.volume = min(2.0, vc.source.volume + 0.1)
            await interaction.followup.send(f"🔊 Volumen: {int(vc.source.volume*100)}%", ephemeral=True)

    @discord.ui.button(label="🔊 -", style=discord.ButtonStyle.red, row=1)
    async def vol_down(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        vc = self.guild.voice_client
        if vc and vc.source:
            vc.source.volume = max(0.0, vc.source.volume - 0.1)
            await interaction.followup.send(f"🔊 Volumen: {int(vc.source.volume*100)}%", ephemeral=True)


# ==================== COMANDO PRINCIPAL ====================
@bot.hybrid_command(name="play", description="Reproduce música con controles")
async def play(ctx, *, query: str):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ Debes estar en un canal de voz.")

    guild_id = ctx.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    queues[guild_id].append(query)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send(f"🔍 Buscando **{query}**...")
        await ctx.guild.voice_client.disconnect() if ctx.voice_client else None
        vc = await ctx.author.voice.channel.connect()
        await play_next(ctx.guild)
    else:
        await ctx.send(f"✅ **{query}** añadido a la cola.")


@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        print(f"✅ Bot conectado como {bot.user} - Listo para reproducir música")
    except Exception as e:
        print(f"Error sync: {e}")


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN")
