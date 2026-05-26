"""Redis Stream 实现的 MessageBus。

提供与 InMemoryBus 相同的接口，支持：
- 消息持久化
- 消费者组（Consumer Group）
- 消息确认（ACK）
- 自动 fallback 到内存实现

通过环境变量 MESSAGE_BUS_BACKEND=redis 启用。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol

from .message_bus import AgentMessage


class MessageBusProtocol(Protocol):
    """消息总线协议。所有实现（InMemory / Redis / Kafka）统一接口。"""

    def publish(self, message: AgentMessage) -> None:
        ...

    def consume(self, receiver: str, topic: str | None = None) -> list[AgentMessage]:
        ...

    def peek_all(self) -> list[AgentMessage]:
        ...


class RedisStreamBus:
    """基于 Redis Stream 的消息总线。

    特性：
    - 每个 receiver 对应一个 Consumer Group
    - 消息按时间有序
    - 支持消息持久化和重放
    - 自动创建 stream 和 consumer group
    """

    STREAM_KEY = "code_review:messages"

    def __init__(self, redis_url: str | None = None) -> None:
        try:
            import redis
        except ImportError:
            raise ImportError("redis package required: pip install redis")

        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = redis.from_url(self._redis_url, decode_responses=True)
        self._ensure_stream()

    def _ensure_stream(self) -> None:
        """确保 stream 存在。"""
        try:
            self._redis.xinfo_stream(self.STREAM_KEY)
        except Exception:
            # Stream 不存在时会自动在第一次 XADD 时创建
            pass

    def _ensure_group(self, group: str) -> None:
        """确保 consumer group 存在。"""
        try:
            self._redis.xgroup_create(self.STREAM_KEY, group, id="0", mkstream=True)
        except Exception:
            # 如果 group 已存在会抛出错误，忽略
            pass

    def publish(self, message: AgentMessage) -> None:
        """发布消息到 Redis Stream。"""
        data = {
            "sender": message.sender,
            "receiver": message.receiver,
            "topic": message.topic,
            "payload": json.dumps(message.payload, default=str, ensure_ascii=False),
            "timestamp": str(time.time()),
        }
        self._redis.xadd(self.STREAM_KEY, data)

    def consume(self, receiver: str, topic: str | None = None) -> list[AgentMessage]:
        """从 Redis Stream 消费指定 receiver 的消息。"""
        group = f"group:{receiver}"
        consumer = f"consumer:{receiver}"
        self._ensure_group(group)

        messages: list[AgentMessage] = []
        try:
            entries = self._redis.xreadgroup(group, consumer, {self.STREAM_KEY: ">"}, count=100, block=0)
        except Exception:
            return messages

        if not entries:
            return messages

        for stream_name, stream_entries in entries:
            for msg_id, fields in stream_entries:
                if fields.get("receiver") != receiver:
                    # ACK but skip
                    self._redis.xack(self.STREAM_KEY, group, msg_id)
                    continue
                if topic and fields.get("topic") != topic:
                    self._redis.xack(self.STREAM_KEY, group, msg_id)
                    continue

                try:
                    payload = json.loads(fields.get("payload", "{}"))
                except (json.JSONDecodeError, TypeError):
                    payload = fields.get("payload")

                messages.append(AgentMessage(
                    sender=fields.get("sender", ""),
                    receiver=fields.get("receiver", ""),
                    topic=fields.get("topic", ""),
                    payload=payload,
                ))
                self._redis.xack(self.STREAM_KEY, group, msg_id)

        return messages

    def peek_all(self) -> list[AgentMessage]:
        """查看所有未消费消息（不消费）。"""
        messages: list[AgentMessage] = []
        try:
            entries = self._redis.xrange(self.STREAM_KEY, "-", "+")
        except Exception:
            return messages

        for msg_id, fields in entries:
            try:
                payload = json.loads(fields.get("payload", "{}"))
            except (json.JSONDecodeError, TypeError):
                payload = fields.get("payload")
            messages.append(AgentMessage(
                sender=fields.get("sender", ""),
                receiver=fields.get("receiver", ""),
                topic=fields.get("topic", ""),
                payload=payload,
            ))
        return messages


def create_message_bus() -> MessageBusProtocol:
    """工厂函数：根据环境变量选择消息总线实现。

    MESSAGE_BUS_BACKEND=redis  → RedisStreamBus
    MESSAGE_BUS_BACKEND=memory → InMemoryBus（默认）
    """
    from .message_bus import MessageBus as InMemoryBus

    backend = os.getenv("MESSAGE_BUS_BACKEND", "memory").lower()
    if backend == "redis":
        try:
            return RedisStreamBus()
        except (ImportError, Exception) as e:
            import logging
            logging.warning(f"Redis bus unavailable ({e}), falling back to in-memory bus")
            return InMemoryBus()
    return InMemoryBus()
