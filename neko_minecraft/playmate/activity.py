import time
from dataclasses import dataclass


@dataclass
class ActivityUpdate:
    state: str
    label: str
    text: str


class PlayerActivityInference:
    def __init__(self, debounce_checks=2, cooldown_seconds=120):
        self._debounce_checks = max(1, int(debounce_checks or 1))
        self._cooldown_seconds = max(0, int(cooldown_seconds or 0))
        self._stable_state = "unknown"
        self._candidate_state = "unknown"
        self._candidate_count = 0
        self._last_change_time = 0

    @property
    def stable_state(self):
        return self._stable_state

    @property
    def stable_label(self):
        return self._label(self._stable_state)

    def observe(self, awareness_data, memory=None, now=None):
        now = now or time.time()
        state = self._classify(awareness_data or {}, memory)
        if state == self._stable_state:
            self._candidate_state = state
            self._candidate_count = 0
            return None
        if state == self._candidate_state:
            self._candidate_count += 1
        else:
            self._candidate_state = state
            self._candidate_count = 1
        if self._candidate_count < self._debounce_checks:
            return None
        if now - self._last_change_time < self._cooldown_seconds:
            return None
        old_state = self._stable_state
        self._stable_state = state
        self._last_change_time = now
        label = self._label(state)
        old_label = self._label(old_state)
        text = f"玩家活动状态从{old_label}变为{label}，可以按这个阶段自然陪玩，不需要刻意打断。"
        return ActivityUpdate(state=state, label=label, text=text)

    def _classify(self, data, memory):
        if data.get("player_on_fire") or data.get("player_is_drowning"):
            return "combat"
        player_health = data.get("player_health", 20) or 20
        player_max_health = data.get("player_max_health", 20) or 20
        if player_health < player_max_health * 0.35:
            return "combat"
        if self._has_close_hostile(data):
            return "combat"
        distance = data.get("maid_player_distance")
        if distance is not None and distance > 50:
            return "away"
        held = str(data.get("player_held_item", "")).lower()
        if data.get("is_underground"):
            if any(k in held for k in ("pickaxe", "torch", "ore")):
                return "mining"
            return "underground_exploring"
        if any(k in held for k in ("pickaxe", "shovel", "axe")):
            return "gathering"
        if self._is_building_item(held):
            return "building"
        if any(k in held for k in ("sword", "bow", "crossbow", "trident", "shield")):
            return "danger_exploring"
        structures = data.get("nearby_structures") or []
        if structures:
            return "exploring"
        if not held:
            return "idle"
        return "unknown"

    def _has_close_hostile(self, data):
        for hostile in data.get("nearby_hostiles") or []:
            if hostile.get("distance", 999) < 12:
                return True
        return False

    def _recent_memory_matches(self, memory, keywords):
        if not memory:
            return False
        for item in memory.recent(5):
            if any(keyword in item.summary for keyword in keywords):
                return True
        return False

    def _is_building_item(self, held):
        if not held:
            return False
        building_keywords = (
            "planks", "glass", "brick", "concrete", "wool", "stairs", "slab",
            "fence", "door", "trapdoor", "lantern", "torch", "scaffolding",
        )
        if any(k in held for k in building_keywords):
            return True
        exact_blocks = (
            "minecraft:stone", "minecraft:cobblestone", "minecraft:dirt", "minecraft:grass_block",
            "minecraft:oak_log", "minecraft:spruce_log", "minecraft:birch_log",
        )
        return held in exact_blocks

    def _label(self, state):
        return {
            "unknown": "未知",
            "combat": "战斗/危险探索",
            "away": "远离女仆",
            "mining": "挖矿",
            "underground_exploring": "地下探索",
            "gathering": "采集整理",
            "building": "建造/整理",
            "danger_exploring": "危险探索",
            "organizing": "整理物品",
            "exploring": "探索",
            "idle": "闲置",
        }.get(state, state)
