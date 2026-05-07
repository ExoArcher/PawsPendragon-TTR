# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.doodlesearch")


_DOODLE_SEARCH_THREAD_RE = re.compile(r"'s Search \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$")


async def cleanup_doodle_search_threads(bot: TTRBot, guild: discord.Guild) -> int:
    """Delete orphaned doodle-search result threads in this guild's doodles channel."""
    guild_state = bot._guild_state(guild.id)
    doodles_entry = guild_state.get("doodles", {})
    channel: discord.TextChannel | None = None
    channel_id = 0
    if isinstance(doodles_entry, dict):
        try:
            channel_id = int(doodles_entry.get("channel_id", 0))
        except (TypeError, ValueError):
            pass
    if channel_id:
        ch = bot.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel):
            channel = ch
    if channel is None:
        channel_name = bot.config.feeds().get("doodles", bot.config.channel_doodles)
        channel = discord.utils.get(guild.text_channels, name=channel_name)

    if not isinstance(channel, discord.TextChannel):
        return 0

    deleted = 0

    # Use guild.active_threads() (REST API) instead of channel.threads (local cache only)
    try:
        active_threads = [t for t in await guild.active_threads() if t.parent_id == channel.id]
    except (discord.Forbidden, discord.HTTPException):
        active_threads = list(channel.threads)

    for thread in active_threads:
        if _DOODLE_SEARCH_THREAD_RE.search(thread.name):
            try:
                await thread.delete()
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass

    try:
        async for thread in channel.archived_threads(limit=100):
            if _DOODLE_SEARCH_THREAD_RE.search(thread.name):
                try:
                    await thread.delete()
                    deleted += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
    except (discord.Forbidden, discord.HTTPException):
        pass

    if deleted:
        log.info("[%s][%d] Cleaned %d orphaned doodle-search thread(s).",
                 guild.name, guild.id, deleted)
    return deleted


def _norm_search_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _trait_similarity(requested: str, actual: str) -> float:
    requested_norm = _norm_search_text(requested)
    actual_norm = _norm_search_text(actual)
    if not requested_norm or not actual_norm:
        return 0.0
    if requested_norm == actual_norm:
        return 1.0
    if requested_norm in actual_norm or actual_norm in requested_norm:
        return 0.95
    return SequenceMatcher(None, requested_norm, actual_norm).ratio()


def _trait_search_score(search_traits: list[str], doodle_traits: list[str]) -> tuple[int, float]:
    if not search_traits:
        return 0, 0.0

    best_scores = [
        max((_trait_similarity(search_trait, trait) for trait in doodle_traits), default=0.0)
        for search_trait in search_traits
    ]
    matched_count = sum(1 for score in best_scores if score >= 0.82)
    average_score = sum(best_scores) / len(best_scores)
    return matched_count, average_score


def _cost_as_int(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


async def _resolve_doodles_channel(
    bot: TTRBot,
    interaction: discord.Interaction,
) -> discord.TextChannel | None:
    """Return the configured #tt-doodles channel for this guild, if available."""
    guild = interaction.guild
    if guild is None:
        return None

    guild_state = bot._guild_state(guild.id)
    doodles_entry = guild_state.get("doodles", {})
    channel_id = 0
    if isinstance(doodles_entry, dict):
        try:
            channel_id = int(doodles_entry.get("channel_id", 0))
        except (TypeError, ValueError):
            channel_id = 0

    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if isinstance(channel, discord.TextChannel):
            return channel

    channel_name = bot.config.feeds().get("doodles", bot.config.channel_doodles)
    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if isinstance(channel, discord.TextChannel):
        return channel

    return None


def register_doodlesearch(bot: TTRBot) -> None:
    @bot.tree.command(
        name="doodlesearch",
        description="Search for specific doodles by traits or location.",
    )
    @app_commands.describe(
        trait1="Filter by a specific trait (e.g., 'Rarely Tired', 'Always Playful')",
        trait2="Filter by a second trait",
        trait3="Filter by a third trait",
        trait4="Filter by a fourth trait",
        playground="Filter by a playground (e.g., 'Donald\\'s Dreamland')",
        district="Filter by a district (e.g., 'Splat Summit')",
        cost="Filter by exact jellybean cost",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def doodlesearch(
        interaction: discord.Interaction, 
        trait1: str = None, 
        trait2: str = None,
        trait3: str = None,
        trait4: str = None,
        playground: str = None,
        district: str = None,
        cost: int = None,
    ) -> None:
        if await bot._reject_if_banned(interaction):
            return

        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            await bot._maybe_welcome(interaction.user)
        except Exception as exc:
            log.warning("Failed to send welcome message: %s", exc)

        if bot._api is None:
            await interaction.followup.send("API client not ready yet.", ephemeral=True)
            return

        try:
            doodle_data = await bot._api.fetch("doodles")
        except Exception as exc:
            log.exception("Failed to fetch doodles: %s", exc)
            await interaction.followup.send("Failed to fetch doodle data.", ephemeral=True)
            return

        # Flatten and filter the doodles
        from Features.Core.formatters.formatters import doodle_priority, doodle_quality, PRIORITY_REST, JELLYBEAN_EMOJI, star_for

        search_traits = [t.strip() for t in (trait1, trait2, trait3, trait4) if t and t.strip()]
        
        results = []
        for dist, playgrounds in (doodle_data or {}).items():
            if district and district.lower() not in dist.lower():
                continue
                
            for pg, doodles in playgrounds.items():
                if playground and playground.lower() not in pg.lower():
                    continue
                    
                for d in doodles:
                    traits = d.get("traits") or []
                    dna = d.get("dna", "")
                    cost = d.get("cost", "?")
                    parsed_cost = _cost_as_int(cost)

                    if cost is not None and parsed_cost != cost:
                        continue
                    
                    if search_traits:
                        matched_count, similarity = _trait_search_score(search_traits, traits)
                        if matched_count == 0:
                            continue
                    else:
                        matched_count, similarity = 0, 0.0

                    results.append((dist, pg, traits, cost, dna, matched_count, similarity))

        # Drop "REST" tier doodles if we have a lot of results, unless specifically searching for bad ones
        if len(results) > 7 and not search_traits and cost is None:
            results = [r for r in results if doodle_priority(r[2]) != PRIORITY_REST]

        # Sort by closest requested traits first, then let quality fill blank slots.
        results.sort(key=lambda r: (
            -r[5],
            -r[6],
            doodle_priority(r[2]),
            -doodle_quality(r[2]),
            r[0].lower(),
            r[1].lower(),
        ))

        # Take Top 7
        top_results = results[:7]

        if not top_results:
            await interaction.followup.send("No doodles found matching those criteria.", ephemeral=True)
            return

        embeds = []
        for dist, pg, traits, cost, dna, _matched_count, _similarity in top_results:
            embed = discord.Embed(color=0x9124F2)
            
            traits_list = traits or []
            trait_str = ", ".join(traits_list) if traits_list else "Traits not listed"
            
            # Formatting as requested: [trait, trait] [location] [cost]
            stars = "".join(star_for(t, i) for i, t in enumerate(traits_list[:4]))
            
            title_text = f"[{stars}] [{trait_str}] [{dist} · {pg}] [{JELLYBEAN_EMOJI} {cost}]"
            embed.description = f"**{title_text}**"
                
            # Render image
            image_url = f"https://rendition.toontownrewritten.com/render/{dna}/doodle/256x256.png"
            embed.set_image(url=image_url)
            embeds.append(embed)

        # Generate thread name
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        thread_name = f"{interaction.user.display_name}'s Search {now_str}"

        # Search results should live under the tracked doodles feed channel,
        # regardless of where the slash command was invoked.
        channel = await _resolve_doodles_channel(bot, interaction)
        
        if channel is not None:
            try:
                thread = await channel.create_thread(
                    name=thread_name[:100],
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=60
                )
                await thread.send(content="Here are the top results:", embeds=embeds)

                guild = interaction.guild
                guild_name = guild.name if guild else "Unknown"
                guild_id = guild.id if guild else 0
                log.info("[%s][%d][%s][%d][1 MsgAdd]",
                         guild_name, guild_id, thread_name, thread.id)

                await interaction.followup.send(
                    content=(
                        f"Found {len(top_results)} doodles! "
                        f"I posted the results in {thread.mention} under {channel.mention}."
                    )
                )
                
                # Schedule auto-deletion of the thread after 10 minutes (600 seconds)
                import asyncio
                async def delete_thread_later():
                    await asyncio.sleep(600)
                    try:
                        await thread.delete()
                    except Exception:
                        pass
                        
                asyncio.create_task(delete_thread_later())
            except discord.Forbidden:
                log.warning("No permission to create/send doodlesearch thread in #%s", channel.name)
                await interaction.followup.send(
                    content=(
                        f"I found {len(top_results)} doodles, but I don't have permission "
                        f"to create or post in threads under {channel.mention}."
                    ),
                    embeds=embeds,
                )
            except discord.HTTPException as e:
                log.error("Failed to create doodlesearch thread in #%s: %s", channel.name, e)
                await interaction.followup.send(
                    content=(
                        f"I found {len(top_results)} doodles, but Discord would not let me "
                        f"create the results thread in {channel.mention}."
                    ),
                    embeds=embeds,
                )
        else:
            # Fallback for DMs, existing threads, or non-text channels
            msg = await interaction.followup.send(
                content=f"Here are the top {len(top_results)} doodles matching your search:",
                embeds=embeds,
                wait=True
            )
            # Try to delete after 10m
            import asyncio
            try:
                asyncio.create_task(msg.delete(delay=600))
            except Exception:
                pass
