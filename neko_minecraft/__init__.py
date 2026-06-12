"""N.E.K.O Minecraft 插件主模块 — 插件生命周期、消息分发、LLM 工具声明与 UI 入口"""

from plugin.sdk.plugin import (
    NekoPluginBase, neko_plugin, lifecycle, llm_tool,
    plugin_entry, ui, tr,
    Ok, Err, SdkError,
)
import asyncio
import os
import sys
import uuid

from .instructions import _TLM_AI_INSTRUCTIONS
from .bridge import WSBridge
from . import config as _config
from . import events as _events
from .awareness import AwarenessManager
from . import tools as _tools
from .playmate import PlaymateContextManager, MinecraftPushRouter

from .tool_defs import (
    MC_MAID_STATUS, MC_SWITCH_FOLLOW, MC_SWITCH_SIT,
    MC_SWITCH_TASK, MC_SWITCH_SCHEDULE, MC_EQUIP_ITEM,
    MC_SEND_CHAT, MC_GAME_CONTEXT, MC_USE_SKILL, MC_EXECUTE_COMMAND,
)


@neko_plugin
class NekoMinecraftPlugin(NekoPluginBase):

    def __init__(self, ctx):
        super().__init__(ctx)
        self.logger = ctx.logger
        self._bridge = None
        self._poll_task = None
        self._request_futures = {}
        self._maid_status_cache = {}
        self._ws_url = "ws://127.0.0.1:48920"
        self._heartbeat_interval = 30
        self._reconnect_interval = 5
        self._max_reconnect_interval = 60
        self._assigned_maid_id = ""
        self._assigned_maid_name = ""
        self._command_execution_enabled = False
        self._chat_bubble_enabled = True
        self._chat_box_enabled = True
        self._instructions_injected = False
        self._awareness_interval = 60
        self._playmate_memory_items = 24
        self._playmate_memory_summary_length = 120
        self._playmate_memory_inject_items = 8
        self._playmate_memory_inject_chars = 700
        self._playmate_activity_debounce_checks = 2
        self._playmate_activity_cooldown = 120
        self._playmate_quiet_stable_seconds = 90
        self._playmate_quiet_cooldown = 300
        self._playmate_aggregate_window = 8
        self._playmate_throttle_window = 30
        self._playmate_throttle_limit = 6
        self._minecraft_push = MinecraftPushRouter(self)
        self._playmate = PlaymateContextManager(self)
        self._awareness = AwarenessManager(self)

    def _load_config(self):
        _config.load_config(self)

    def _save_config(self):
        _config.save_config(self)

    def _refresh_playmate_modules(self):
        self._minecraft_push = MinecraftPushRouter(
            self,
            aggregate_window=self._playmate_aggregate_window,
            throttle_window=self._playmate_throttle_window,
            throttle_limit=self._playmate_throttle_limit,
        )
        self._playmate = PlaymateContextManager(self)

    async def _push_minecraft_context(self, text, ai_behavior="read", priority=1, metadata=None, aggregate=None):
        await self._minecraft_push.push(
            text,
            ai_behavior=ai_behavior,
            priority=priority,
            metadata=metadata,
            aggregate=aggregate,
        )

    @lifecycle(id="startup")
    async def on_startup(self, **_):
        self._load_config()
        self._refresh_playmate_modules()
        self.logger.info(f"Python {sys.version}")
        self.logger.info(f"Event loop: {type(asyncio.get_event_loop())}")
        if self._assigned_maid_id:
            self.logger.info(f"[Config] Assigned maid: {self._assigned_maid_name} ({self._assigned_maid_id})")
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        if self._bridge:
            self._bridge.stop()
        self._bridge = WSBridge(
            ws_url=self._ws_url, logger=self.logger,
            heartbeat_interval=self._heartbeat_interval,
        )
        self._bridge.start()
        self._poll_task = asyncio.create_task(self._poll_messages())
        self._instructions_injected = False
        self.logger.info(f"[Startup] Bridge started, maid_id={self._assigned_maid_id}")
        return Ok({"status": "ready"})

    async def _on_command_loop_start(self):
        self.logger.info("[CommandLoop] Starting message poll on command loop")
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = asyncio.create_task(self._poll_messages())
        self._awareness.start()

    @lifecycle(id="shutdown")
    async def on_shutdown(self, **_):
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._awareness.stop()
        if self._bridge:
            self._bridge.stop()
        await self._minecraft_push.flush()
        return Ok({"status": "stopped"})

    async def _poll_messages(self):
        while True:
            try:
                if self._bridge:
                    if self._bridge.mc_exited:
                        self.logger.info("[Poll] MC has exited, cleaning up plugin resources")
                        self._awareness.stop()
                        self._bridge.stop()
                        self._instructions_injected = False
                        os._exit(0)
                    if self._bridge.connected and not self._instructions_injected:
                        await self._inject_instructions()
                    for data in self._bridge.drain():
                        await self._handle_message(data)
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Poll error: {e}")
                await asyncio.sleep(1)

    async def _inject_instructions(self):
        self._instructions_injected = True
        try:
            config_result = await self._send_request({"type": "get_config"}, timeout=5)
            if config_result.get("type") == "config":
                _config.sync_config(self, config_result.get("data", {}))
        except Exception:
            pass
        if self._assigned_maid_id:
            try:
                await self._send_request({
                    "type": "set_monitored_maid",
                    "data": {"maid_id": self._assigned_maid_id},
                }, timeout=5)
            except Exception:
                pass
        instructions = _TLM_AI_INSTRUCTIONS
        if self._assigned_maid_id and self._assigned_maid_name:
            instructions += (
                f"\n\n## 当前配置\n你已被指定为女仆「{self._assigned_maid_name}」"
                f"（maid_id={self._assigned_maid_id}）。所有需要 maid_id 的操作会自动使用此 ID，你无需再调用 mc_maid_status 获取。\n"
            )
        self.push_message(
            source="minecraft", ai_behavior="read",
            parts=[{"type": "text", "text": instructions}], priority=0,
        )
        self.logger.info("[TLM] Injected AI calling instructions into LLM context")

    async def _handle_message(self, data):
        msg_type = data.get("type", "")
        request_id = data.get("request_id")
        if msg_type == "pong":
            return
        if msg_type in ("maid_status", "game_context", "command_result",
                        "chat_result", "skill_result", "command_execution_result",
                        "attack_target_result", "error"):
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return
        if msg_type == "config":
            _config.sync_config(self, data.get("data", {}))
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return
        if msg_type == "config_update":
            _config.sync_config(self, data.get("data", {}))
            return
        if msg_type == "event":
            await self._handle_event(data)
            return
        if msg_type == "chat_message":
            chat_data = data.get("data", {})
            sender = chat_data.get("sender", "unknown")
            message = chat_data.get("message", "")
            text = f"{sender}说了: {message}"
            self._playmate.remember_event("chat", text, priority=7)
            await self._push_minecraft_context(
                text,
                ai_behavior="respond",
                metadata={"description": f"Minecraft聊天消息 - {sender}: {message}"},
                priority=7,
            )
            return
        if request_id and request_id in self._request_futures:
            self._request_futures[request_id].set_result(data)
            del self._request_futures[request_id]

    async def _handle_event(self, data):
        event_data = data.get("data", {})
        parts_text, priority, side_effects = _events.format_event(
            event_data, self._assigned_maid_id
        )
        if parts_text is None:
            return
        event_type = event_data.get("event_type", "event")
        self._playmate.remember_event(event_type, parts_text, priority=priority)
        if side_effects:
            if "pending_revenge" in side_effects:
                self._awareness._pending_revenge = side_effects["pending_revenge"]
            if "was_dead" in side_effects:
                self._awareness._was_dead = side_effects["was_dead"]

        # 棋局事件特殊处理
        if side_effects.get("chess_event"):
            ai_behavior = side_effects.get("ai_behavior", "respond")
            chess_event_type = side_effects.get("chess_event_type", "")

            self.logger.info(
                f"[Chess] Event: {chess_event_type}, "
                f"game={event_data.get('game_type', '?')}, "
                f"priority={priority}, ai_behavior={ai_behavior}, "
                f"text={parts_text[:80]}"
            )

            await self._push_minecraft_context(
                parts_text,
                ai_behavior=ai_behavior,
                priority=priority,
                aggregate=ai_behavior == "read" and priority <= 4,
            )
            return

        await self._push_minecraft_context(
            parts_text,
            ai_behavior="respond",
            priority=priority,
        )

    async def _send(self, data):
        if self._bridge and self._bridge.connected:
            self._bridge.send(data)

    async def _send_request(self, data, timeout=30):
        if not self._bridge or not self._bridge.connected:
            return {"type": "error", "data": {"message": "Not connected to Minecraft"}}
        request_id = str(uuid.uuid4())
        data["request_id"] = request_id
        future = asyncio.get_event_loop().create_future()
        self._request_futures[request_id] = future
        self._bridge.send(data)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._request_futures.pop(request_id, None)
            return {"type": "error", "data": {"message": "Request timed out"}}

    @property
    def connected(self):
        return self._bridge and self._bridge.connected

    def _resolve_maid_id(self, maid_id=None):
        if maid_id:
            return maid_id
        if self._assigned_maid_id:
            return self._assigned_maid_id
        return self._get_cached_maid_id()

    def _get_cached_maid_id(self):
        if self._assigned_maid_id:
            return self._assigned_maid_id
        if self._maid_status_cache:
            first_id = next(iter(self._maid_status_cache.values()), None)
            if first_id:
                return first_id.get("id", "")
        return ""

    # ── UI context & actions ──

    @ui.context(id="dashboard")
    async def dashboard_context(self, **_):
        if self.connected and not self._maid_status_cache:
            try:
                result = await self._send_request({"type": "get_maid_status"}, timeout=5)
                if result.get("type") != "error":
                    for maid in result.get("data", {}).get("maids", []):
                        self._maid_status_cache[maid.get("id", "")] = maid
            except Exception as e:
                self.logger.warning(f"dashboard_context: failed to fetch maid_status: {e}")
        maids = []
        for maid in self._maid_status_cache.values():
            maids.append({
                "id": maid.get("id", ""), "name": maid.get("name", ""),
                "health": maid.get("health", 0), "max_health": maid.get("max_health", 0),
                "is_sitting": maid.get("is_sitting", False),
                "is_following": maid.get("is_following", False),
                "owner": maid.get("owner", ""),
            })
        return {
            "connected": self.connected, "ws_url": self._ws_url, "maids": maids,
            "assigned_maid_id": self._assigned_maid_id,
            "assigned_maid_name": self._assigned_maid_name,
            "command_execution_enabled": self._command_execution_enabled,
        }

    @ui.action(id="refresh_maid_status", label=tr("actions.refresh", default="Refresh Status"), tone="primary", refresh_context=True)
    @plugin_entry(id="refresh_maid_status", name=tr("entries.refresh.name", default="Refresh Maid Status"), description="Fetch current maid status from Minecraft", input_schema={"type": "object", "properties": {}}, llm_result_fields=["maids"])
    async def refresh_maid_status(self, **_):
        if not self.connected:
            return Err("Not connected to Minecraft")
        result = await self._send_request({"type": "get_maid_status"})
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        return Ok({"maids": result.get("data", {}).get("maids", [])})

    @ui.action(id="assign_maid", label=tr("actions.assignMaid", default="Assign Maid"), tone="primary", refresh_context=True)
    @plugin_entry(id="assign_maid", name=tr("entries.assign.name", default="Assign Maid"), description="Assign a specific maid by ID for the AI to control. ONLY use this tool when you need to CHANGE the current maid or no maid is assigned. If a maid is already assigned in the config, you do NOT need to call this tool; just proceed with the task directly.", input_schema={"type": "object", "properties": {"maid_id": {"type": "string", "description": "The maid entity ID (UUID) to assign"}, "maid_name": {"type": "string", "description": "The maid name for display"}}, "required": []}, llm_result_fields=["assigned_maid_id", "assigned_maid_name"])
    async def assign_maid(self, *, maid_id="", maid_name="", **_):
        if not maid_id:
            if self._assigned_maid_id:
                return Ok({"assigned_maid_id": self._assigned_maid_id, "assigned_maid_name": self._assigned_maid_name, "message": "Already assigned. No change."})
            return Err("maid_id is required")
        self._assigned_maid_id = maid_id
        self._assigned_maid_name = maid_name
        self._save_config()
        self._instructions_injected = False
        self.logger.info(f"[Config] Assigned maid: {maid_name} ({maid_id})")
        if self._bridge and self._bridge.connected and maid_id:
            self._bridge.send({"type": "set_monitored_maid", "data": {"maid_id": maid_id}})
        return Ok({"assigned_maid_id": maid_id, "assigned_maid_name": maid_name})

    # ── LLM Tools ──

    @llm_tool(**MC_MAID_STATUS)
    async def mc_maid_status(self, **_):
        return await _tools.do_maid_status(self)

    @llm_tool(**MC_SWITCH_FOLLOW)
    async def switch_follow(self, *, action="follow", **_):
        return await _tools.do_switch_follow(self, action=action)

    @llm_tool(**MC_SWITCH_SIT)
    async def switch_sit(self, *, action="sit", **_):
        return await _tools.do_switch_sit(self, action=action)

    @llm_tool(**MC_SWITCH_TASK)
    async def switch_task(self, *, task="", **_):
        return await _tools.do_switch_task(self, task=task)

    @llm_tool(**MC_SWITCH_SCHEDULE)
    async def switch_schedule(self, *, schedule="all", **_):
        return await _tools.do_switch_schedule(self, schedule=schedule)

    @llm_tool(**MC_EQUIP_ITEM)
    async def equip_item(self, *, item="", slot=None, **_):
        return await _tools.do_equip_item(self, item=item, slot=slot)

    @llm_tool(**MC_SEND_CHAT)
    async def mc_send_chat(self, *, message, maid_id=None, **_):
        return await _tools.do_send_chat(self, message=message, maid_id=maid_id)

    @llm_tool(**MC_GAME_CONTEXT)
    async def mc_game_context(self, category=None, **_):
        return await _tools.do_game_context(self, category=category)

    @llm_tool(**MC_USE_SKILL)
    async def use_skill(self, *, skill_name="", **_):
        return await _tools.do_use_skill(self, skill_name=skill_name)

    @llm_tool(**MC_EXECUTE_COMMAND)
    async def execute_command(self, *, command="", **_):
        return await _tools.do_execute_command(self, command=command)
