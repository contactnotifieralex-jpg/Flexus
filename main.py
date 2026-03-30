import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
from typing import List, Dict

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues: Dict[int, List[dict]] = {}
text_channels: Dict[int, discord.TextChannel] = {}

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

async def get_song_entries(query: str, max_results: int = 8) -> List[dict]:
    loop = asyncio.get_event_loop()
    def _extract():
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            if query.startswith(("http", "https")) and ("youtube.com" in query or "youtu.be" in query):
                info = ydl.extract_info(query, download=False)
                return info.get("entries", [info])[:max_results]
            else:
                info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                return info.get("entries", [])
    return await loop.run_in_executor(None, _extract)


class SongSelect(discord.ui.Select):
    def __init__(self, entries: List[dict]):
        self.entries = entries
        options = []
        for i, entry in enumerate(entries):
            title = (entry.get("title") or "Sin título")[:95]
            duration = entry.get("duration")
            dur_str = f"{int(duration//60)}:{int(duration%60):02d}" if duration else "LIVE"
            uploader = (entry.get("uploader") or "Desconocido")[:40]
            options.append(
                discord.SelectOption(
                    label=title,
                    description=f"{dur_str} • {uploader}",
                    value=str(i),
                    emoji="🎵"
                )
            )
        super().__init__(placeholder="Elige una canción...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            selected_idx = int(self.values[0])
            track = self.entries[selected_idx]

            guild = interaction.guild
            if not guild:
                return

            text_channels[guild.id] = interaction.channel

            queue = queues.setdefault(guild.id, [])
            queue.append(track)

            if not interaction.user.voice or not interaction.user.voice.channel:
                return await interaction.followup.send("❌ Debes estar en un canal de voz.", ephemeral=True)

            vc = guild.voice_client
            if not vc or not vc.is_connected():
                vc = await interaction.user.voice.channel.connect()

            # Reproducir si no hay nada sonando
            if not vc.is_playing() and not vc.is_paused():
                await self.play_next(guild)
                embed = discord.Embed(title="▶️ Reproduciendo ahora", description=f"**{track.get('title')}**", color=0x00ff00)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(f"✅ **{track.get('title')}** añadida a la cola.")

        except Exception as e:
            print(f"❌ Error en Select callback: {e}")
            try:
                await interaction.followup.send("❌ Ocurrió un error al procesar la selección.", ephemeral=True)
            except:
                pass

    async def play_next(self, guild: discord.Guild):
        queue = queues.get(guild.id, [])
        if not queue:
            return
        track = queue.pop(0)
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        url = track.get("url")
        title = track.get("title", "Canción")

        def after_play(error):
            if error:
                print(f"Error reproduciendo: {error}")
            asyncio.create_task(self.play_next(guild))

        try:
            vc.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTS), after=after_play)
            channel = text_channels.get(guild.id)
            if channel:
                embed = discord.Embed(title="▶️ Ahora suena", description=f"**{title}**", color=0x1DB954)
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Error al reproducir {title}: {e}")


class SongSelectView(discord.ui.View):
    def __init__(self, entries: List[dict]):
        super().__init__(timeout=180)
        self.add_item(SongSelect(entries))


@bot.tree.command(name="play", description="Busca y reproduce música con selección")
@app_commands.describe(query="Nombre o enlace de YouTube")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)

    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.followup.send("❌ Debes estar en un canal de voz.")

    await interaction.followup.send(f"🔍 Buscando **{query}**...")
    entries = await get_song_entries(query)

    if not entries:
        return await interaction.followup.send("❌ No encontré resultados.")

    view = SongSelectView(entries)
    embed = discord.Embed(
        title="🎵 Resultados de búsqueda",
        description=f"**{query}**\nElige una canción:",
        color=0x1DB954
    )
    await interaction.followup.send(embed=embed, view=view)


# Comandos básicos (pause, resume, stop, skip) se mantienen iguales que antes


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Bot conectado como {bot.user} | {len(synced)} comandos sincronizados")
    except Exception as e:
        print(f"Error sincronizando: {e}")


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN")
