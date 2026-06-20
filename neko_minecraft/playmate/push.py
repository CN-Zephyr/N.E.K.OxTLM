import asyncio
import time
from collections import deque


class MinecraftPushRouter:
    def __init__(self, plugin, aggregate_window=8, throttle_window=30, throttle_limit=6):
        self._plugin = plugin
        self._aggregate_window = max(0, float(aggregate_window or 0))
        self._throttle_window = max(1, float(throttle_window or 1))
        self._throttle_limit = max(1, int(throttle_limit or 1))
        self._pending_low = []
        self._flush_task = None
        self._push_times = deque()

    async def push(self, text, ai_behavior="read", priority=1, metadata=None, aggregate=None, coalesce_key=None):
        if not text:
            return
        if aggregate is None:
            aggregate = ai_behavior == "read" and priority <= 2
        if aggregate:
            self._pending_low.append((time.time(), text, priority, metadata or {}))
            self._plugin._playmate_debug.record("push", route="aggregate_pending", ai_behavior=ai_behavior, priority=priority, pending=len(self._pending_low), text=str(text)[:160])
            if self._aggregate_window <= 0:
                await self._flush_pending()
                return
            self._ensure_flush_task()
            return
        self._direct_push(text, ai_behavior=ai_behavior, priority=priority, metadata=metadata, coalesce_key=coalesce_key)

    def recent_push_count(self, window_seconds=60):
        now = time.time()
        self._trim_push_times(now, window_seconds)
        return len(self._push_times)

    async def flush(self):
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        await self._flush_pending(ignore_throttle=True)

    def _ensure_flush_task(self):
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self):
        await asyncio.sleep(self._aggregate_window)
        await self._flush_pending()

    async def _flush_pending(self, ignore_throttle=False):
        if not self._pending_low:
            return
        now = time.time()
        self._trim_push_times(now, self._throttle_window)
        if not ignore_throttle and len(self._push_times) >= self._throttle_limit:
            self._plugin._playmate_debug.record("push", route="throttled", pending=len(self._pending_low), recent_push_count=len(self._push_times))
            if self._flush_task is None or self._flush_task.done() or self._flush_task is asyncio.current_task():
                self._flush_task = asyncio.create_task(self._delayed_flush())
            return
        items = self._pending_low
        self._pending_low = []
        lines = []
        for _, text, _, _ in items:
            for line in str(text).splitlines():
                line = line.strip()
                if line:
                    lines.append(line if line.startswith("-") else f"- {line}")
        merged = "Minecraft 陪玩上下文：\n" + "\n".join(lines)
        priority = max((item[2] for item in items), default=1)
        self._direct_push(merged, ai_behavior="read", priority=priority)

    def _direct_push(self, text, ai_behavior="read", priority=1, metadata=None, coalesce_key=None):
        self._push_times.append(time.time())
        self._plugin._playmate_debug.record("push", route="direct", ai_behavior=ai_behavior, priority=priority, coalesce_key=coalesce_key, text=str(text)[:160])
        self._plugin.push_message(
            source="minecraft",
            ai_behavior=ai_behavior,
            parts=[{"type": "text", "text": text}],
            metadata=metadata,
            priority=priority,
            coalesce_key=coalesce_key,
        )

    def _trim_push_times(self, now, window_seconds):
        while self._push_times and now - self._push_times[0] > window_seconds:
            self._push_times.popleft()
