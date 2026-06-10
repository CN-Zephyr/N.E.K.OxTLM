"""感知系统 — 定时轮询游戏状态，检测玩家血量/着火/溺水、敌对生物、距离变化等，主动关心或提醒"""

import asyncio
import time
from collections import Counter


class AwarenessManager:
    def __init__(self, plugin):
        self._plugin = plugin
        self._task = None
        self._last_awareness_state = {}
        self._last_low_health_warn_time = 0
        self._last_fire_warn_time = 0
        self._last_drown_warn_time = 0
        self._last_hostile_warn_time = 0
        self._last_food_offer_time = 0
        self._last_dark_warn_time = 0
        self._pending_revenge = None
        self._was_dead = False
        self._last_notified_held_item = ""
        self._held_item_candidate = ""
        self._held_item_candidate_count = 0
        self._last_maid_player_distance = None
        self._player_nearby = True
        self._last_distance_warn_time = 0

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._awareness_loop())
            self._plugin.logger.info(
                f"[CommandLoop] Awareness loop started, interval={self._plugin._awareness_interval}s"
            )

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    async def _awareness_loop(self):
        self._plugin.logger.info("[Awareness] Loop started, first check in 5s")
        await asyncio.sleep(5)
        while True:
            try:
                maid_id = self._plugin._resolve_maid_id()
                if self._plugin._bridge and self._plugin._bridge.connected and maid_id:
                    changes = await self.detect_awareness_changes()
                    if changes:
                        context_items = [c for c in changes if c.get("context_only")]
                        respond_items = [c for c in changes if not c.get("context_only")]

                        if context_items:
                            context_text = "；".join(c["text"] for c in context_items)
                            self._plugin.push_message(
                                source="minecraft",
                                ai_behavior="read",
                                parts=[{"type": "text", "text": context_text}],
                                priority=1,
                            )

                        if respond_items:
                            change_text = "；".join(c["text"] for c in respond_items)
                            has_urgent = any(c.get("urgent") for c in respond_items)
                            self._plugin.logger.info(f"[Awareness] Pushing: {change_text}")
                            self._plugin.push_message(
                                source="minecraft",
                                ai_behavior="respond",
                                parts=[{"type": "text", "text": change_text}],
                                priority=6 if has_urgent else 3,
                            )
                await asyncio.sleep(self._plugin._awareness_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._plugin.logger.error(f"Awareness loop error: {e}")
                await asyncio.sleep(self._plugin._awareness_interval)

    async def detect_awareness_changes(self):
        changes = []
        try:
            maid_id = self._plugin._resolve_maid_id()
            if not maid_id:
                return changes

            now = time.time()

            result = await self._plugin._send_request({
                "type": "get_game_context",
                "data": {"maid_id": maid_id, "category": "awareness"},
            }, timeout=15)
            if result.get("type") == "error":
                return changes
            data = result.get("data", {})
            if data.get("error"):
                return changes

            new_state = {
                "is_raining": data.get("is_raining", False),
                "is_thundering": data.get("is_thundering", False),
                "time_of_day": data.get("time_of_day", 0),
                "nearby_hostiles": [],
                "maid_health": data.get("maid_health", 0),
                "player_health": data.get("player_health", 20),
                "player_max_health": data.get("player_max_health", 20),
                "player_on_fire": data.get("player_on_fire", False),
                "player_is_drowning": data.get("player_is_drowning", False),
                "light_level": data.get("light_level", 15),
                "is_underground": data.get("is_underground", False),
                "maid_inventory": [],
                "player_held_item": data.get("player_held_item", ""),
                "player_held_item_count": data.get("player_held_item_count", 0),
                "nearby_structures": [],
                "maid_player_distance": data.get("maid_player_distance", None),
            }

            entities = data.get("entities", [])
            hostile_types = ["creeper", "zombie", "skeleton", "spider", "enderman", "witch", "phantom", "slime", "wither", "blaze", "ghast"]
            for entity in entities:
                entity_type = entity.get("type", "").lower()
                if any(h in entity_type for h in hostile_types):
                    new_state["nearby_hostiles"].append({
                        "name": entity.get("name", ""),
                        "distance": entity.get("distance", 999),
                    })

            inv_items = data.get("inventory", [])
            if inv_items:
                new_state["maid_inventory"] = [{"item": item.get("item", ""), "count": item.get("count", 1)} for item in inv_items]

            structures = data.get("nearby_structures", [])
            if structures:
                new_state["nearby_structures"] = [{"name": s.get("name", ""), "distance": s.get("distance", 999)} for s in structures]

            old_state = self._last_awareness_state
            self._last_awareness_state = new_state

            if not old_state:
                return changes

            # === 0. Player held item change (debounced) ===
            new_held = new_state["player_held_item"]
            new_held_count = new_state["player_held_item_count"]
            if new_held == self._held_item_candidate:
                if new_held != self._last_notified_held_item:
                    self._last_notified_held_item = new_held
                    if new_held:
                        changes.append({"text": f"玩家手持物品: {new_held}x{new_held_count}", "urgent": False, "context_only": True})
                    else:
                        changes.append({"text": "玩家手持物品: 空", "urgent": False, "context_only": True})
            else:
                self._held_item_candidate = new_held
                self._held_item_candidate_count = new_held_count

            # === 0.5 Nearby structures discovery ===
            old_structures = {s["name"] for s in old_state.get("nearby_structures", [])}
            new_structures = new_state["nearby_structures"]
            discovered = [s for s in new_structures if s["name"] not in old_structures]
            if discovered:
                for s in discovered[:3]:
                    changes.append({"text": f"附近发现结构: {s['name']} (距离{s['distance']}格)", "urgent": False, "context_only": True})

            # === 0.6 Player near/far state change ===
            new_dist = new_state.get("maid_player_distance")
            if new_dist is not None:
                if self._player_nearby and new_dist > 50:
                    self._player_nearby = False
                    if now - self._last_distance_warn_time > 60:
                        self._last_distance_warn_time = now
                        changes.append({"text": "玩家走好远了...询问要去哪里呀？", "urgent": False})
                elif not self._player_nearby and new_dist < 30:
                    self._player_nearby = True
                    if now - self._last_distance_warn_time > 60:
                        self._last_distance_warn_time = now
                        changes.append({"text": "玩家回来了！你很开心", "urgent": False})
                self._last_maid_player_distance = new_dist

            # === 1. Revenge after respawn ===
            if self._was_dead and new_state["maid_health"] > 0:
                self._was_dead = False
                if self._pending_revenge:
                    revenge = self._pending_revenge
                    self._pending_revenge = None
                    killer = revenge.get("killer", "")
                    if killer:
                        changes.append({"text": f"我复活了！刚才那只{killer}呢？我要打回去！", "urgent": False})
                    else:
                        changes.append({"text": "我复活了！下次不会再倒下了！", "urgent": False})

            # === 2. Player health & status concern ===
            new_player_health = new_state["player_health"]
            player_max_health = new_state["player_max_health"]

            if new_player_health < player_max_health * 0.3 and now - self._last_low_health_warn_time > 300:
                self._last_low_health_warn_time = now
                changes.append({"text": "玩家血量低！提醒小心！", "urgent": True})

            if new_state["player_on_fire"] and now - self._last_fire_warn_time > 120:
                self._last_fire_warn_time = now
                changes.append({"text": "玩家着火了！快提醒灭火！", "urgent": True})

            if new_state["player_is_drowning"] and now - self._last_drown_warn_time > 120:
                self._last_drown_warn_time = now
                changes.append({"text": "玩家在溺水！提醒快上岸！", "urgent": True})

            # === 3. Proactive inventory sharing ===
            new_inventory = new_state["maid_inventory"]
            torch_keywords = ["torch", "soul_torch"]
            has_torches = any(any(tk in item.get("item", "") for tk in torch_keywords) for item in new_inventory)
            if new_inventory:
                food_keywords = ["bread", "cooked_beef", "cooked_porkchop", "cooked_mutton", "cooked_chicken",
                                 "cooked_cod", "cooked_salmon", "baked_potato", "golden_carrot", "apple",
                                 "melon_slice", "cookie", "cake", "pumpkin_pie"]
                has_food = any(any(fk in item.get("item", "") for fk in food_keywords) for item in new_inventory)

                if has_food and new_player_health < player_max_health * 0.7 and now - self._last_food_offer_time > 300:
                    self._last_food_offer_time = now
                    changes.append({"text": "询问玩家饿不饿？我这里有点吃的～", "urgent": False})

            # === 4. Dark cave torch suggestion ===
            if (new_state["is_underground"] and new_state["light_level"] < 7
                    and now - self._last_dark_warn_time > 600):
                self._last_dark_warn_time = now
                if has_torches:
                    changes.append({"text": "这里好暗...询问玩家要不要我帮忙插火把？", "urgent": False})
                else:
                    changes.append({"text": "这里好暗...表达有点害怕，可惜没有火把了", "urgent": False})

            # Hostile entities
            old_hostiles = {h["name"] for h in old_state.get("nearby_hostiles", [])}
            new_hostiles = new_state["nearby_hostiles"]
            appeared = [h for h in new_hostiles if h["name"] not in old_hostiles]
            close_danger = [h for h in appeared if h["distance"] < 10]
            if close_danger and now - self._last_hostile_warn_time > 180:
                self._last_hostile_warn_time = now
                counts = Counter(h["name"] for h in close_danger)
                parts = [f"{name}x{count}" if count > 1 else name for name, count in counts.items()]
                names = "、".join(parts)
                changes.append({"text": f"危险！附近有{names}！", "urgent": True})

        except Exception as e:
            self._plugin.logger.error(f"Awareness detection error: {e}")

        return changes
