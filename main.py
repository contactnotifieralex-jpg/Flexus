import discord
from discord import app_commands, ui
from discord.ext import commands
import yt_dlp
import asyncio
import os
from datetime import datetime

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# YT-DLP CONFIG
# ==========================================
SEARCH_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
    'extract_flat': True,   # rápido para buscar sin descargar
}

STREAM_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k',
}

def format_duration(seconds):
    if not seconds:
        return "🔴 Live"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def search_tracks(query):
    """Busca 5 resultados en YouTube."""
    is_url = query.startswith("http://") or query.startswith("https://")
    with yt_dlp.YoutubeDL(SEARCH_OPTS) as ydl:
        if is_url:
            info = ydl.extract_info(query, download=False)
            entries = [info] if 'entries' not in info else info['entries'][:5]
        else:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get('entries', [])
    results = []
    for e in entries[:5]:
        if not e:
            continue
        results.append({
            'title': e.get('title', 'Sin título'),
            'url': e.get('webpage_url') or e.get('url', ''),
            'duration': e.get('duration', 0),
            'channel': e.get('uploader') or e.get('channel', 'Desconocido'),
            'thumbnail': e.get('thumbnail', ''),
            'views': e.get('view_count', 0),
        })
    return results

def get_stream_url(webpage_url):
    """Obtiene la URL de stream de audio real."""
    with yt_dlp.YoutubeDL(STREAM_OPTS) as ydl:
        info = ydl.extract_info(webpage_url, download=False)
        return info['url'], info

# ==========================================
# ESTADO DEL PLAYER POR SERVIDOR
# ==========================================
class GuildPlayer:
    def __init__(self):
        self.queue = []
        self.current = None
        self.loop = False
        self.volume = 1.0
        self.start_time = None
        self.text_channel = None

players = {}  # guild_id -> GuildPlayer

def get_player(guild_id):
    if guild_id not in players:
        players[guild_id] = GuildPlayer()
    return players[guild_id]

# ==========================================
# AFTER CALLBACK — siguiente canción
# ==========================================
def play_next_after(guild_id, bot_ref):
    async def _next():
        gp = get_player(guild_id)
        guild = bot_ref.get_guild(guild_id)
        if not guild:
            return
        vc = guild.voice_client
        if not vc:
            return

        if gp.loop and gp.current:
            gp.queue.insert(0, gp.current)

        if not gp.queue:
            gp.current = None
            if gp.text_channel:
                embed = discord.Embed(
                    title="✅ Cola vacía",
                    description="No hay más canciones en la cola.\nUsa `/play` para añadir más música.",
                    color=0x5865F2,
                    timestamp=datetime.now()
                )
                embed.set_footer(text="FLEXUS MUSIC")
                await gp.text_channel.send(embed=embed)
            return

        track = gp.queue.pop(0)
        gp.current = track
        gp.start_time = datetime.now()

        try:
            stream_url, _ = await asyncio.get_event_loop().run_in_executor(
                None, get_stream_url, track['url']
            )
        except Exception as e:
            if gp.text_channel:
                await gp.text_channel.send(f"❌ Error al reproducir **{track['title']}**: {e}")
            await _next()
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS),
            volume=gp.volume
        )

        def after(error):
            if error:
                print(f"[FLEXUS] Error: {error}")
            asyncio.run_coroutine_threadsafe(_next(), bot_ref.loop)

        vc.play(source, after=after)

        if gp.text_channel:
            embed = now_playing_embed(track, gp)
            await gp.text_channel.send(embed=embed)

    return _next

def now_playing_embed(track, gp: GuildPlayer):
    dur = format_duration(track.get('duration', 0))
    views = track.get('views', 0)
    views_str = f"{views:,}".replace(",", ".") if views else "?"

    embed = discord.Embed(
        title="▶️  NOW PLAYING",
        description=f"## [{track['title']}]({track['url']})",
        color=0x1DB954,
        timestamp=datetime.now()
    )
    if track.get('thumbnail'):
        embed.set_image(url=track['thumbnail'])
    embed.add_field(name="⏱️ Duración", value=f"`{dur}`", inline=True)
    embed.add_field(name="📺 Canal", value=track.get('channel', '?'), inline=True)
    embed.add_field(name="👁️ Vistas", value=views_str, inline=True)
    embed.add_field(name="🔁 Loop", value="✅ Sí" if gp.loop else "❌ No", inline=True)
    embed.add_field(name="🔊 Volumen", value=f"{int(gp.volume * 100)}%", inline=True)
    embed.add_field(name="📋 En cola", value=str(len(gp.queue)), inline=True)
    embed.set_footer(text="FLEXUS MUSIC  •  Neon Audio Experience")
    return embed

# ==========================================
# SELECT MENU — elegir canción
# ==========================================
class SongSelectMenu(ui.Select):
    def __init__(self, results, voice_channel, guild_id, requester):
        self.results = results
        self.voice_channel = voice_channel
        self.guild_id = guild_id
        self.requester = requester

        options = []
        for i, track in enumerate(results):
            dur = format_duration(track.get('duration', 0))
            label = track['title'][:95]
            desc = f"{track['channel'][:40]}  •  {dur}"
            options.append(discord.SelectOption(
                label=label,
                description=desc,
                value=str(i),
                emoji=["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"][i]
            ))

        super().__init__(
            placeholder="🎵  Elige la canción que quieres escuchar...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            return await interaction.response.send_message(
                "❌ Solo quien buscó puede elegir.", ephemeral=True
            )

        await interaction.response.defer()
        idx = int(self.values[0])
        track = self.results[idx]
        gp = get_player(self.guild_id)
        gp.text_channel = interaction.channel

        # Conectar al canal de voz
        guild = interaction.guild
        vc = guild.voice_client

        try:
            if not vc:
                vc = await self.voice_channel.connect()
            elif vc.channel.id != self.voice_channel.id:
                await vc.move_to(self.voice_channel)
        except Exception as e:
            return await interaction.followup.send(f"❌ No pude conectarme al canal de voz: {e}")

        # Obtener stream URL (con loading embed)
        loading_embed = discord.Embed(
            title="⏳ Cargando canción...",
            description=f"**{track['title']}**\nObteniendo audio, espera un momento...",
            color=0xffaa00
        )
        await interaction.edit_original_response(embed=loading_embed, view=None)

        try:
            stream_url, full_info = await asyncio.get_event_loop().run_in_executor(
                None, get_stream_url, track['url']
            )
            # Actualizar con info completa
            track['duration'] = full_info.get('duration', track.get('duration', 0))
            track['views'] = full_info.get('view_count', 0)
            track['thumbnail'] = full_info.get('thumbnail', track.get('thumbnail', ''))
            track['channel'] = full_info.get('uploader') or full_info.get('channel', track.get('channel', ''))
        except Exception as e:
            return await interaction.followup.send(f"❌ Error obteniendo el audio: {e}")

        # Si ya está reproduciendo, añadir a cola
        if vc.is_playing() or vc.is_paused():
            gp.queue.append(track)
            embed = discord.Embed(
                title="📋 Añadido a la cola",
                description=f"**[{track['title']}]({track['url']})**",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            embed.add_field(name="⏱️ Duración", value=f"`{format_duration(track['duration'])}`", inline=True)
            embed.add_field(name="📋 Posición en cola", value=f"**#{len(gp.queue)}**", inline=True)
            if track.get('thumbnail'):
                embed.set_thumbnail(url=track['thumbnail'])
            embed.set_footer(text="FLEXUS MUSIC")
            await interaction.edit_original_response(embed=embed, view=None)
            return

        # Reproducir directamente
        gp.current = track
        gp.start_time = datetime.now()

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS),
            volume=gp.volume
        )

        def after(error):
            if error:
                print(f"[FLEXUS] Error playback: {error}")
            coro = play_next_after(self.guild_id, interaction.client)()
            asyncio.run_coroutine_threadsafe(coro, interaction.client.loop)

        vc.play(source, after=after)

        embed = now_playing_embed(track, gp)
        await interaction.edit_original_response(embed=embed, view=None)


class SongSelectView(ui.View):
    def __init__(self, results, voice_channel, guild_id, requester):
        super().__init__(timeout=60)
        self.add_item(SongSelectMenu(results, voice_channel, guild_id, requester))

        cancel = ui.Button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
        async def cancel_cb(interaction: discord.Interaction):
            embed = discord.Embed(title="❌ Búsqueda cancelada", color=0xff4444)
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
        cancel.callback = cancel_cb
        self.add_item(cancel)

    async def on_timeout(self):
        pass

# ==========================================
# COMANDOS
# ==========================================

@bot.tree.command(name="play", description="🎵 Busca una canción o pega un enlace de YouTube")
@app_commands.describe(busqueda="Nombre de la canción o URL de YouTube")
async def play(interaction: discord.Interaction, busqueda: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        embed = discord.Embed(
            title="❌ No estás en un canal de voz",
            description="Únete a un canal de voz primero y vuelve a intentarlo.",
            color=0xff4444
        )
        return await interaction.followup.send(embed=embed)

    # Buscar canciones
    searching_embed = discord.Embed(
        title="🔍 Buscando...",
        description=f"Buscando resultados para:\n**{busqueda}**",
        color=0xffaa00
    )
    await interaction.followup.send(embed=searching_embed)

    try:
        results = await asyncio.get_event_loop().run_in_executor(None, search_tracks, busqueda)
    except Exception as e:
        embed = discord.Embed(title="❌ Error en la búsqueda", description=str(e), color=0xff4444)
        return await interaction.edit_original_response(embed=embed)

    if not results:
        embed = discord.Embed(
            title="❌ Sin resultados",
            description=f"No encontré nada para **{busqueda}**.\nIntenta con otro nombre o un enlace directo.",
            color=0xff4444
        )
        return await interaction.edit_original_response(embed=embed)

    # Mostrar resultados
    desc = ""
    for i, track in enumerate(results):
        emoji = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"][i]
        dur = format_duration(track.get('duration', 0))
        desc += f"{emoji} **{track['title'][:60]}**\n"
        desc += f"   `{track['channel'][:35]}` · `{dur}`\n\n"

    embed = discord.Embed(
        title="🎵 Resultados de búsqueda",
        description=desc,
        color=0x1DB954,
        timestamp=datetime.now()
    )
    embed.set_footer(text="FLEXUS MUSIC  •  Selecciona una canción del menú  •  Expira en 60s")

    view = SongSelectView(
        results=results,
        voice_channel=interaction.user.voice.channel,
        guild_id=interaction.guild_id,
        requester=interaction.user
    )
    await interaction.edit_original_response(embed=embed, view=view)


@bot.tree.command(name="skip", description="⏭️ Salta la canción actual")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(
            embed=discord.Embed(title="❌ Nada reproduciéndose", color=0xff4444), ephemeral=True
        )
    vc.stop()
    await interaction.response.send_message(
        embed=discord.Embed(title="⏭️ Canción saltada", color=0x5865F2, timestamp=datetime.now())
    )


@bot.tree.command(name="pause", description="⏸️ Pausa la reproducción")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message(
            embed=discord.Embed(title="⏸️ Pausado", color=0xffaa00, timestamp=datetime.now())
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌ Nada reproduciéndose", color=0xff4444), ephemeral=True
        )


@bot.tree.command(name="resume", description="▶️ Reanuda la reproducción")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message(
            embed=discord.Embed(title="▶️ Reanudado", color=0x1DB954, timestamp=datetime.now())
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌ No hay nada pausado", color=0xff4444), ephemeral=True
        )


@bot.tree.command(name="stop", description="⏹️ Para la música y desconecta el bot")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    gp = get_player(interaction.guild_id)
    if vc:
        gp.queue.clear()
        gp.current = None
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⏹️ Detenido",
                description="Cola limpiada y bot desconectado.",
                color=0xff4444,
                timestamp=datetime.now()
            )
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌ No estoy en ningún canal", color=0xff4444), ephemeral=True
        )


@bot.tree.command(name="queue", description="📋 Muestra la cola de reproducción")
async def queue_cmd(interaction: discord.Interaction):
    gp = get_player(interaction.guild_id)
    if not gp.current and not gp.queue:
        return await interaction.response.send_message(
            embed=discord.Embed(title="📋 Cola vacía", description="Usa `/play` para añadir música.", color=0x5865F2)
        )

    desc = ""
    if gp.current:
        dur = format_duration(gp.current.get('duration', 0))
        desc += f"**▶️ Sonando ahora:**\n[{gp.current['title'][:55]}]({gp.current['url']}) `{dur}`\n\n"

    if gp.queue:
        desc += "**📋 Siguiente en cola:**\n"
        for i, t in enumerate(gp.queue[:10]):
            dur = format_duration(t.get('duration', 0))
            desc += f"**{i+1}.** {t['title'][:50]} `{dur}`\n"
        if len(gp.queue) > 10:
            desc += f"\n*...y {len(gp.queue)-10} canciones más*"

    embed = discord.Embed(title="📋 Cola de reproducción", description=desc, color=0x5865F2, timestamp=datetime.now())
    embed.set_footer(text=f"FLEXUS MUSIC  •  {len(gp.queue)} canciones en cola  •  Loop: {'✅' if gp.loop else '❌'}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="nowplaying", description="🎵 Muestra la canción que está sonando")
async def nowplaying(interaction: discord.Interaction):
    gp = get_player(interaction.guild_id)
    if not gp.current:
        return await interaction.response.send_message(
            embed=discord.Embed(title="❌ Nada reproduciéndose", color=0xff4444), ephemeral=True
        )
    await interaction.response.send_message(embed=now_playing_embed(gp.current, gp))


@bot.tree.command(name="volume", description="🔊 Ajusta el volumen (1-200)")
@app_commands.describe(nivel="Nivel de volumen entre 1 y 200")
async def volume(interaction: discord.Interaction, nivel: int):
    if not 1 <= nivel <= 200:
        return await interaction.response.send_message(
            embed=discord.Embed(title="❌ Volumen inválido", description="Elige entre 1 y 200.", color=0xff4444), ephemeral=True
        )
    gp = get_player(interaction.guild_id)
    gp.volume = nivel / 100
    vc = interaction.guild.voice_client
    if vc and vc.source:
        vc.source.volume = gp.volume
    bar_filled = int((nivel / 200) * 20)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    embed = discord.Embed(
        title="🔊 Volumen ajustado",
        description=f"`{bar}` **{nivel}%**",
        color=0x1DB954,
        timestamp=datetime.now()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="loop", description="🔁 Activa o desactiva el modo loop")
async def loop(interaction: discord.Interaction):
    gp = get_player(interaction.guild_id)
    gp.loop = not gp.loop
    status = "✅ Activado" if gp.loop else "❌ Desactivado"
    embed = discord.Embed(
        title=f"🔁 Loop {status}",
        description="La canción actual se repetirá." if gp.loop else "La canción no se repetirá.",
        color=0x1DB954 if gp.loop else 0xff4444,
        timestamp=datetime.now()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clear", description="🗑️ Limpia la cola de reproducción")
async def clear(interaction: discord.Interaction):
    gp = get_player(interaction.guild_id)
    count = len(gp.queue)
    gp.queue.clear()
    embed = discord.Embed(
        title="🗑️ Cola limpiada",
        description=f"Se eliminaron **{count}** canciones de la cola.",
        color=0xffaa00,
        timestamp=datetime.now()
    )
    await interaction.response.send_message(embed=embed)


# ==========================================
# EVENTOS
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} conectado — FLEXUS MUSIC listo")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="/play  •  FLEXUS"
    ))

@bot.event
async def on_voice_state_update(member, before, after):
    """Desconectar si el bot se queda solo."""
    if member.bot:
        return
    guild = member.guild
    vc = guild.voice_client
    if vc and len(vc.channel.members) == 1:
        await asyncio.sleep(30)
        vc = guild.voice_client
        if vc and len(vc.channel.members) == 1:
            gp = get_player(guild.id)
            gp.queue.clear()
            gp.current = None
            await vc.disconnect()

# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN en las variables de entorno.")
