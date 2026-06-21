from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from services import modlog as modlog_svc
from services import permissions as perms
from ui.admin_view import AdminPanelView
from ui.embeds import error_embed, safe_reply, success_embed


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Moderación ────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Banea a un usuario del servidor")
    @app_commands.describe(usuario="El miembro a banear", razon="Razón del ban", delete_days="Días de mensajes a borrar (0-7)")
    async def ban(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str = "Sin razón",
        delete_days: int = 0,
    ) -> None:
        perms.check(interaction, "ban")
        if delete_days not in range(8):
            return await interaction.response.send_message(
                embed=error_embed("delete_days debe estar entre 0 y 7."), ephemeral=True
            )
        try:
            await interaction.guild.ban(usuario, reason=razon, delete_message_days=delete_days)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para banear a ese usuario."), ephemeral=True
            )
        modlog_svc.add_entry(
            interaction.guild_id,
            type="ban",
            target_id=usuario.id,
            target_name=str(usuario),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            reason=razon,
        )
        await interaction.response.send_message(
            embed=success_embed(f"{usuario.mention} fue baneado. Razón: {razon}")
        )

    @app_commands.command(name="unban", description="Desbanea a un usuario por su ID")
    @app_commands.describe(user_id="ID del usuario a desbanear", razon="Razón del unban")
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        razon: str = "Sin razón",
    ) -> None:
        perms.check(interaction, "unban")
        try:
            uid = int(user_id.strip())
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("ID inválido. Ingresá solo números."), ephemeral=True
            )
        try:
            await interaction.guild.unban(discord.Object(id=uid), reason=razon)
        except discord.NotFound:
            return await interaction.response.send_message(
                embed=error_embed("Ese usuario no está baneado."), ephemeral=True
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para desbanear."), ephemeral=True
            )
        modlog_svc.add_entry(
            interaction.guild_id,
            type="unban",
            target_id=uid,
            target_name=str(uid),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            reason=razon,
        )
        await interaction.response.send_message(
            embed=success_embed(f"Usuario `{uid}` desbaneado. Razón: {razon}")
        )

    @app_commands.command(name="kick", description="Expulsa a un usuario del servidor")
    @app_commands.describe(usuario="El miembro a kickear", razon="Razón del kick")
    async def kick(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str = "Sin razón",
    ) -> None:
        perms.check(interaction, "kick")
        try:
            await usuario.kick(reason=razon)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para kickear a ese usuario."), ephemeral=True
            )
        modlog_svc.add_entry(
            interaction.guild_id,
            type="kick",
            target_id=usuario.id,
            target_name=str(usuario),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            reason=razon,
        )
        await interaction.response.send_message(
            embed=success_embed(f"{usuario.mention} fue kickeado. Razón: {razon}")
        )

    @app_commands.command(name="timeout", description="Silencia a un usuario temporalmente")
    @app_commands.describe(usuario="El miembro a silenciar", duracion="Duración: 10m, 1h, 7d", razon="Razón")
    async def timeout_cmd(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        duracion: str,
        razon: str = "Sin razón",
    ) -> None:
        perms.check(interaction, "timeout")
        delta = modlog_svc.parse_duration(duracion)
        if delta is None:
            return await interaction.response.send_message(
                embed=error_embed("Duración inválida. Usá: `10m`, `1h`, `7d`."), ephemeral=True
            )
        try:
            until = datetime.now(timezone.utc) + delta
            await usuario.timeout(until, reason=razon)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para silenciar a ese usuario."), ephemeral=True
            )
        modlog_svc.add_entry(
            interaction.guild_id,
            type="timeout",
            target_id=usuario.id,
            target_name=str(usuario),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            reason=f"{duracion} — {razon}",
        )
        await interaction.response.send_message(
            embed=success_embed(f"{usuario.mention} silenciado por `{duracion}`. Razón: {razon}")
        )

    @app_commands.command(name="warn", description="Agrega un aviso al historial de un usuario")
    @app_commands.describe(usuario="El miembro a advertir", razon="Razón del warn")
    async def warn(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        razon: str,
    ) -> None:
        perms.check(interaction, "warn")
        entry = modlog_svc.add_entry(
            interaction.guild_id,
            type="warn",
            target_id=usuario.id,
            target_name=str(usuario),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            reason=razon,
        )
        count = len(modlog_svc.get_entries(interaction.guild_id, usuario.id, entry_type="warn"))
        await interaction.response.send_message(
            embed=success_embed(
                f"{usuario.mention} recibió un warn (`{count}` total). Razón: {razon}\nID: `{entry['id'][:8]}`"
            )
        )

    @app_commands.command(name="warns", description="Muestra el historial de warns de un usuario")
    @app_commands.describe(usuario="El miembro a consultar")
    async def warns(self, interaction: discord.Interaction, usuario: discord.Member) -> None:
        perms.check(interaction, "warns")
        entries = modlog_svc.get_entries(interaction.guild_id, usuario.id, entry_type="warn")
        embed = discord.Embed(
            title=f"⚠️ Warns de {usuario.display_name}",
            color=discord.Color.orange() if entries else discord.Color.green(),
        )
        if not entries:
            embed.description = "Sin advertencias registradas."
        else:
            lines = []
            for e in entries:
                ts = e["timestamp"][:10]
                lines.append(f"`{e['id'][:8]}` `{ts}` **{e['type'].upper()}** — {e['reason']} _(por {e['moderator_name']})_")
            embed.description = "\n".join(lines)
        embed.set_thumbnail(url=usuario.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unwarn", description="Elimina un warn del historial")
    @app_commands.describe(usuario="El miembro", warn_id="ID del warn (los primeros 8 caracteres)")
    async def unwarn(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        warn_id: str,
    ) -> None:
        perms.check(interaction, "unwarn")
        entries = modlog_svc.get_entries(interaction.guild_id, usuario.id, entry_type="warn")
        full_id = next((e["id"] for e in entries if e["id"].startswith(warn_id.strip())), None)
        if full_id is None:
            return await interaction.response.send_message(
                embed=error_embed(f"No se encontró un warn con ID `{warn_id}` para ese usuario."),
                ephemeral=True,
            )
        modlog_svc.remove_entry(interaction.guild_id, full_id)
        await interaction.response.send_message(
            embed=success_embed(f"Warn `{warn_id}` eliminado del historial de {usuario.mention}.")
        )

    # ── Roles ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="role-give", description="Asigna un rol a un usuario")
    @app_commands.describe(usuario="El miembro", rol="El rol a asignar")
    async def role_give(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        rol: discord.Role,
    ) -> None:
        perms.check(interaction, "role-give")
        if rol in usuario.roles:
            return await interaction.response.send_message(
                embed=error_embed(f"{usuario.mention} ya tiene el rol {rol.mention}."), ephemeral=True
            )
        try:
            await usuario.add_roles(rol, reason=f"Por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para asignar ese rol."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success_embed(f"Rol {rol.mention} asignado a {usuario.mention}.")
        )

    @app_commands.command(name="role-remove", description="Quita un rol a un usuario")
    @app_commands.describe(usuario="El miembro", rol="El rol a quitar")
    async def role_remove(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        rol: discord.Role,
    ) -> None:
        perms.check(interaction, "role-remove")
        if rol not in usuario.roles:
            return await interaction.response.send_message(
                embed=error_embed(f"{usuario.mention} no tiene el rol {rol.mention}."), ephemeral=True
            )
        try:
            await usuario.remove_roles(rol, reason=f"Por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para quitar ese rol."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success_embed(f"Rol {rol.mention} quitado a {usuario.mention}.")
        )

    @app_commands.command(name="role-info", description="Muestra información de un rol")
    @app_commands.describe(rol="El rol a consultar")
    async def role_info(self, interaction: discord.Interaction, rol: discord.Role) -> None:
        perms.check(interaction, "role-info")
        embed = discord.Embed(
            title=f"🎭 {rol.name}",
            color=rol.color,
        )
        embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
        embed.add_field(name="Color", value=str(rol.color), inline=True)
        embed.add_field(name="Posición", value=str(rol.position), inline=True)
        embed.add_field(name="Mencionable", value="Sí" if rol.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted", value="Sí" if rol.hoist else "No", inline=True)
        embed.add_field(name="Miembros", value=str(len(rol.members)), inline=True)
        created = discord.utils.format_dt(rol.created_at, "D")
        embed.add_field(name="Creado", value=created, inline=True)
        key_perms = [
            name.replace("_", " ").title()
            for name, val in rol.permissions
            if val and name in (
                "administrator", "manage_guild", "manage_channels", "manage_roles",
                "kick_members", "ban_members", "manage_messages", "mention_everyone",
            )
        ]
        embed.add_field(
            name="Permisos clave",
            value=", ".join(key_perms) if key_perms else "Ninguno destacado",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # ── Canales ───────────────────────────────────────────────────────────────

    @app_commands.command(name="channel-lock", description="Bloquea escritura en un canal para @everyone")
    @app_commands.describe(canal="El canal a bloquear")
    async def channel_lock(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        perms.check(interaction, "channel-lock")
        everyone = interaction.guild.default_role
        try:
            await canal.set_permissions(everyone, send_messages=False, reason=f"Lock por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para modificar ese canal."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success_embed(f"🔒 {canal.mention} bloqueado.")
        )

    @app_commands.command(name="channel-unlock", description="Desbloquea escritura en un canal para @everyone")
    @app_commands.describe(canal="El canal a desbloquear")
    async def channel_unlock(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ) -> None:
        perms.check(interaction, "channel-unlock")
        everyone = interaction.guild.default_role
        try:
            await canal.set_permissions(everyone, send_messages=None, reason=f"Unlock por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para modificar ese canal."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=success_embed(f"🔓 {canal.mention} desbloqueado.")
        )

    @app_commands.command(name="channel-slowmode", description="Activa o desactiva el modo lento en un canal")
    @app_commands.describe(canal="El canal", segundos="Segundos entre mensajes (0 = desactivar, máx 21600)")
    async def channel_slowmode(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        segundos: int,
    ) -> None:
        perms.check(interaction, "channel-slowmode")
        if not 0 <= segundos <= 21600:
            return await interaction.response.send_message(
                embed=error_embed("El valor debe estar entre 0 y 21600 segundos."), ephemeral=True
            )
        try:
            await canal.edit(slowmode_delay=segundos, reason=f"Slowmode por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para modificar ese canal."), ephemeral=True
            )
        msg = f"⏱️ Modo lento en {canal.mention}: `{segundos}s`." if segundos else f"✅ Modo lento desactivado en {canal.mention}."
        await interaction.response.send_message(embed=success_embed(msg))

    # ── Panel ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="adminpanel", description="Panel interactivo de administración")
    async def adminpanel(self, interaction: discord.Interaction) -> None:
        perms.check(interaction, "adminpanel")
        entries = modlog_svc.recent_entries(interaction.guild_id, 5)
        embed = discord.Embed(
            title="🛡️ Panel de Administración",
            color=discord.Color.dark_red(),
        )
        if entries:
            lines = []
            for e in reversed(entries):
                ts = e["timestamp"][:10]
                lines.append(f"`{ts}` **{e['type'].upper()}** — {e['target_name']}: {e['reason']}")
            embed.add_field(name="Últimas acciones", value="\n".join(lines), inline=False)
        else:
            embed.description = "Sin acciones registradas aún."
        embed.set_footer(text=f"Servidor: {interaction.guild.name}")
        view = AdminPanelView()
        await interaction.response.send_message(embed=embed, view=view)

    # ── Error handler ─────────────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
