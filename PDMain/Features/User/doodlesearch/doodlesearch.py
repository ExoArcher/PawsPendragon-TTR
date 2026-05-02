# -*- coding: utf-8 -*-
import logging
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.doodlesearch")

# Classic and TTR Doodle Colors mapped from hex bytes
TTR_COLORS = {
    "00": "White",
    "01": "Peach",
    "02": "Red",
    "03": "Orange",
    "04": "Yellow",
    "05": "Green",
    "06": "Light Blue",
    "07": "Blue",
    "08": "Purple",
    "09": "Brown",
    "0a": "Black",
    "0b": "Pink",
    "0c": "Dark Green",
    "0d": "Teal",
    "0e": "Magenta",
    "0f": "Crimson",
    "10": "Sea Green",
    "11": "Mint",
    "12": "Lavender",
    "13": "Salmon",
    "14": "Periwinkle",
    "15": "Steel Blue",
    "16": "Forest Green",
    "17": "Coral",
    "18": "Navy",
    "19": "Plum",
    "1a": "Indigo",
    "ff": "Default/Pattern",
}

def get_doodle_colors(dna: str) -> list[str]:
    """Parse the DNA string (20 hex chars) for color traits.
    Bytes 2, 3, and 4 (indices 4:6, 6:8, 8:10) represent head, body, and legs colors.
    """
    if not dna or len(dna) < 10:
        return []
    
    colors = set()
    for i in range(4, 10, 2):
        hex_byte = dna[i:i+2].lower()
        if hex_byte in TTR_COLORS and hex_byte != "ff":
            colors.add(TTR_COLORS[hex_byte])
    return list(colors)


def register_doodlesearch(bot: TTRBot) -> None:
    @bot.tree.command(
        name="doodlesearch",
        description="Search for specific doodles by trait, color, or location.",
    )
    @app_commands.describe(
        trait="Filter by a specific trait (e.g., 'Rarely Tired', 'Always Playful')",
        color="Filter by color (e.g., 'Red', 'Blue', 'Purple')",
        playground="Filter by a playground (e.g., 'Donald\\'s Dreamland')",
        district="Filter by a district (e.g., 'Splat Summit')"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def doodlesearch(
        interaction: discord.Interaction, 
        trait: str = None, 
        color: str = None,
        playground: str = None,
        district: str = None
    ) -> None:
        if await bot._reject_if_banned(interaction):
            return

        await interaction.response.defer(ephemeral=False, thinking=True)
        await bot._maybe_welcome(interaction.user)

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
                    
                    # Filter by Trait
                    if trait:
                        if not any(trait.lower() in t.lower() for t in traits):
                            continue
                    
                    # Filter by Color
                    if color:
                        dna_colors = get_doodle_colors(dna)
                        if not any(color.lower() in c.lower() for c in dna_colors):
                            continue

                    results.append((dist, pg, traits, d.get("cost", "?"), dna))

        # Drop "REST" tier doodles if we have a lot of results, unless specifically searching for bad ones
        if len(results) > 5 and not trait:
            results = [r for r in results if doodle_priority(r[2]) != PRIORITY_REST]

        # Sort by best traits
        results.sort(key=lambda r: (
            doodle_priority(r[2]),
            -doodle_quality(r[2]),
            r[0].lower(),
            r[1].lower(),
        ))

        # Take Top 5
        top_results = results[:5]

        if not top_results:
            await interaction.followup.send("No doodles found matching those criteria.", ephemeral=True)
            return

        embeds = []
        for dist, pg, traits, cost, dna in top_results:
            embed = discord.Embed(color=0x9124F2)
            
            traits_list = traits or []
            trait_str = ", ".join(traits_list) if traits_list else "Traits not listed"
            
            # Formatting as requested: [trait, trait] [location] [cost]
            stars = "".join(star_for(t, i) for i, t in enumerate(traits_list[:4]))
            
            title_text = f"[{stars}] [{trait_str}] [{dist} · {pg}] [{JELLYBEAN_EMOJI} {cost}]"
            embed.description = f"**{title_text}**"
            
            # Display colors if known
            colors = get_doodle_colors(dna)
            if colors:
                embed.set_footer(text=f"Colors: {', '.join(colors)}")
                
            # Render image
            image_url = f"https://rendition.toontownrewritten.com/render/{dna}/doodle/256x256.png"
            embed.set_image(url=image_url)
            embeds.append(embed)

        # Send response and auto-delete after 10 minutes (600 seconds)
        msg = await interaction.followup.send(
            content=f"Here are the top {len(top_results)} doodles matching your search:",
            embeds=embeds,
            wait=True
        )
        
        # Schedule auto-deletion
        try:
            import asyncio
            asyncio.create_task(msg.delete(delay=600))
        except Exception as e:
            log.warning(f"Failed to schedule deletion for doodlesearch message: {e}")
