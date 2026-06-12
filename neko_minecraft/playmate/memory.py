import time
from collections import deque
from dataclasses import dataclass


@dataclass
class MinecraftMemoryItem:
    timestamp: float
    kind: str
    priority: int
    summary: str


class MinecraftShortTermMemory:
    def __init__(self, max_items=24, max_summary_length=120):
        self._items = deque(maxlen=max_items)
        self._max_summary_length = max_summary_length

    def remember(self, kind, summary, priority=1, timestamp=None):
        text = self._normalize(summary)
        if not text:
            return None
        item = MinecraftMemoryItem(
            timestamp=timestamp or time.time(),
            kind=str(kind or "context"),
            priority=int(priority or 0),
            summary=text,
        )
        self._items.append(item)
        return item

    def recent(self, limit=None):
        items = list(self._items)
        if limit is not None:
            items = items[-limit:]
        return items

    def format_summary(self, limit=8, max_text_length=700):
        lines = []
        for item in self.recent(limit):
            time_text = time.strftime("%H:%M:%S", time.localtime(item.timestamp))
            lines.append(f"- {time_text} [{item.kind}] {item.summary}")
        text = "\n".join(lines)
        if len(text) > max_text_length:
            text = text[-max_text_length:].lstrip()
            first_newline = text.find("\n")
            if first_newline >= 0:
                text = text[first_newline + 1:]
        return text

    def _normalize(self, summary):
        text = str(summary or "").strip()
        if len(text) > self._max_summary_length:
            return text[:self._max_summary_length - 1].rstrip() + "…"
        return text
