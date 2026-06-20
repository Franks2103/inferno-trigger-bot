from dataclasses import dataclass
from typing import Optional

import discord


@dataclass
class Track:
    title: str
    webpage_url: str
    requester: discord.Member
    stream_url: Optional[str] = None  # None = pendiente de resolver (tracks de playlist)
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
