# bot.py — patch notes for V1.4
# Two sections need updating.  Diffs are shown below; apply them to your
# existing bot.py.  Everything else stays the same.
# ─────────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH 1 — _ensure_channels_for_guild
# Add #suit-calculator creation + pinned info embed after the live-feed loop.
# ───────────────────────────────────────────────────────────────────────────────
# FIND this existing method and REPLACE its body with the version below.

    async def _ensure_channels_for_guild(self, guild: discord.Guild) -> None:
        category = discord.utils.get(guild.categories, name=self.config.category_name)
        if category is None:
            log.info("Creating category %r in %s", self.config.category_name, guild.name)
            category = await guild.create_category(self.config.category_name)

        # ── Live-feed channels (tt-information, tt-doodles) ───────────────
        for key, channel_name in self.config.feeds().items():
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel is None:
                log.info("Creating channel #%s in %s", channel_name, guild.name)
                channel = await guild.create_text_channel(
                    channel_name, category=category,
                    topic=f"Live TTR {key} feed — auto-updated by bot.",
                )
            await self._ensure_messages(guild.id, key, channel, at_least=1)

        # ── Static #suit-calculator channel ──────────────────────────────
        calc_name = self.config.channel_suit_calculator
        calc_ch   = discord.utils.get(guild.text_channels, name=calc_name)
        if calc_ch is None:
            log.info("Creating channel #%s in %s", calc_name, guild.name)
            calc_ch = await guild.create_text_channel(
                calc_name, category=category,
                topic="Cog suit disguise calculator — use /calculate here.",
            )

        await self._ensure_suit_calculator_pin(guild.id, calc_ch)
        await self._save_state()


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH 2 — add _ensure_suit_calculator_pin helper method to TTRBot
# Place this anywhere in the TTRBot class body (e.g. after _send_placeholder).
# ───────────────────────────────────────────────────────────────────────────────

    async def _ensure_suit_calculator_pin(
        self, guild_id: int, channel: discord.TextChannel
    ) -> None:
        """
        Post (or update) the pinned info embed in #suit-calculator.

        State is stored under guild → 'suit_calculator' → message_id.
        On re-setup, the existing pin is edited in place so the channel
        stays clean.
        """
        from calculate import build_suit_calculator_embed  # local import avoids circular

        embed = build_suit_calculator_embed()
        gs    = self._guild_state(guild_id)
        entry = gs.get("suit_calculator", {})
        msg_id = entry.get("message_id") if isinstance(entry, dict) else None

        # Try to edit the existing pinned message
        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed)
                log.info(
                    "[suit-calc] Updated pin %s in guild %s", msg_id, guild_id
                )
                return
            except discord.NotFound:
                log.info("[suit-calc] Old pin gone for guild %s — reposting.", guild_id)
            except discord.HTTPException as exc:
                log.warning("[suit-calc] Could not edit pin: %s", exc)

        # Post a fresh pin
        try:
            msg = await channel.send(embed=embed)
            try:
                await msg.pin(reason="Suit calculator info — LanceAQuack TTR")
            except (discord.Forbidden, discord.HTTPException) as exc:
                log.debug("[suit-calc] Could not pin: %s", exc)

            gs["suit_calculator"] = {"channel_id": channel.id, "message_id": msg.id}
            log.info(
                "[suit-calc] Posted pin %s in guild %s (#%s)",
                msg.id, guild_id, channel.name,
            )
        except Exception as exc:
            log.warning("[suit-calc] Failed to post pin in guild %s: %s", guild_id, exc)


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH 3 — .env.example  (add one line)
# ───────────────────────────────────────────────────────────────────────────────
# CHANNEL_SUIT_CALCULATOR=suit-calculator
# (optional — defaults to "suit-calculator" if omitted)
