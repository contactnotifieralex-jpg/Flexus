import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import os
from datetime import datetime, timedelta

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# BASE DE DATOS EN MEMORIA
# ==========================================
# ping_rules[guild_id][victim_id] = {"action": "warn"/"mute"/"ban"/"nothing", "protected_users": [id1, id2]}
ping_rules = {}
# warnings[guild_id][user_id] = count
warnings = {}

# ==========================================
# HELPERS
# ==========================================
def get_ping_rule(guild_id, victim_id):
    return ping_rules.get(guild_id, {}).get(victim_id)

def add_warning(guild_id, user_id):
    if guild_id not in warnings:
        warnings[guild_id] = {}
    warnings[guild_id][user_id] = warnings[guild_id].get(user_id, 0) + 1
    return warnings[guild_id][user_id]

# ==========================================
# PANEL 1 - ELEGIR CASTIGO
# ==========================================
class PunishmentSelect(ui.Select):
    def __init__(self, setup_state):
        self.setup_state = setup_state
        options = [
            discord.SelectOption(label="Nada", value="nothing", emoji="✅", description="No hacer nada cuando te hagan ping"),
            discord.SelectOption(label="Advertencia", value="warn", emoji="⚠️", description="El usuario recibe una advertencia"),
            discord.SelectOption(label="Silenciar 5 min", value="mute", emoji="🔇", description="El usuario es silenciado 5 minutos"),
            discord.SelectOption(label="Ban permanente", value="ban", emoji="🔨", description="El usuario es baneado del servidor"),
        ]
        super().__init__(placeholder="Elige el castigo para quien te haga ping...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.setup_state["action"] = self.values[0]
        labels = {"nothing": "✅ Nada", "warn": "⚠️ Advertencia", "mute": "🔇 Silenciado 5 min", "ban": "🔨 Ban permanente"}
        embed = discord.Embed(
            title="⚙️ SETUP — Paso 2 de 2",
            description=(
                f"**Castigo seleccionado:** {labels[self.values[0]]}\n\n"
                "Ahora menciona en el cuadro de texto a los usuarios que quieres **proteger**.\n"
                "Escribe sus menciones en el chat y pulsa **Confirmar**.\n\n"
                "Ejemplo: `@pepe @ana @luis`"
            ),
            color=0x5865F2
        )
        embed.set_footer(text="FLEXUS GUARD • Sistema de protección de pings")
        view = ProtectedUsersView(self.setup_state, interaction.user.id, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=view)

class PunishmentView(ui.View):
    def __init__(self, setup_state):
        super().__init__(timeout=120)
        self.add_item(PunishmentSelect(setup_state))

    async def on_timeout(self):
        pass

# ==========================================
# PANEL 2 - ELEGIR USUARIOS PROTEGIDOS
# ==========================================
class ProtectedUsersView(ui.View):
    def __init__(self, setup_state, owner_id, guild):
        super().__init__(timeout=120)
        self.setup_state = setup_state
        self.owner_id = owner_id
        self.guild = guild

    @ui.button(label="Confirmar selección", style=discord.ButtonStyle.success, emoji="✔️")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Solo quien ejecutó /setup puede confirmar.", ephemeral=True)

        # Buscar menciones en los últimos mensajes del canal
        protected = []
        async for msg in interaction.channel.history(limit=10):
            if msg.author.id == self.owner_id and msg.mentions:
                for member in msg.mentions:
                    if member.id not in protected:
                        protected.append(member.id)
                break

        action = self.setup_state.get("action", "nothing")
        victim_id = self.owner_id

        if interaction.guild.id not in ping_rules:
            ping_rules[interaction.guild.id] = {}

        ping_rules[interaction.guild.id][victim_id] = {
            "action": action,
            "protected_users": protected
        }

        labels = {"nothing": "✅ Nada", "warn": "⚠️ Advertencia", "mute": "🔇 Silenciado 5 min", "ban": "🔨 Ban permanente"}
        protected_mentions = " ".join([f"<@{uid}>" for uid in protected]) if protected else "*(todos los usuarios)*"

        embed = discord.Embed(
            title="✅ Protección activada",
            color=0x00ff88,
            timestamp=datetime.now()
        )
        embed.add_field(name="🛡️ Usuario protegido", value=f"<@{victim_id}>", inline=True)
        embed.add_field(name="⚡ Castigo", value=labels[action], inline=True)
        embed.add_field(name="👥 Se aplica a", value=protected_mentions, inline=False)
        embed.set_footer(text="FLEXUS GUARD • Protección activa")
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="Proteger de TODOS", style=discord.ButtonStyle.danger, emoji="🌐")
    async def protect_all(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Solo quien ejecutó /setup puede confirmar.", ephemeral=True)

        action = self.setup_state.get("action", "nothing")
        victim_id = self.owner_id

        if interaction.guild.id not in ping_rules:
            ping_rules[interaction.guild.id] = {}

        # Lista vacía = aplica a todos
        ping_rules[interaction.guild.id][victim_id] = {
            "action": action,
            "protected_users": []
        }

        labels = {"nothing": "✅ Nada", "warn": "⚠️ Advertencia", "mute": "🔇 Silenciado 5 min", "ban": "🔨 Ban permanente"}

        embed = discord.Embed(
            title="✅ Protección total activada",
            description=f"**Cualquier usuario** que te haga ping recibirá: **{labels[action]}**",
            color=0xff4444,
            timestamp=datetime.now()
        )
        embed.set_footer(text="FLEXUS GUARD • Protección total activa")
        await interaction.response.edit_message(embed=embed, view=None)

# ==========================================
# EVENTO — DETECTAR PINGS
# ==========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    guild_id = message.guild.id if message.guild else None
    if guild_id and message.mentions:
        guild_rules = ping_rules.get(guild_id, {})
        for victim in message.mentions:
            if victim.id == message.author.id:
                continue  # ignorar auto-pings
            rule = guild_rules.get(victim.id)
            if not rule:
                continue

            protected = rule["protected_users"]
            # Si la lista está vacía protege de todos, si tiene IDs solo de esos
            if protected and message.author.id not in protected:
                continue

            action = rule["action"]
            pinger = message.author

            if action == "nothing":
                pass

            elif action == "warn":
                count = add_warning(guild_id, pinger.id)
                try:
                    embed = discord.Embed(
                        title="⚠️ ADVERTENCIA",
                        description=(
                            f"{pinger.mention} has recibido una advertencia por hacer ping a {victim.mention}.\n"
                            f"**Total de advertencias:** {count}"
                        ),
                        color=0xffaa00,
                        timestamp=datetime.now()
                    )
                    await message.channel.send(embed=embed)
                except Exception as e:
                    print(f"Error warn: {e}")

            elif action == "mute":
                try:
                    until = datetime.utcnow() + timedelta(minutes=5)
                    await pinger.timeout(until, reason=f"Ping no autorizado a {victim.display_name}")
                    embed = discord.Embed(
                        title="🔇 SILENCIADO",
                        description=f"{pinger.mention} ha sido silenciado **5 minutos** por hacer ping a {victim.mention}.",
                        color=0xff6600,
                        timestamp=datetime.now()
                    )
                    await message.channel.send(embed=embed)
                except discord.Forbidden:
                    await message.channel.send("❌ No tengo permisos para silenciar a ese usuario.")
                except Exception as e:
                    print(f"Error mute: {e}")

            elif action == "ban":
                try:
                    embed = discord.Embed(
                        title="🔨 BAN",
                        description=f"{pinger.mention} ha sido **baneado** por hacer ping a {victim.mention}.",
                        color=0xff0000,
                        timestamp=datetime.now()
                    )
                    await message.channel.send(embed=embed)
                    await asyncio.sleep(1)
                    await pinger.ban(reason=f"Ping no autorizado a {victim.display_name}")
                except discord.Forbidden:
                    await message.channel.send("❌ No tengo permisos para banear a ese usuario.")
                except Exception as e:
                    print(f"Error ban: {e}")

    await bot.process_commands(message)

# ==========================================
# COMANDO PRINCIPAL — /setup
# ==========================================
@bot.tree.command(name="setup", description="🛡️ Configura la protección de pings para ti")
async def setup(interaction: discord.Interaction):
    setup_state = {}
    embed = discord.Embed(
        title="⚙️ SETUP — Paso 1 de 2",
        description=(
            "**Bienvenido al sistema de protección de pings.**\n\n"
            "Cuando alguien te mencione (`@tú`), el bot ejecutará automáticamente el castigo que elijas.\n\n"
            "**Paso 1:** Selecciona qué castigo quieres aplicar:"
        ),
        color=0x5865F2,
        timestamp=datetime.now()
    )
    embed.add_field(name="✅ Nada", value="No pasa nada", inline=True)
    embed.add_field(name="⚠️ Advertencia", value="Aviso público", inline=True)
    embed.add_field(name="🔇 Silenciar 5 min", value="Timeout automático", inline=True)
    embed.add_field(name="🔨 Ban", value="Ban permanente", inline=True)
    embed.set_footer(text="FLEXUS GUARD • Configura tu protección")
    view = PunishmentView(setup_state)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==========================================
# COMANDO — /miproteccion
# ==========================================
@bot.tree.command(name="miproteccion", description="🔍 Ver tu configuración de protección actual")
async def miproteccion(interaction: discord.Interaction):
    rule = ping_rules.get(interaction.guild_id, {}).get(interaction.user.id)
    if not rule:
        return await interaction.response.send_message(
            embed=discord.Embed(title="❌ Sin protección", description="No tienes ninguna protección configurada. Usa `/setup`.", color=0xff4444),
            ephemeral=True
        )
    labels = {"nothing": "✅ Nada", "warn": "⚠️ Advertencia", "mute": "🔇 Silenciado 5 min", "ban": "🔨 Ban permanente"}
    protected = rule["protected_users"]
    protected_text = " ".join([f"<@{uid}>" for uid in protected]) if protected else "🌐 Todos los usuarios"
    embed = discord.Embed(title="🛡️ Tu protección activa", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="⚡ Castigo configurado", value=labels[rule["action"]], inline=True)
    embed.add_field(name="👥 Aplica a", value=protected_text, inline=False)
    embed.set_footer(text="FLEXUS GUARD")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# COMANDO — /quitarproteccion
# ==========================================
@bot.tree.command(name="quitarproteccion", description="🗑️ Elimina tu protección de pings")
async def quitarproteccion(interaction: discord.Interaction):
    if interaction.guild_id in ping_rules and interaction.user.id in ping_rules[interaction.guild_id]:
        del ping_rules[interaction.guild_id][interaction.user.id]
        await interaction.response.send_message(
            embed=discord.Embed(title="🗑️ Protección eliminada", description="Tu protección ha sido desactivada.", color=0xffaa00),
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(title="❌ Sin protección", description="No tenías ninguna protección activa.", color=0xff4444),
            ephemeral=True
        )

# ==========================================
# COMANDO — /advertencias
# ==========================================
@bot.tree.command(name="advertencias", description="📋 Ver las advertencias de un usuario")
@app_commands.describe(usuario="Usuario del que ver las advertencias")
async def advertencias(interaction: discord.Interaction, usuario: discord.Member):
    count = warnings.get(interaction.guild_id, {}).get(usuario.id, 0)
    embed = discord.Embed(
        title="📋 Advertencias",
        description=f"{usuario.mention} tiene **{count}** advertencia(s).",
        color=0xffaa00 if count > 0 else 0x00ff88,
        timestamp=datetime.now()
    )
    await interaction.response.send_message(embed=embed)

# ==========================================
# COMANDO — /limpiaradvertencias
# ==========================================
@bot.tree.command(name="limpiaradvertencias", description="🧹 Limpia las advertencias de un usuario (solo admins)")
@app_commands.describe(usuario="Usuario al que limpiar advertencias")
async def limpiaradvertencias(interaction: discord.Interaction, usuario: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo los administradores pueden usar este comando.", ephemeral=True)
    if interaction.guild_id in warnings and usuario.id in warnings[interaction.guild_id]:
        warnings[interaction.guild_id][usuario.id] = 0
    embed = discord.Embed(
        title="🧹 Advertencias limpiadas",
        description=f"Las advertencias de {usuario.mention} han sido reiniciadas a 0.",
        color=0x00ff88,
        timestamp=datetime.now()
    )
    await interaction.response.send_message(embed=embed)

# ==========================================
# COMANDO — /userinfo
# ==========================================
@bot.tree.command(name="userinfo", description="👤 Información detallada de un usuario")
@app_commands.describe(usuario="Usuario del que ver la información")
async def userinfo(interaction: discord.Interaction, usuario: discord.Member = None):
    usuario = usuario or interaction.user
    roles = [r.mention for r in usuario.roles if r.name != "@everyone"]
    embed = discord.Embed(title=f"👤 {usuario.display_name}", color=usuario.color, timestamp=datetime.now())
    embed.set_thumbnail(url=usuario.display_avatar.url)
    embed.add_field(name="🆔 ID", value=f"`{usuario.id}`", inline=True)
    embed.add_field(name="📅 Cuenta creada", value=f"<t:{int(usuario.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="📥 Entró al servidor", value=f"<t:{int(usuario.joined_at.timestamp())}:R>", inline=True)
    embed.add_field(name="🤖 Bot", value="Sí" if usuario.bot else "No", inline=True)
    embed.add_field(name=f"🎭 Roles ({len(roles)})", value=" ".join(roles[:5]) if roles else "Ninguno", inline=False)
    warns = warnings.get(interaction.guild_id, {}).get(usuario.id, 0)
    embed.add_field(name="⚠️ Advertencias", value=str(warns), inline=True)
    rule = ping_rules.get(interaction.guild_id, {}).get(usuario.id)
    embed.add_field(name="🛡️ Protección", value="✅ Activa" if rule else "❌ Inactiva", inline=True)
    embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

# ==========================================
# COMANDO — /serverinfo
# ==========================================
@bot.tree.command(name="serverinfo", description="🏠 Información del servidor")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"🏠 {g.name}", color=0x5865F2, timestamp=datetime.now())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="🆔 ID", value=f"`{g.id}`", inline=True)
    embed.add_field(name="👑 Dueño", value=f"<@{g.owner_id}>", inline=True)
    embed.add_field(name="📅 Creado", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="👥 Miembros", value=str(g.member_count), inline=True)
    embed.add_field(name="💬 Canales", value=str(len(g.channels)), inline=True)
    embed.add_field(name="🎭 Roles", value=str(len(g.roles)), inline=True)
    embed.add_field(name="😀 Emojis", value=str(len(g.emojis)), inline=True)
    embed.add_field(name="🔒 Verificación", value=str(g.verification_level).capitalize(), inline=True)
    protecciones = sum(1 for v in ping_rules.get(g.id, {}).values() if v)
    embed.add_field(name="🛡️ Protecciones activas", value=str(protecciones), inline=True)
    await interaction.response.send_message(embed=embed)

# ==========================================
# COMANDO — /silenciar (admin)
# ==========================================
@bot.tree.command(name="silenciar", description="🔇 Silencia a un usuario (solo admins)")
@app_commands.describe(usuario="Usuario a silenciar", minutos="Duración en minutos", razon="Razón del silencio")
async def silenciar(interaction: discord.Interaction, usuario: discord.Member, minutos: int = 5, razon: str = "Sin razón especificada"):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("❌ No tienes permisos para silenciar.", ephemeral=True)
    try:
        until = datetime.utcnow() + timedelta(minutes=minutos)
        await usuario.timeout(until, reason=razon)
        embed = discord.Embed(
            title="🔇 Usuario silenciado",
            color=0xff6600,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Usuario", value=usuario.mention, inline=True)
        embed.add_field(name="⏱️ Duración", value=f"{minutos} minutos", inline=True)
        embed.add_field(name="📝 Razón", value=razon, inline=False)
        embed.add_field(name="🛡️ Moderador", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ No puedo silenciar a ese usuario.", ephemeral=True)

# ==========================================
# COMANDO — /dessilenciar (admin)
# ==========================================
@bot.tree.command(name="dessilenciar", description="🔊 Quita el silencio a un usuario (solo admins)")
@app_commands.describe(usuario="Usuario a dessilenciar")
async def dessilenciar(interaction: discord.Interaction, usuario: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)
    try:
        await usuario.timeout(None)
        embed = discord.Embed(
            title="🔊 Silencio retirado",
            description=f"{usuario.mention} ya puede hablar de nuevo.",
            color=0x00ff88,
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ No puedo modificar a ese usuario.", ephemeral=True)

# ==========================================
# COMANDO — /protecciones (admin)
# ==========================================
@bot.tree.command(name="protecciones", description="📊 Lista todas las protecciones activas del servidor (admins)")
async def protecciones(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)
    guild_rules = ping_rules.get(interaction.guild_id, {})
    if not guild_rules:
        return await interaction.response.send_message(
            embed=discord.Embed(title="📊 Protecciones", description="No hay protecciones activas.", color=0xffaa00),
            ephemeral=True
        )
    labels = {"nothing": "✅ Nada", "warn": "⚠️ Advertir", "mute": "🔇 Silenciar", "ban": "🔨 Ban"}
    desc = ""
    for victim_id, rule in guild_rules.items():
        protected = rule["protected_users"]
        prot_text = "Todos" if not protected else f"{len(protected)} usuario(s)"
        desc += f"<@{victim_id}> → **{labels[rule['action']]}** · Aplica a: {prot_text}\n"
    embed = discord.Embed(title="📊 Protecciones activas", description=desc, color=0x5865F2, timestamp=datetime.now())
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# EVENTO ON_READY
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} conectado y listo.")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="los pings del servidor 🛡️"
    ))

# ==========================================
# INICIO
# ==========================================
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Falta DISCORD_TOKEN")
