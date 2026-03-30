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

# ==================== SISTEMA DE COLA AVANZADO ====================
queues: Dict[int, List[dict]] = {}          # guild_id → lista de canciones
text_channels: Dict[int, discord.TextChannel] = {}  # guild_id → canal donde se escribió /play

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': False,          # permite playlists pequeñas
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
    'extract_flat': False,
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# ==================== FUNCIÓN DE BÚSQUEDA PROFESIONAL ====================
async def get_song_entries(query: str, max_results: int = 8) -> List[dict]:
    """Busca por nombre o enlace de YouTube y devuelve hasta 8 resultados."""
    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            # Si es enlace directo de YouTube → extrae la canción exacta (o playlist)
            if query.startswith(("http://", "https://")) and ("youtube.com" in query or "youtu.be" in query):
                info = ydl.extract_info(query, download=False)
                if "entries" in info:  # es playlist
                    return info["entries"][:max_results]
                return [info]  # canción única
            else:
                # Búsqueda normal
                info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                return info.get("entries", [])

    return await loop.run_in_executor(None, _extract)

# ==================== MENÚ DE SELECCIÓN BONITO ====================
class SongSelect(discord.ui.Select):
    def __init__(self, entries: List[dict]):
        self.entries = entries
        options = []

        for i, entry in enumerate(entries):
            title = entry.get("title", "Sin título")[:97]
            if len(entry.get("title", "")) > 97:
                title += "..."

            duration = entry.get("duration")
            dur_str = f"{duration//60}:{duration%60:02d}" if duration else "LIVE"

            uploader = entry.get("uploader", "Desconocido")[:40]

            options.append(
                discord.SelectOption(
                    label=title,
                    description=f"{dur_str} • {uploader}",
                    value=str(i),
                    emoji="🎵"
                )
            )

        super().__init__(
            placeholder="🎵 Elige la canción que quieres reproducir...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_idx = int(self.values[0])
        track = self.entries[selected_idx]

        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("❌ Error interno.")

        # Guardar canal de texto para mensajes automáticos
        text_channels[guild.id] = interaction.channel

        # Añadir a cola
        queue = queues.setdefault(guild.id, [])
        queue.append(track)

        # Unirse al canal de voz
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("❌ Debes estar en un canal de voz.")

        vc = guild.voice_client
        if not vc or not vc.is_connected():
            vc = await interaction.user.voice.channel.connect()

        # Si no está reproduciendo nada → reproducir inmediatamente
        if not vc.is_playing() and not vc.is_paused():
            await play_next(guild)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="✅ Reproduciendo",
                    description=f"**{track.get('title')}**",
                    color=0x00ff00
                )
            )
        else:
            await interaction.followup.send(
                f"➕ **{track.get('title')}** añadida a la cola (posición {len(queue)})"
            )


class SongSelectView(discord.ui.View):
    def __init__(self, entries: List[dict]):
        super().__init__(timeout=120)  # 2 minutos para elegir
        self.add_item(SongSelect(entries))

    async def on_timeout(self):
        # Opcional: puedes editar el mensaje cuando caduque
        pass


# ==================== REPRODUCCIÓN Y COLA ====================
async def play_track(vc: discord.VoiceClient, guild: discord.Guild, track: dict):
    """Reproduce una canción y configura el siguiente automáticamente."""
    url = track.get("url")  # URL directa de audio que da yt-dlp
    title = track.get("title", "Canción desconocida")

    def after_play(error):
        if error:
            print(f"Error en reproducción: {error}")
        asyncio.create_task(play_next(guild))

    vc.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTS), after=after_play)

    # Mensaje bonito de "Ahora suena"
    channel = text_channels.get(guild.id)
    if channel:
        embed = discord.Embed(
            title="▶️ Ahora suena",
            description=f"**{title}**",
            color=0x1DB954
        )
        await channel.send(embed=embed)


async def play_next(guild: discord.Guild):
    """Reproduce la siguiente canción de la cola."""
    queue = queues.get(guild.id, [])
    if not queue:
        return

    track = queue.pop(0)  # sacamos la primera
    vc = guild.voice_client

    if vc and vc.is_connected():
        await play_track(vc, guild, track)


# ==================== COMANDO /play ====================
@bot.tree.command(name="play", description="Busca y reproduce música de YouTube con selección")
@app_commands.describe(query="Nombre de la canción o enlace completo de YouTube")
async def play(interaction: discord.Interaction, query: str):
    """Comando principal: busca, muestra panel bonito y reproduce."""
    await interaction.response.defer(thinking=True)

    # Verificar que esté en voz
    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.followup.send("❌ Debes estar en un canal de voz para usar este comando.")

    # Buscar canciones
    await interaction.followup.send(f"🔍 Buscando **{query}**...")
    entries = await get_song_entries(query)

    if not entries:
        return await interaction.followup.send("❌ No encontré ninguna canción. Inténtalo con otro nombre o enlace.")

    # Crear el panel de selección
    view = SongSelectView(entries)
    embed = discord.Embed(
        title="🎵 Resultados encontrados",
        description=f"Búsqueda: **{query}**\n\nElige una canción abajo 👇",
        color=0x1DB954
    )

    await interaction.followup.send(embed=embed, view=view)


# ==================== COMANDOS BÁSICOS (también slash) ====================
@bot.tree.command(name="pause", description="Pausa la música")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ **Pausado**")
    else:
        await interaction.response.send_message("❌ No hay nada reproduciéndose.", ephemeral=True)


@bot.tree.command(name="resume", description="Reanuda la música")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ **Reanudado**")
    else:
        await interaction.response.send_message("❌ No hay nada pausado.", ephemeral=True)


@bot.tree.command(name="stop", description="Detiene la música y desconecta")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc:
        vc.stop()
        await vc.disconnect()
        queues.pop(interaction.guild.id, None)
        await interaction.response.send_message("⏹️ **Detenido y desconectado**")
    else:
        await interaction.response.send_message("❌ No estoy en ningún canal.", ephemeral=True)


@bot.tree.command(name="skip", description="Salta a la siguiente canción")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭️ **Canción saltada**")
    else:
        await interaction.response.send_message("❌ No hay nada reproduciéndose.", ephemeral=True)


# ==================== EVENTOS ====================
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ Bot conectado como {bot.user} | {len(synced)} comandos slash sincronizados")
    except Exception as e:
        print(f"⚠️ Error sincronizando comandos: {e}")

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="/play")
    )


# ==================== ARRANQUE ====================
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta la variable DISCORD_TOKEN en Railway")
