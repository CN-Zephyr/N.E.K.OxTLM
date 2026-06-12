import time

from .activity import PlayerActivityInference
from .memory import MinecraftShortTermMemory
from .minigame import MiniGameCompanion
from .quiet import QuietCompanionTrigger
from .suggestion import ProactiveSuggestionTrigger


class PlaymateContextManager:
    def __init__(self, plugin):
        self._plugin = plugin
        self.memory = MinecraftShortTermMemory(
            max_items=plugin._playmate_memory_items,
            max_summary_length=plugin._playmate_memory_summary_length,
        )
        self.activity = PlayerActivityInference(
            debounce_checks=plugin._playmate_activity_debounce_checks,
            cooldown_seconds=plugin._playmate_activity_cooldown,
        )
        self.quiet = QuietCompanionTrigger(
            stable_seconds=plugin._playmate_quiet_stable_seconds,
            cooldown_seconds=plugin._playmate_quiet_cooldown,
        )
        self.minigame = MiniGameCompanion(
            cooldown_seconds=plugin._playmate_minigame_feedback_cooldown,
            max_context_chars=plugin._playmate_minigame_context_chars,
        )
        self.suggestion = ProactiveSuggestionTrigger(
            cooldown_seconds=plugin._playmate_suggestion_cooldown,
        )
        self._last_observed_state = "unknown"

    def remember_event(self, event_type, text, priority=1):
        return self.memory.remember(event_type or "event", text, priority=priority)

    def remember_minigame_event(self, event_data, text, priority, side_effects):
        return self.minigame.record(event_data, text, priority, side_effects or {}, self.memory)

    def remember_awareness(self, changes):
        for change in changes or []:
            priority = 2 if change.get("context_only") else 6 if change.get("urgent") else 3
            self.memory.remember("awareness", change.get("text", ""), priority=priority)

    async def observe_awareness(self, awareness_data):
        update = self.activity.observe(awareness_data, self.memory)
        if update:
            self._plugin.logger.info(f"[Playmate] Activity changed: {update.state} ({update.label})")
            self.memory.remember("activity", update.text, priority=1)
            summary = self.memory.format_summary(
                limit=self._plugin._playmate_memory_inject_items,
                max_text_length=self._plugin._playmate_memory_inject_chars,
            )
            activity_text = update.text
            ai_behavior = "read"
            priority = 1
            aggregate = True
            if update.state in ("mining", "underground_exploring"):
                activity_text = f"{update.text}\n玩家像是进入了下矿/探洞节奏。请主动短短陪一句，重点是一起下去、注意照明或会陪着，不要像系统提醒。"
                ai_behavior = "respond"
                priority = 3
                aggregate = False
            text = f"{activity_text}\n最近共同经历：\n{summary}" if summary else activity_text
            await self._plugin._push_minecraft_context(text, ai_behavior=ai_behavior, priority=priority, aggregate=aggregate)
        stable_state = self.activity.stable_state
        if stable_state != self._last_observed_state:
            self._last_observed_state = stable_state
            self._plugin.logger.info(f"[Playmate] Stable state: {stable_state} ({self.activity.stable_label})")
        quiet_text = self.quiet.observe(
            stable_state,
            self.activity.stable_label,
            recent_push_count=self._plugin._minecraft_push.recent_push_count(60),
        )
        if quiet_text:
            self._plugin.logger.info(f"[Playmate] Quiet companion triggered: {self.activity.stable_label}")
            self.memory.remember("quiet", quiet_text, priority=1)
            summary = self.memory.format_summary(
                limit=self._plugin._playmate_memory_inject_items,
                max_text_length=self._plugin._playmate_memory_inject_chars,
            )
            text = f"{quiet_text}\n最近共同经历：\n{summary}" if summary else quiet_text
            await self._plugin._push_minecraft_context(text, ai_behavior="respond", priority=3, aggregate=False)
        suggestion = None
        if not quiet_text:
            suggestion = self.suggestion.observe(
                awareness_data,
                stable_state,
                recent_push_count=self._plugin._minecraft_push.recent_push_count(60),
                recent_chat_seconds=self._recent_chat_seconds(),
            )
        if suggestion:
            self._plugin.logger.info(f"[Playmate] Proactive suggestion triggered: {stable_state}")
            suggestion_text = suggestion.get("text", "")
            should_respond = bool(suggestion.get("respond"))
            self.memory.remember("suggestion", suggestion_text, priority=1)
            summary = self.memory.format_summary(
                limit=self._plugin._playmate_memory_inject_items,
                max_text_length=self._plugin._playmate_memory_inject_chars,
            )
            text = f"{suggestion_text}\n最近共同经历：\n{summary}" if summary else suggestion_text
            await self._plugin._push_minecraft_context(
                text,
                ai_behavior="respond" if should_respond else "read",
                priority=3 if should_respond else 1,
                aggregate=not should_respond,
            )

    def _recent_chat_seconds(self):
        for item in reversed(self.memory.recent(12)):
            if item.kind == "chat":
                return time.time() - item.timestamp
        return None
