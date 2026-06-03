from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AgentMessage:
    sender: str
    receiver: str
    topic: str
    payload: Any
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class MessageBus:
    """In-memory message bus. MVP 阶段可替换为 Redis Stream / Celery / Kafka。"""

    def __init__(self) -> None:
        self._messages: list[AgentMessage] = []

    def publish(self, message: AgentMessage) -> None:
        self._messages.append(message)

    def consume(self, receiver: str, topic: str | None = None) -> list[AgentMessage]:
        matched = [msg for msg in self._messages if msg.receiver == receiver and (topic is None or msg.topic == topic)]
        self._messages = [msg for msg in self._messages if msg not in matched]
        return matched

    def peek_all(self) -> list[AgentMessage]:
        return list(self._messages)
