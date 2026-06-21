from __future__ import annotations

import discord

from services import modlog as modlog_svc
from ui.embeds import error_embed, success_embed


# ── Modales ───────────────────────────────────────────────────────────────────

class BanModal(discord.ui.Modal, title="Banear usuario"):
    user_id_field = discord.ui.TextInput(
        label="ID del usuario",
        placeholder="123456789012345678",
    )
    reason_field = discord.ui.TextInput(
        label="Razón",
        placeholder="Motivo del ban",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.user_id_field.value.strip().lstrip("<@!").rstrip(">")
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("ID de usuario inválido."), ephemeral=True
            )
        reason = self.reason_field.value.strip() or "Sin razón"
        try:
            await interaction.guild.ban(discord.Object(id=uid), reason=reason, delete_message_days=0)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para banear a ese usuario."), ephemeral=True
            )
        except discord.NotFound:
            return await interaction.response.send_message(
                embed=error_embed("Usuario no encontrado."), ephemeral=True
            )
        mod = interaction.user
        modlog_svc.add_entry(
            interaction.guild_id,
            type="ban",
            target_id=uid,
            target_name=str(uid),
            moderator_id=mod.id,
            moderator_name=str(mod),
            reason=reason,
        )
        await interaction.response.send_message(
            embed=success_embed(f"Usuario `{uid}` baneado. Razón: {reason}"),
            ephemeral=True,
        )


class KickModal(discord.ui.Modal, title="Kickear usuario"):
    user_id_field = discord.ui.TextInput(
        label="ID del usuario",
        placeholder="123456789012345678",
    )
    reason_field = discord.ui.TextInput(
        label="Razón",
        placeholder="Motivo del kick",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.user_id_field.value.strip().lstrip("<@!").rstrip(">")
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("ID de usuario inválido."), ephemeral=True
            )
        reason = self.reason_field.value.strip() or "Sin razón"
        try:
            member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
            await member.kick(reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para kickear a ese usuario."), ephemeral=True
            )
        except discord.NotFound:
            return await interaction.response.send_message(
                embed=error_embed("Usuario no encontrado en el servidor."), ephemeral=True
            )
        mod = interaction.user
        modlog_svc.add_entry(
            interaction.guild_id,
            type="kick",
            target_id=uid,
            target_name=str(member),
            moderator_id=mod.id,
            moderator_name=str(mod),
            reason=reason,
        )
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} fue kickeado. Razón: {reason}"),
            ephemeral=True,
        )


class TimeoutModal(discord.ui.Modal, title="Timeout a usuario"):
    user_id_field = discord.ui.TextInput(
        label="ID del usuario",
        placeholder="123456789012345678",
    )
    duration_field = discord.ui.TextInput(
        label="Duración",
        placeholder="10m, 1h, 7d",
    )
    reason_field = discord.ui.TextInput(
        label="Razón",
        placeholder="Motivo del timeout",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from datetime import datetime, timezone
        raw = self.user_id_field.value.strip().lstrip("<@!").rstrip(">")
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("ID de usuario inválido."), ephemeral=True
            )
        delta = modlog_svc.parse_duration(self.duration_field.value)
        if delta is None:
            return await interaction.response.send_message(
                embed=error_embed("Duración inválida. Usá: `10m`, `1h`, `7d`."), ephemeral=True
            )
        reason = self.reason_field.value.strip() or "Sin razón"
        try:
            member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
            until = datetime.now(timezone.utc) + delta
            await member.timeout(until, reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("No tengo permisos para silenciar a ese usuario."), ephemeral=True
            )
        except discord.NotFound:
            return await interaction.response.send_message(
                embed=error_embed("Usuario no encontrado en el servidor."), ephemeral=True
            )
        mod = interaction.user
        modlog_svc.add_entry(
            interaction.guild_id,
            type="timeout",
            target_id=uid,
            target_name=str(member),
            moderator_id=mod.id,
            moderator_name=str(mod),
            reason=f"{self.duration_field.value} — {reason}",
        )
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} silenciado por `{self.duration_field.value}`. Razón: {reason}"),
            ephemeral=True,
        )


class WarnModal(discord.ui.Modal, title="Warn a usuario"):
    user_id_field = discord.ui.TextInput(
        label="ID del usuario",
        placeholder="123456789012345678",
    )
    reason_field = discord.ui.TextInput(
        label="Razón",
        placeholder="Motivo del warn",
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.user_id_field.value.strip().lstrip("<@!").rstrip(">")
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("ID de usuario inválido."), ephemeral=True
            )
        reason = self.reason_field.value.strip()
        try:
            member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
        except (discord.NotFound, discord.HTTPException):
            return await interaction.response.send_message(
                embed=error_embed("Usuario no encontrado en el servidor."), ephemeral=True
            )
        mod = interaction.user
        entry = modlog_svc.add_entry(
            interaction.guild_id,
            type="warn",
            target_id=uid,
            target_name=str(member),
            moderator_id=mod.id,
            moderator_name=str(mod),
            reason=reason,
        )
        count = len(modlog_svc.get_entries(interaction.guild_id, uid, entry_type="warn"))
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} recibió un warn (`{count}` total). Razón: {reason}\nID: `{entry['id'][:8]}`"),
            ephemeral=True,
        )


# ── Panel View ────────────────────────────────────────────────────────────────

class AdminPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    @discord.ui.button(label="Banear", emoji="🔨", style=discord.ButtonStyle.danger, row=0)
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Sin permisos.", ephemeral=True)
        await interaction.response.send_modal(BanModal())

    @discord.ui.button(label="Kickear", emoji="👢", style=discord.ButtonStyle.danger, row=0)
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Sin permisos.", ephemeral=True)
        await interaction.response.send_modal(KickModal())

    @discord.ui.button(label="Timeout", emoji="🔇", style=discord.ButtonStyle.secondary, row=0)
    async def timeout_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Sin permisos.", ephemeral=True)
        await interaction.response.send_modal(TimeoutModal())

    @discord.ui.button(label="Warn", emoji="⚠️", style=discord.ButtonStyle.primary, row=1)
    async def warn_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Sin permisos.", ephemeral=True)
        await interaction.response.send_modal(WarnModal())

    @discord.ui.button(label="Ver Modlog", emoji="📋", style=discord.ButtonStyle.secondary, row=1)
    async def modlog_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        entries = modlog_svc.recent_entries(interaction.guild_id, 5)
        if not entries:
            return await interaction.response.send_message(
                embed=discord.Embed(description="El modlog está vacío.", color=discord.Color.blurple()),
                ephemeral=True,
            )
        lines = []
        for e in reversed(entries):
            ts = e["timestamp"][:10]
            lines.append(f"`{ts}` **{e['type'].upper()}** — {e['target_name']} por {e['moderator_name']}: {e['reason']}")
        embed = discord.Embed(title="📋 Últimas acciones", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)
