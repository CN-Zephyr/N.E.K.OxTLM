import time


class QuietCompanionTrigger:
    def __init__(self, stable_seconds=90, cooldown_seconds=300):
        self._stable_seconds = max(0, int(stable_seconds or 0))
        self._cooldown_seconds = max(0, int(cooldown_seconds or 0))
        self._state = "unknown"
        self._state_since = 0
        self._last_trigger = {}

    def observe(self, state, label, recent_push_count=0, now=None):
        now = now or time.time()
        state = state or "unknown"
        if state != self._state:
            self._state = state
            self._state_since = now
            return None
        if state in ("unknown", "combat", "away", "exploring", "danger_exploring", "gathering"):
            return None
        if recent_push_count > 2:
            return None
        if now - self._state_since < self._stable_seconds:
            return None
        if now - self._last_trigger.get(state, 0) < self._cooldown_seconds:
            return None
        self._last_trigger[state] = now
        return f"玩家已经持续处于{label}一段时间。请主动用一句很短、自然、低打扰的陪玩语气回应，可以轻轻吐槽、鼓励或提出一个很小的建议；不要长篇解释，也不要像系统提醒。"
