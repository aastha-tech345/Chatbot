"""Bounded, short-lived conversation context, isolated by application and principal.

Use a shared store/lock when deploying multiple workers. Credentials are never accepted
by this store; login is handled by the host application's authentication endpoint.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass
class Conversation:
    updated: float = field(default_factory=monotonic)
    turns: list[dict[str, Any]] = field(default_factory=list)
    checkout_context: dict[str, Any] = field(default_factory=dict)
    responses: OrderedDict = field(default_factory=OrderedDict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConversationStore:
    def __init__(self, capacity: int = 1000, ttl: int = 1800):
        self.capacity, self.ttl = capacity, ttl
        self.entries: OrderedDict[tuple[str, str, str], Conversation] = OrderedDict()

    def get(self, app_id: str, principal: str, conversation_id: str) -> Conversation:
        now = monotonic()
        for key, entry in list(self.entries.items()):
            if now - entry.updated > self.ttl and not entry.lock.locked():
                del self.entries[key]
        key = (app_id, principal, conversation_id)
        if key not in self.entries:
            if len(self.entries) >= self.capacity:
                victim = next((key for key, entry in self.entries.items() if not entry.lock.locked()), None)
                if victim is None:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=503, detail="Please try again shortly.")
                del self.entries[victim]
            self.entries[key] = Conversation()
        entry = self.entries[key]
        entry.updated = now
        self.entries.move_to_end(key)
        return entry


conversations = ConversationStore()
