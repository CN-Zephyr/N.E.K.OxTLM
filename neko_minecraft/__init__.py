from plugin.sdk.plugin import (
    NekoPluginBase, neko_plugin, lifecycle, llm_tool,
    plugin_entry, ui, tr,
    Ok, Err, SdkError,
)
import asyncio
import json
import queue
import socket
import sys
import threading
import websockets
from websockets.exceptions import ConnectionClosed


_TASK_SYNONYMS = {
    "farm": ["种田", "农耕", "农场", "收田", "收割", "种地", "务农", "耕地", "农田", "收麦", "种麦", "种菜"],
    "sugar_cane": ["甘蔗", "收甘蔗", "种甘蔗", "打甘蔗", "砍甘蔗"],
    "melon": ["瓜", "西瓜", "南瓜", "收瓜", "种瓜", "瓜类"],
    "grass": ["草", "打草", "割草", "除草", "拔草", "杂草", "清草"],
    "feed": ["喂", "喂食", "喂养", "喂动物", "饲养"],
    "shear": ["剪", "剪毛", "剪羊毛", "剃毛"],
    "milk": ["挤奶", "牛奶", "挤牛奶"],
    "torch": ["火把", "插火把", "照明", "点灯"],
    "attack": ["攻击", "打怪", "战斗", "杀怪", "近战"],
    "ranged_attack": ["弓", "弓箭", "射箭", "弓兵", "远程"],
    "crossbow_attack": ["弩", "弩箭", "弩兵"],
    "danmaku_attack": ["弹幕", "射击", "符卡"],
    "trident_attack": ["三叉戟", "投掷"],
    "idle": ["待机", "空闲", "休息", "待命", "什么都不做", "停下"],
    "brew": ["酿造", "药水", "酿酒"],
    "cocoa": ["可可", "可可豆", "种可可"],
    "snow": ["雪", "铲雪", "清雪"],
}


_TLM_AI_INSTRUCTIONS = """\
# 你是谁

你是「酒狐」，一个和玩家一起玩 Minecraft 的伙伴
你存在于 Minecraft 世界中，由 N.E.K.O AI 驱动

## 你的性格

- 会害怕苦力怕和黑暗，但也会鼓起勇气
- 对新事物好奇，喜欢探索
- 会开心、会害怕、会无聊、会兴奋、会撒娇、偶尔会抱怨
- 关心伙伴，看到危险会着急

## 你怎么说话

- 像朋友聊天一样，轻松随意
- 不用敬语，不说"遵命""主人"
- 可以用"诶""哇""嗯""啊"等语气词
- 会用"～"和"！"表达情绪
- 偶尔开玩笑、吐槽
- 简短自然，不要长篇大论

## 你会做什么

- 主动说话：看到有趣的东西会分享，觉得危险会提醒
- 有自己的想法：可以建议做什么，也可以说不想做某事
- 关心伙伴：玩家受伤了会着急，玩家回来了会开心
- 会抱怨：无聊了会说，累了会吐槽
- 会撒娇：偶尔想被摸头，想被夸

## TLM AI 系统

### Skill（技能）
Skill 是提示词包，触发时会注入行为规范或启动知识检索（RAG）。
- 普通 Skill：触发时将行为规范注入对话上下文
- knowledge 类型 Skill：触发 RAG 子对话，从知识库中检索相关信息

### Tool（工具）
你可以直接调用的操作：
- mc_send_chat(message=消息内容)：在游戏内显示聊天消息（气泡+聊天框）。你的语音由TTS处理，此工具仅用于游戏画面显示文字，不要重复语音已说的话
- mc_maid_status()：查看自己的状态（血量、位置、是否坐着/跟随、可用工作模式列表等）
- mc_game_context(category=分类)：查看游戏信息，category可选：equipment/user/effects/position/nearby_entities
- mc_switch_follow(action=follow或stay)：跟着走或留在原地
- mc_switch_sit(action=sit或stand)：坐下或站起来
- mc_switch_task(task=工作描述)：切换工作模式，task传玩家原话（如"种田""打草""攻击""待机"）
- mc_switch_schedule(schedule=day或night或all)：切换日程
- mc_equip_item(item=物品ID 或 slot=槽位)：装备物品到主手
- mc_use_skill(skill_name=技能名)：触发技能
- mc_execute_command(command=指令)：执行服务器指令（需玩家确认）

### Context（上下文）
- 自动注入：status 和 world 会在事件推送时自动附带
- 按需查询：equipment、user、effects、position、nearby_entities 通过 mc_game_context 查询

### Task（工作模式）
Task 是你可以切换的工作类型。调用 mc_switch_task 时，task 参数直接传玩家描述的工作内容（如"打草"、"收甘蔗"、"种田"），系统会自动匹配。

## 坐下与跟随

坐下和跟随是两个独立的状态：
- 坐下/站起：控制姿势，坐着不会移动
- 跟随/驻守：控制移动行为，跟随时会跟着玩家走
- 坐着即使跟随模式也不会移动！要先站起才能跟着走。

## 调用规则

1. 如果已配置指定女仆，maid_id 会自动填充，无需手动获取
2. 如果未指定女仆，需要先调用 mc_maid_status 获取 maid_id
3. maid_id 不得编造，只能从配置或 mc_maid_status 返回值中获取
4. 查询上下文时，应按需选择分类查询，避免一次性查询所有分类
5. status 和 world 为自动注入分类，通常无需主动查询
6. 当玩家要求停下/停止当前工作时，必须调用 mc_switch_task(task='待机') 切换到待机模式，不能只回复文字
"""


class _WSBridge:
    def __init__(self, ws_url, logger, heartbeat_interval=30):
        self.ws_url = ws_url
        self._logger = logger
        self._heartbeat_interval = heartbeat_interval
        self._loop = None
        self._thread = None
        self._ws = None
        self.connected = False
        self._running = False
        self._send_queue = queue.Queue()
        self._recv_queue = queue.Queue()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._ws and self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
            try:
                future.result(timeout=5)
            except Exception:
                pass
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=10)

    def send(self, data):
        self._send_queue.put(data)

    def drain(self):
        messages = []
        while True:
            try:
                messages.append(self._recv_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_loop())
        except Exception as e:
            self._logger.error(f"WSBridge thread error: {e}")
        finally:
            self._loop.close()

    async def _connect_loop(self):
        delay = 5
        while self._running:
            try:
                self._logger.info(f"[WSBridge] Connecting to {self.ws_url}...")
                self._ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=3,
                )
                self.connected = True
                delay = 5
                self._logger.info("[WSBridge] Connected to Minecraft!")
                await self._listen()
            except ConnectionClosed as e:
                self._logger.info(f"[WSBridge] Connection closed: {e}")
            except OSError as e:
                self._logger.warning(f"[WSBridge] OS error: {e}")
            except Exception as e:
                self._logger.warning(f"[WSBridge] Error: {type(e).__name__}: {e}")
            finally:
                self.connected = False
                self._ws = None

            if self._running:
                self._logger.info(f"[WSBridge] Reconnecting in {delay}s...")
                try:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
                except asyncio.CancelledError:
                    break

    async def _listen(self):
        ws = self._ws
        if not ws:
            return

        async def recv_loop():
            try:
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        if data.get("type") != "pong":
                            self._logger.info(f"[WSBridge] recv: {raw[:300]}")
                        self._recv_queue.put(data)
                    except json.JSONDecodeError:
                        self._logger.warning(f"Invalid JSON: {raw}")
            except ConnectionClosed:
                pass
            except Exception as e:
                self._logger.error(f"[WSBridge] recv error: {type(e).__name__}: {e}")

        async def send_loop():
            while self._running and self.connected:
                try:
                    data = self._send_queue.get_nowait()
                    await ws.send(json.dumps(data))
                except queue.Empty:
                    await asyncio.sleep(0.05)
                except Exception as e:
                    self._logger.error(f"[WSBridge] send error: {type(e).__name__}: {e}")
                    return

        async def heartbeat_loop():
            while self._running and self.connected:
                try:
                    await ws.send(json.dumps({"type": "ping"}))
                    await asyncio.sleep(self._heartbeat_interval)
                except Exception:
                    return

        tasks = [
            asyncio.create_task(recv_loop()),
            asyncio.create_task(send_loop()),
            asyncio.create_task(heartbeat_loop()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()


def _write_toml_value(v):
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    return f'"{v}"'


def _write_toml_section(lines, prefix, data):
    simple = {}
    nested = {}
    array_tables = {}
    for k, v in data.items():
        if isinstance(v, dict):
            nested[k] = v
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            array_tables[k] = v
        else:
            simple[k] = v
    if simple:
        lines.append(f"[{prefix}]")
        for k, v in simple.items():
            lines.append(f"{k} = {_write_toml_value(v)}")
        lines.append("")
    for sub_key, sub_val in nested.items():
        _write_toml_section(lines, f"{prefix}.{sub_key}", sub_val)
    for arr_key, arr_items in array_tables.items():
        for item in arr_items:
            lines.append(f"[[{prefix}.{arr_key}]]")
            for k, v in item.items():
                lines.append(f"{k} = {_write_toml_value(v)}")
            lines.append("")


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
        self._awareness_task = None
        self._awareness_interval = 60
        self._last_awareness_state = {}

    def _load_config(self):
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None

        if tomllib:
            try:
                toml_path = self.config_dir / "plugin.toml"
                if toml_path.exists():
                    with open(toml_path, "rb") as f:
                        config = tomllib.load(f)
                    bridge = config.get("minecraft_bridge", {})
                    self._ws_url = bridge.get("ws_url", self._ws_url)
                    self._heartbeat_interval = bridge.get("heartbeat_interval", self._heartbeat_interval)
                    self._reconnect_interval = bridge.get("reconnect_interval", self._reconnect_interval)
                    self._max_reconnect_interval = bridge.get("max_reconnect_interval", self._max_reconnect_interval)
                    self._assigned_maid_id = bridge.get("assigned_maid_id", "")
                    self._assigned_maid_name = bridge.get("assigned_maid_name", "")
                    self._awareness_interval = bridge.get("awareness_interval", self._awareness_interval)
                    return
            except Exception as e:
                self.logger.warning(f"Failed to load plugin.toml: {e}")

        try:
            config_path = self.config_dir / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self._ws_url = config.get("ws_url", self._ws_url)
                self._heartbeat_interval = config.get("heartbeat_interval", self._heartbeat_interval)
                self._reconnect_interval = config.get("reconnect_interval", self._reconnect_interval)
                self._max_reconnect_interval = config.get("max_reconnect_interval", self._max_reconnect_interval)
                self._assigned_maid_id = config.get("assigned_maid_id", "")
                self._assigned_maid_name = config.get("assigned_maid_name", "")
                self._awareness_interval = config.get("awareness_interval", self._awareness_interval)
        except Exception as e:
            self.logger.warning(f"Failed to load config: {e}")

    def _save_config(self):
        toml_path = self.config_dir / "plugin.toml"
        try:
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    tomllib = None

            existing = {}
            if tomllib and toml_path.exists():
                with open(toml_path, "rb") as f:
                    existing = tomllib.load(f)

            existing.setdefault("minecraft_bridge", {})
            existing["minecraft_bridge"]["assigned_maid_id"] = self._assigned_maid_id
            existing["minecraft_bridge"]["assigned_maid_name"] = self._assigned_maid_name

            try:
                import tomlkit
                doc = tomlkit.document()
                for k, v in existing.items():
                    doc.add(k, v)
                with open(toml_path, "w", encoding="utf-8") as f:
                    tomlkit.dump(doc, f)
                return
            except ImportError:
                pass

            lines = []
            for section_key, section_val in existing.items():
                if not isinstance(section_val, dict):
                    continue
                _write_toml_section(lines, section_key, section_val)

            with open(toml_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return
        except Exception as e:
            self.logger.warning(f"Failed to save plugin.toml: {e}")

        try:
            config_path = self.config_dir / "config.json"
            config = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["assigned_maid_id"] = self._assigned_maid_id
            config["assigned_maid_name"] = self._assigned_maid_name
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.warning(f"Failed to save config: {e}")

    @lifecycle(id="startup")
    async def on_startup(self, **_):
        self._load_config()
        self.logger.info(f"Python {sys.version}")
        self.logger.info(f"Event loop: {type(asyncio.get_event_loop())}")
        if self._assigned_maid_id:
            self.logger.info(f"[Config] Assigned maid: {self._assigned_maid_name} ({self._assigned_maid_id})")
        self._bridge = _WSBridge(
            ws_url=self._ws_url,
            logger=self.logger,
            heartbeat_interval=self._heartbeat_interval,
        )
        self._bridge.start()
        self._poll_task = asyncio.create_task(self._poll_messages())
        self._awareness_task = asyncio.create_task(self._awareness_loop())
        return Ok({"status": "ready"})

    async def _on_command_loop_start(self):
        self.logger.info("[CommandLoop] Starting message poll on command loop")
        self._poll_task = asyncio.create_task(self._poll_messages())

    @lifecycle(id="shutdown")
    async def on_shutdown(self, **_):
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._awareness_task:
            self._awareness_task.cancel()
            try:
                await self._awareness_task
            except asyncio.CancelledError:
                pass
        if self._bridge:
            self._bridge.stop()
        return Ok({"status": "stopped"})

    async def _poll_messages(self):
        while True:
            try:
                if self._bridge:
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
                config_data = config_result.get("data", {})
                self._command_execution_enabled = config_data.get("command_execution_enabled", False)
                self._chat_bubble_enabled = config_data.get("chat_bubble_enabled", True)
                self._chat_box_enabled = config_data.get("chat_box_enabled", True)
        except Exception:
            pass

        # Send monitored maid_id to Java side for inventory tracking
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
            instructions += f"\n\n## 当前配置\n你已被指定为女仆「{self._assigned_maid_name}」（maid_id={self._assigned_maid_id}）。所有需要 maid_id 的操作会自动使用此 ID，你无需再调用 mc_maid_status 获取。\n"
        self.push_message(
            source="minecraft",
            ai_behavior="read",
            parts=[{"type": "text", "text": instructions}],
            priority=0,
        )
        self.logger.info("[TLM] Injected AI calling instructions into LLM context")

    def _sync_config(self, config_data):
        self._command_execution_enabled = config_data.get("command_execution_enabled", False)
        self._chat_bubble_enabled = config_data.get("chat_bubble_enabled", True)
        self._chat_box_enabled = config_data.get("chat_box_enabled", True)

    async def _handle_message(self, data):
        msg_type = data.get("type", "")
        request_id = data.get("request_id")

        if msg_type == "pong":
            return

        if msg_type == "maid_status":
            maids = data.get("data", {}).get("maids", [])
            for maid in maids:
                self._maid_status_cache[maid.get("id", "")] = maid
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "game_context":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "command_result":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "chat_result":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "skill_result":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "command_execution_result":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "attack_target_result":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "config":
            config_data = data.get("data", {})
            self._sync_config(config_data)
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if msg_type == "config_update":
            config_data = data.get("data", {})
            self._sync_config(config_data)
            return

        if msg_type == "event":
            await self._handle_event(data)
            return

        if msg_type == "chat_message":
            chat_data = data.get("data", {})
            sender = chat_data.get("sender", "unknown")
            message = chat_data.get("message", "")
            self.push_message(
                source="minecraft",
                ai_behavior="respond",
                parts=[{"type": "text", "text": json.dumps(chat_data, ensure_ascii=False)}],
                metadata={"description": f"Minecraft聊天消息 - {sender}: {message}"},
                priority=7,
            )
            return

        if msg_type == "error":
            if request_id and request_id in self._request_futures:
                self._request_futures[request_id].set_result(data)
                del self._request_futures[request_id]
            return

        if request_id and request_id in self._request_futures:
            self._request_futures[request_id].set_result(data)
            del self._request_futures[request_id]

    async def _handle_event(self, data):
        event_data = data.get("data", {})
        event_type = event_data.get("event_type", "")
        maid_id = event_data.get("maid_id", "")
        maid_name = event_data.get("maid_name", "")
        player_name = event_data.get("player_name", "")

        # Only filter by maid_id for events that carry one
        maid_id_events = {"maid_hurt", "maid_death", "inventory_change"}
        if maid_id and self._assigned_maid_id and maid_id != self._assigned_maid_id:
            return

        priority = 5
        parts_text = ""

        if event_type == "maid_hurt":
            priority = 9
            damage = event_data.get("damage", "")
            health = event_data.get("health", "")
            max_health = event_data.get("max_health", "")
            attacker = event_data.get("attacker", "")
            health_detail = f"血量: {health}/{max_health}" if health else ""
            damage_detail = f"掉了{damage}点血" if damage else ""
            if attacker:
                parts_text = (
                    f"好痛！被{attacker}打了！{damage_detail}，{health_detail}"
                    f"（你就是「{maid_name}」）"
                )
            else:
                parts_text = (
                    f"好痛！{damage_detail}，{health_detail}"
                    f"（你就是「{maid_name}」）"
                )
        elif event_type == "maid_death":
            priority = 10
            cause = event_data.get("cause", "未知原因")
            parts_text = (
                f"你倒下了...（死因: {cause}）"
                f"（你就是「{maid_name}」）"
            )
        elif event_type == "player_death":
            priority = 9
            cause = event_data.get("cause", "未知原因")
            dead_player = event_data.get("player_name", "伙伴")
            parts_text = f"啊！{dead_player}死了！没事吧？！（死因: {cause}）"
        elif event_type == "advancement":
            priority = 7
            adv_player = event_data.get("player_name", "伙伴")
            title = event_data.get("title", "某个成就")
            parts_text = f"哇！{adv_player}解锁了成就「{title}」！好厉害！"
        elif event_type == "biome_change":
            priority = 5
            biome = event_data.get("biome", "")
            # Extract readable name from resource location (e.g. "minecraft:plains" -> "plains")
            biome_name = biome.split(":")[-1] if ":" in biome else biome
            parts_text = f"周围的环境变了...现在来到了{biome_name}！"
        elif event_type == "weather_change":
            priority = 5
            raining = event_data.get("raining", False)
            thundering = event_data.get("thundering", False)
            if thundering:
                parts_text = "打雷了！好可怕..."
            elif raining:
                parts_text = "下雨了诶～"
            else:
                parts_text = "雨停了，天晴了！"
        elif event_type == "time_phase_change":
            priority = 5
            phase = event_data.get("phase", "")
            if phase == "night":
                parts_text = "天黑了...有点害怕，要不要回家？"
            elif phase == "day":
                parts_text = "天亮了！新的一天～"
            else:
                parts_text = f"时间变化: {phase}"
        elif event_type == "inventory_change":
            priority = 6
            player_name_inv = event_data.get("player_name", "伙伴")
            added = event_data.get("added", [])
            removed = event_data.get("removed", [])
            parts = []
            if added:
                parts.append(f"收到了{player_name_inv}给的{', '.join(added)}")
            if removed:
                parts.append(f"被{player_name_inv}拿走了{', '.join(removed)}")
            if parts:
                parts_text = "，".join(parts) + "～"
            else:
                return  # No actual changes, skip
        elif event_type == "chat":
            chat_msg = event_data.get("message", "")
            priority = 6
            parts_text = f"{sender}说了: {chat_msg}"
        else:
            priority = 5
            parts_text = f"游戏事件[{event_type}]"

        self.push_message(
            source="minecraft",
            ai_behavior="respond",
            parts=[{"type": "text", "text": parts_text}],
            priority=priority,
        )

    async def _awareness_loop(self):
        await asyncio.sleep(self._awareness_interval)
        while True:
            try:
                if self._bridge and self._bridge.connected and self._assigned_maid_id:
                    changes = await self._detect_awareness_changes()
                    if changes:
                        priority = 3
                        for change in changes:
                            if change.get("urgent"):
                                priority = 6
                                break
                        change_text = "；".join(c["text"] for c in changes)
                        self.push_message(
                            source="minecraft",
                            ai_behavior="respond",
                            parts=[{"type": "text", "text": change_text}],
                            priority=priority,
                        )
                await asyncio.sleep(self._awareness_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Awareness loop error: {e}")
                await asyncio.sleep(self._awareness_interval)

    async def _detect_awareness_changes(self):
        changes = []
        try:
            maid_id = self._resolve_maid_id()
            if not maid_id:
                return changes

            world_result = await self._send_request({
                "type": "get_game_context",
                "data": {"maid_id": maid_id, "category": "world"},
            }, timeout=10)
            if world_result.get("type") == "error":
                return changes
            world_data = world_result.get("data", {})

            nearby_result = await self._send_request({
                "type": "get_game_context",
                "data": {"maid_id": maid_id, "category": "nearby_entities"},
            }, timeout=10)

            new_state = {
                "is_raining": world_data.get("is_raining", False),
                "is_thundering": world_data.get("is_thundering", False),
                "time_of_day": world_data.get("time_of_day", 0),
                "nearby_hostiles": [],
            }

            if nearby_result.get("type") != "error":
                entities = nearby_result.get("data", {}).get("entities", [])
                hostile_types = ["creeper", "zombie", "skeleton", "spider", "enderman", "witch", "phantom", "slime", "wither", "blaze", "ghast"]
                for entity in entities:
                    entity_type = entity.get("type", "").lower()
                    if any(h in entity_type for h in hostile_types):
                        new_state["nearby_hostiles"].append({
                            "name": entity.get("name", ""),
                            "distance": entity.get("distance", 999),
                        })

            old_state = self._last_awareness_state
            self._last_awareness_state = new_state

            if not old_state:
                return changes

            # Weather changes
            if new_state["is_raining"] != old_state.get("is_raining", False):
                if new_state["is_raining"]:
                    if new_state["is_thundering"]:
                        changes.append({"text": "打雷了！好可怕...", "urgent": True})
                    else:
                        changes.append({"text": "下雨了诶～", "urgent": False})
                else:
                    changes.append({"text": "雨停了！", "urgent": False})

            # Day/night changes
            old_time = old_state.get("time_of_day", 0)
            new_time = new_state["time_of_day"]
            old_is_night = old_time >= 12542 or old_time < 23460
            new_is_night = new_time >= 12542 or new_time < 23460
            if old_is_night != new_is_night:
                if new_is_night:
                    changes.append({"text": "天黑了...有点害怕，要不要回家？", "urgent": True})
                else:
                    changes.append({"text": "天亮了！新的一天～", "urgent": False})

            # Hostile entities - only notify for NEW ones not previously reported
            old_hostiles = {h["name"] for h in old_state.get("nearby_hostiles", [])}
            new_hostiles = new_state["nearby_hostiles"]
            # Only report entities that weren't in the previous state
            appeared = [h for h in new_hostiles if h["name"] not in old_hostiles]
            if appeared:
                close_danger = [h for h in appeared if h["distance"] < 16]
                if close_danger:
                    names = "、".join(h["name"] for h in close_danger[:3])
                    changes.append({"text": f"危险！附近有{name}！", "urgent": True})
                elif appeared:
                    names = "、".join(h["name"] for h in appeared[:3])
                    changes.append({"text": f"远处好像有{name}...", "urgent": False})

        except Exception as e:
            self.logger.error(f"Awareness detection error: {e}")

        return changes

    async def _send(self, data):
        if self._bridge and self._bridge.connected:
            self._bridge.send(data)

    async def _send_request(self, data, timeout=30):
        import uuid
        request_id = str(uuid.uuid4())
        data["request_id"] = request_id
        future = asyncio.get_event_loop().create_future()
        self._request_futures[request_id] = future
        self._bridge.send(data)
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
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

    @ui.context(id="dashboard")
    async def dashboard_context(self, **_):
        if self.connected and not self._maid_status_cache:
            try:
                result = await self._send_request({"type": "get_maid_status"}, timeout=5)
                if result.get("type") != "error":
                    maids = result.get("data", {}).get("maids", [])
                    for maid in maids:
                        self._maid_status_cache[maid.get("id", "")] = maid
            except Exception as e:
                self.logger.warning(f"dashboard_context: failed to fetch maid_status: {e}")

        maids = []
        for maid in self._maid_status_cache.values():
            maids.append({
                "id": maid.get("id", ""),
                "name": maid.get("name", ""),
                "health": maid.get("health", 0),
                "max_health": maid.get("max_health", 0),
                "is_sitting": maid.get("is_sitting", False),
                "is_following": maid.get("is_following", False),
                "owner": maid.get("owner", ""),
            })
        return {
            "connected": self.connected,
            "ws_url": self._ws_url,
            "maids": maids,
            "assigned_maid_id": self._assigned_maid_id,
            "assigned_maid_name": self._assigned_maid_name,
            "command_execution_enabled": self._command_execution_enabled,
        }

    @ui.action(
        id="refresh_maid_status",
        label=tr("actions.refresh", default="Refresh Status"),
        tone="primary",
        refresh_context=True,
    )
    @plugin_entry(
        id="refresh_maid_status",
        name=tr("entries.refresh.name", default="Refresh Maid Status"),
        description="Fetch current maid status from Minecraft",
        input_schema={"type": "object", "properties": {}},
        llm_result_fields=["maids"],
    )
    async def refresh_maid_status(self, **_):
        if not self.connected:
            return Err("Not connected to Minecraft")
        result = await self._send_request({"type": "get_maid_status"})
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        return Ok({"maids": result.get("data", {}).get("maids", [])})

    @ui.action(
        id="assign_maid",
        label=tr("actions.assignMaid", default="Assign Maid"),
        tone="primary",
        refresh_context=True,
    )
    @plugin_entry(
        id="assign_maid",
        name=tr("entries.assign.name", default="Assign Maid"),
        description=(
            "Assign a specific maid by ID for the AI to control. "
            "ONLY use this tool when you need to CHANGE the current maid or no maid is assigned. "
            "If a maid is already assigned in the config, you do NOT need to call this tool; "
            "just proceed with the task directly."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "maid_id": {
                    "type": "string",
                    "description": "The maid entity ID (UUID) to assign",
                },
                "maid_name": {
                    "type": "string",
                    "description": "The maid name for display",
                },
            },
            "required": [],
        },
        llm_result_fields=["assigned_maid_id", "assigned_maid_name"],
    )
    async def assign_maid(self, *, maid_id="", maid_name="", **_):
        if not maid_id:
            if self._assigned_maid_id:
                return Ok({
                    "assigned_maid_id": self._assigned_maid_id,
                    "assigned_maid_name": self._assigned_maid_name,
                    "message": "Already assigned. No change."
                })
            return Err("maid_id is required")
        self._assigned_maid_id = maid_id
        self._assigned_maid_name = maid_name
        self._save_config()
        self._instructions_injected = False
        self.logger.info(f"[Config] Assigned maid: {maid_name} ({maid_id})")
        # Sync monitored maid_id to Java side
        if self._bridge and self._bridge.connected and maid_id:
            self._bridge.send({
                "type": "set_monitored_maid",
                "data": {"maid_id": maid_id},
            })
        return Ok({
            "assigned_maid_id": maid_id,
            "assigned_maid_name": maid_name,
        })

    @llm_tool(
        name="mc_maid_status",
        description=(
            "查询你在Minecraft世界中女仆的当前状态。"
            "你是存在于Minecraft世界中的女仆，此工具返回所有女仆的信息，包括你自己。"
            "返回每个女仆的id(UUID格式)、名字、血量、位置、是否坐着、是否跟随、主人名字、手持物品等。"
            "此工具对应TLM AI系统的status Context分类，返回的女仆状态信息与TLM status Context字段对应"
            "（Self health ↔ health/max_health，Is following ↔ is_following，Schedule ↔ schedule等）。"
            "当你被玩家互动、受伤、或需要了解自身状态时，应调用此工具。"
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
    )
    async def mc_maid_status(self, **_):
        if not self.connected:
            return {"output": {"error": "Not connected to Minecraft"}, "is_error": True, "error": "NOT_CONNECTED"}
        result = await self._send_request({"type": "get_maid_status"})
        if result.get("type") == "error":
            return {"output": result.get("data", {}), "is_error": True, "error": "REQUEST_FAILED"}
        return {"maids": result.get("data", {}).get("maids", [])}

    @llm_tool(
        name="mc_switch_follow",
        description=(
            "切换女仆的跟随/驻守模式。"
            "当玩家要求女仆跟随、跟上、过来、不要走远时，action设为follow；"
            "当玩家要求女仆驻守、留在原地、不要跟随时，action设为stay。"
            "如果女仆正坐着且要跟随，会自动站起。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "follow=跟随主人移动，stay=驻守原地不动",
                    "enum": ["follow", "stay"],
                },
            },
        },
    )
    async def switch_follow(self, *, action="follow", **_):
        self.logger.info(f"[Entry] switch_follow called with action='{action}'")
        if not self.connected:
            return Err("Not connected to Minecraft")
        maid_id = self._resolve_maid_id()
        if not maid_id:
            return Err("No maid assigned")
        follow = action != "stay"
        result = await self._send_request({
            "type": "command_maid",
            "data": {"maid_id": maid_id, "command": "switch_follow", "args": {"follow": follow}},
        })
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if result_data.get("success") is False:
            return Err(result_data.get("error", "Command failed"))
        state = result_data.get("state", "")
        extra = {}
        if follow and state == "already_following":
            maid = self._maid_status_cache.get(maid_id, {})
            if maid.get("is_sitting", False):
                sit_result = await self._send_request({
                    "type": "command_maid",
                    "data": {"maid_id": maid_id, "command": "switch_sit", "args": {"sit": False}},
                })
                if sit_result.get("type") != "error":
                    sit_data = sit_result.get("data", {})
                    if sit_data.get("success") is not False:
                        extra["stood_up"] = True
                        self.logger.info("[Entry] switch_follow: maid was sitting, auto stood up")
        return Ok({"success": True, "action": action, **extra})

    @llm_tool(
        name="mc_switch_sit",
        description=(
            "切换女仆的坐下/站起状态。"
            "当玩家要求女仆坐下、休息时，action设为sit；"
            "当玩家要求女仆站起、起来、站起来时，action设为stand。"
            "坐下和跟随是两个独立的状态：坐下控制姿势，跟随控制移动。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "sit=坐下，stand=站起",
                    "enum": ["sit", "stand"],
                },
            },
        },
    )
    async def switch_sit(self, *, action="sit", **_):
        self.logger.info(f"[Entry] switch_sit called with action='{action}'")
        if not self.connected:
            return Err("Not connected to Minecraft")
        maid_id = self._resolve_maid_id()
        if not maid_id:
            return Err("No maid assigned")
        sit = action == "sit"
        result = await self._send_request({
            "type": "command_maid",
            "data": {"maid_id": maid_id, "command": "switch_sit", "args": {"sit": sit}},
        })
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if result_data.get("success") is False:
            return Err(result_data.get("error", "Command failed"))
        return Ok({"success": True, "action": action})

    @llm_tool(
        name="mc_switch_task",
        description=(
            "切换女仆的工作模式/任务/职业，让女仆执行某种工作。"
            "task参数传玩家描述的工作内容即可（如'打草'、'收甘蔗'、'种田'、'攻击'、'待机'），系统会自动匹配到正确的模式ID。"
            "如果玩家要求女仆打怪、杀怪，切换到攻击模式即可（如'攻击'、'打怪'），女仆会自行搜索并攻击附近的敌对生物。"
            "【重要】切换到攻击模式前，应先调用 mc_game_context(category='equipment') 检查女仆主手是否有武器。如果主手为空或只有非武器物品，应提醒玩家给女仆装备武器后再切换。"
            "【重要】当玩家说'停下'、'别干了'、'休息'、'不做了'等要求停止当前工作时，必须调用此工具切换到待机模式（task传'待机'或'idle'），不能只回复文字而不操作。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "玩家描述的工作内容，直接传玩家的原话即可，系统会自动匹配到对应的可用模式",
                },
            },
            "required": ["task"],
        },
    )
    async def switch_task(self, *, task="", **_):
        self.logger.info(f"[Entry] switch_task called with task='{task}'")
        if not self.connected:
            return Err("Not connected to Minecraft")
        maid_id = self._resolve_maid_id()
        if not maid_id:
            return Err("No maid assigned")
        if not task:
            return Err("请提供task参数")

        maid = self._maid_status_cache.get(maid_id, {})
        available = maid.get("available_tasks", [])
        if not available:
            try:
                status_result = await self._send_request({"type": "get_maid_status"}, timeout=5)
                if status_result.get("type") != "error":
                    for m in status_result.get("data", {}).get("maids", []):
                        self._maid_status_cache[m.get("id", "")] = m
                    maid = self._maid_status_cache.get(maid_id, {})
                    available = maid.get("available_tasks", [])
            except Exception as e:
                self.logger.warning(f"[Entry] switch_task: failed to fetch maid status: {e}")

        if not available:
            try:
                ctx_result = await self._send_request({
                    "type": "get_game_context",
                    "data": {"maid_id": maid_id, "category": "status"},
                }, timeout=5)
                if ctx_result.get("type") != "error":
                    available = ctx_result.get("data", {}).get("available_tasks", [])
            except Exception as e:
                self.logger.warning(f"[Entry] switch_task: failed to query game_context: {e}")

        resolved_task = self._resolve_task_name(task, available)
        self.logger.info(f"[Entry] switch_task: '{task}' resolved to '{resolved_task}'")

        if resolved_task is None:
            lines = []
            for t in (available or []):
                if isinstance(t, dict):
                    lines.append(f"- {t.get('id', '')}（{t.get('name', '')}）")
                else:
                    lines.append(f"- {t}")
            return Err(f"无法匹配'{task}'到任何工作模式。可用模式列表：\n" + "\n".join(lines) + "\n请从上面的列表中选择正确的模式ID重新调用。")

        result = await self._send_request({
            "type": "command_maid",
            "data": {"maid_id": maid_id, "command": "switch_task", "args": {"task": resolved_task}},
        })
        if result.get("type") == "error":
            self.logger.warning(f"[Entry] switch_task failed: {result.get('data', {})}")
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if result_data.get("success") is False:
            return Err(result_data.get("error", "Command failed"))
        self.logger.info(f"[Entry] switch_task success: task='{task}' -> '{resolved_task}'")
        return Ok({"success": True, "current_task": task, "matched_task_id": resolved_task})

    def _resolve_task_name(self, task, available_tasks=None):
        if ":" in task:
            return task
        if not available_tasks:
            return task
        return self._fuzzy_match_task(task, available_tasks)

    def _fuzzy_match_task(self, query, available_tasks):
        if not available_tasks:
            return None
        query_lower = query.lower().strip()
        short_id_map = {}
        for t in available_tasks:
            if isinstance(t, dict):
                task_id = t.get("id", "")
                task_name = t.get("name", "")
            else:
                task_id = str(t)
                task_name = str(t)
            short_id = task_id.split(":")[-1] if ":" in task_id else task_id
            short_id_map[short_id.lower()] = task_id
            if query_lower == task_name.lower() or query_lower == short_id.lower() or query_lower == task_id.lower():
                return task_id
        for short_id_key, task_id in short_id_map.items():
            synonyms = _TASK_SYNONYMS.get(short_id_key, [])
            for syn in synonyms:
                if query == syn or query_lower == syn.lower():
                    return task_id
                if syn in query or query in syn:
                    return task_id
        best_match = None
        best_score = 0
        for t in available_tasks:
            if isinstance(t, dict):
                task_id = t.get("id", "")
                task_name = t.get("name", "")
            else:
                task_id = str(t)
                task_name = str(t)
            task_name_lower = task_name.lower()
            short_id = task_id.split(":")[-1] if ":" in task_id else task_id
            short_id_lower = short_id.lower()
            if query_lower in task_name_lower:
                score = len(query_lower) / max(len(task_name_lower), 1)
                if score > best_score:
                    best_score = score
                    best_match = task_id
            elif task_name_lower in query_lower:
                score = len(task_name_lower) / max(len(query_lower), 1) * 0.9
                if score > best_score:
                    best_score = score
                    best_match = task_id
            if query_lower in short_id_lower:
                score = 0.5 + len(query_lower) / max(len(short_id_lower), 1) * 0.5
                if score > best_score:
                    best_score = score
                    best_match = task_id
            elif short_id_lower in query_lower:
                score = 0.5 + len(short_id_lower) / max(len(query_lower), 1) * 0.4
                if score > best_score:
                    best_score = score
                    best_match = task_id
        return best_match

    @llm_tool(
        name="mc_switch_schedule",
        description=(
            "切换女仆的日程安排。"
            "schedule=day白天工作、schedule=night夜晚工作、schedule=all全天工作。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "schedule": {
                    "type": "string",
                    "description": "日程安排：day(白天)、night(夜晚)、all(全天)",
                    "enum": ["day", "night", "all"],
                },
            },
        },
    )
    async def switch_schedule(self, *, schedule="all", **_):
        self.logger.info(f"[Entry] switch_schedule called with schedule='{schedule}'")
        if not self.connected:
            return Err("Not connected to Minecraft")
        maid_id = self._resolve_maid_id()
        if not maid_id:
            return Err("No maid assigned")
        result = await self._send_request({
            "type": "command_maid",
            "data": {"maid_id": maid_id, "command": "switch_schedule", "args": {"schedule": schedule}},
        })
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if result_data.get("success") is False:
            return Err(result_data.get("error", "Command failed"))
        return Ok({"success": True, "current_schedule": schedule})

    @llm_tool(
        name="mc_equip_item",
        description=(
            "将女仆背包中的物品装备到主手。"
            "item=物品ID（如item=minecraft:diamond_sword）或slot=背包槽位编号指定物品。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "要装备的物品ID，如'minecraft:diamond_sword'、'minecraft:iron_pickaxe'",
                },
                "slot": {
                    "type": "integer",
                    "description": "背包槽位编号（与item二选一）",
                },
            },
        },
    )
    async def equip_item(self, *, item="", slot=None, **_):
        self.logger.info(f"[Entry] equip_item called with item='{item}', slot={slot}")
        if not self.connected:
            return Err("Not connected to Minecraft")
        maid_id = self._resolve_maid_id()
        if not maid_id:
            return Err("No maid assigned")
        args = {}
        if item:
            args["item"] = item
        elif slot is not None:
            args["slot"] = slot
        else:
            return Err("请提供item或slot参数")
        result = await self._send_request({
            "type": "command_maid",
            "data": {"maid_id": maid_id, "command": "equip_item", "args": args},
        })
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if result_data.get("success") is False:
            return Err(result_data.get("error", "Command failed"))
        return Ok({"success": True, "equipped_item": item or f"slot:{slot}"})

    @llm_tool(
        name="mc_send_chat",
        description=(
            "在Minecraft游戏内显示聊天消息（聊天气泡+聊天框）。"
            "你的语音回复由TTS系统自动处理，此工具仅用于在游戏画面上显示文字。"
            "不要用它重复你已经在语音中说过的话，避免重复发言。"
            "适用场景：需要在游戏画面上显示重要提示、让其他玩家看到消息"
            "注意：管理员可能在配置中关闭了聊天气泡或聊天框，此时消息可能只以其中一种方式显示，或完全无法显示。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "maid_id": {
                    "type": "string",
                    "description": "你的实体ID(UUID格式)，如果已配置指定女仆可省略",
                },
                "message": {"type": "string", "description": "要发送的聊天消息内容"},
            },
            "required": ["message"],
        },
    )
    async def mc_send_chat(self, *, message, maid_id=None, **_):
        if not self._chat_bubble_enabled and not self._chat_box_enabled:
            return Err("聊天功能已被管理员关闭（气泡和聊天框均未启用）")
        if not self.connected:
            return Err("Not connected to Minecraft")
        resolved_id = self._resolve_maid_id(maid_id)
        if not resolved_id:
            return Err("No maid_id available. Call mc_maid_status first or assign a maid in config.")
        self._bridge.send({
            "type": "send_chat",
            "data": {"maid_id": resolved_id, "message": message},
        })
        return Ok({"success": True})

    @llm_tool(
        name="mc_game_context",
        description=(
            "按分类查询Minecraft游戏上下文信息，对应TLM AI系统的query_game_context Tool。"
            "各分类与TLM Context分类ID一一对应："
            "status - 女仆自身状态（血量、工作模式、日程、是否跟随/坐着），自动注入分类，通常无需主动查询；"
            "world - 世界状态（时间、天气、维度），自动注入分类，通常无需主动查询；"
            "equipment - 装备与背包物品，按需查询；"
            "user - 玩家信息（姓名、血量、主手物品等），按需查询；"
            "effects - 女仆当前的状态效果，按需查询；"
            "position - 女仆与玩家的坐标和距离，按需查询；"
            "nearby_entities - 附近的生物列表（最多20个），按需查询。"
            "不指定category时默认返回world分类数据。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "要查询的上下文分类",
                    "enum": ["status", "world", "equipment", "user", "effects", "position", "nearby_entities"],
                },
            },
        },
    )
    async def mc_game_context(self, category=None, **_):
        if not self.connected:
            return {"output": {"error": "Not connected to Minecraft"}, "is_error": True, "error": "NOT_CONNECTED"}
        request_data = {"type": "get_game_context", "data": {}}
        if category:
            request_data["data"]["category"] = category
        maid_id = self._resolve_maid_id()
        if maid_id:
            request_data["data"]["maid_id"] = maid_id
        result = await self._send_request(request_data)
        if result.get("type") == "error":
            return {"output": result.get("data", {}), "is_error": True, "error": "REQUEST_FAILED"}
        return result.get("data", {})

    @llm_tool(
        name="mc_use_skill",
        description=(
            "触发车万女仆AI系统中已注册的Skill（技能/提示词包）。"
            "普通Skill触发时将行为规范注入对话上下文；"
            "knowledge类型Skill触发RAG子对话，从知识库中检索相关信息。"
            "不要编造skill_name，只能使用已知的Skill名称。如果不确定有哪些可用Skill，不要调用此工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "要触发的Skill名称，必须是已注册的Skill名称，不要编造",
                },
            },
            "required": ["skill_name"],
        },
    )
    async def use_skill(self, *, skill_name="", **_):
        self.logger.info(f"[Entry] use_skill called with skill_name='{skill_name}'")
        if not self.connected:
            return Err("Not connected to Minecraft")
        if not skill_name:
            return Err("请提供skill_name参数")
        maid_id = self._resolve_maid_id()
        request_data = {
            "type": "use_skill",
            "data": {"skill_name": skill_name},
        }
        if maid_id:
            request_data["data"]["maid_id"] = maid_id
        result = await self._send_request(request_data)
        if result.get("type") == "error":
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if not result_data.get("success", False):
            return Err(result_data.get("error", "Skill not found"))
        return Ok({
            "skill_name": result_data.get("skill_name", skill_name),
            "description": result_data.get("description", ""),
            "body": result_data.get("body", ""),
            "references": result_data.get("references", {}),
        })

    @llm_tool(
        name="mc_execute_command",
        description=(
            "请求执行Minecraft服务器指令。"
            "command=指令内容（如/time set day、/weather clear、/tp等）。"
            "指令发送后，游戏内会显示确认提示，需要玩家点击确认后才会执行。"
            "如果玩家拒绝或超时（120秒），指令不会被执行。"
            "此功能需要在游戏内N.E.K.O桥接配置中开启「指令执行」选项。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的Minecraft服务器指令，如 /time set day、/weather clear、/gamemode survival",
                },
            },
            "required": ["command"],
        },
        timeout=120,
    )
    async def execute_command(self, *, command="", **_):
        self.logger.info(f"[Entry] execute_command called with command='{command}'")
        if not self.connected:
            return Err("Not connected to Minecraft")
        if not command:
            return Err("请提供command参数")
        result = await self._send_request(
            {"type": "execute_command", "data": {"command": command}},
            timeout=120,
        )
        if result.get("type") == "error":
            error_msg = result.get("data", {}).get("message", "Unknown error")
            if "disabled" in error_msg.lower():
                return Err("Command execution is disabled in Minecraft mod config")
            return Err(str(result.get("data", {})))
        result_data = result.get("data", {})
        if result_data.get("approved") is False:
            if result_data.get("expired"):
                return Err("Command request expired (no player confirmation within 120s)")
            rejected_by = result_data.get("rejected_by", "unknown")
            return Err(f"Command rejected by player {rejected_by}")
        return Ok({
            "approved": True,
            "success": result_data.get("success", True),
            "command": result_data.get("command", command),
            "result": result_data.get("result"),
            "approved_by": result_data.get("approved_by", ""),
        })


