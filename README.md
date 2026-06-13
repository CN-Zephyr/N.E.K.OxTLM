# N.E.K.OxTLM

一个联动插件，为"车万女仆"（Touhou Little Maid）模组与 N.E.K.O 搭建兼容与交互桥梁，可借助 N.E.K.O 通过自然语言控制游戏内女仆行为。

> 新手上路？请阅读 [使用教程](使用教程.md)

## 功能特性

- **伙伴型 AI 女仆** — 女仆不再是仆从，而是陪你一起玩的伙伴。会害怕、会撒娇、会吐槽、会关心你
- **WebSocket 桥接** — 在 Minecraft 服务端启动 WebSocket 服务器，N.E.K.O 客户端通过 WebSocket 协议实时交互
- **女仆状态查询** — 获取所有女仆的生命值、位置、任务、装备等详细信息
- **女仆行为控制** — 通过自然语言指令控制女仆的跟随/停留、坐下/站起、切换任务、切换日程、装备物品等
- **游戏事件推送** — 将女仆受伤/死亡、玩家死亡、天气变化、昼夜变化、群系切换、成就解锁、背包物品变化等事件实时推送给 N.E.K.O
- **定时感知系统** — 每5秒轮询游戏状态，检测玩家血量/着火/溺水、附近敌对生物、矿洞暗处、食物分享等，主动关心或提醒
- **陪玩式感知增强** — 记录最近共同经历，推断玩家当前活动状态，并在长时间稳定游玩时低频主动陪一句
- **上下文注入** — 持续更新玩家手持物品、附近结构/地标等信息到 LLM 上下文，为主动搭话提供素材
- **Push 聚合与节流** — 低优先级上下文会短窗口合并后按时间顺序注入，紧急提醒和聊天消息仍会立即响应
- **女仆聊天** — 让女仆在游戏内发送聊天消息并显示聊天气泡（TTS 由 N.E.K.O 处理，避免重复）(llm自主判断)
- **技能系统** — 查询和使用车万女仆的 AI 技能（Skill）
- **指令执行（需确认）** — N.E.K.O 可请求执行 Minecraft 指令，但需要玩家在游戏内点击确认，防止滥用

## 环境要求

| 依赖                        | 版本                     |
| ------------------------- | ---------------------- |
| Minecraft                 | 1.21.1                 |
| NeoForge                  | 21.1.172+              |
| Java                      | 21                     |
| 车万女仆 (Touhou Little Maid) | 1.5.3+（可选，但无此模组本插件无意义） |

## 安装

1. 确保已安装 Minecraft 1.21.1 + NeoForge
2. 安装车万女仆模组
3. 将本模组 JAR 文件放入 `mods` 文件夹
4. 启动游戏

## 配置

在游戏内通过 Mod 菜单或配置文件 `neko_tlm_bridge-common.toml` 进行配置：

| 配置项                       | 默认值     | 说明                                         |
| ------------------------- | ------- | ------------------------------------------ |
| `nekoModeEnabled`         | `true`  | 启用 N.E.K.O 模式，开启后女仆的 AI 对话由 N.E.K.O 驱动     |
| `websocket.port`          | `48920` | WebSocket 服务器监听端口                          |
| `ignoreTlmBuiltinContext` | `true`  | 忽略车万女仆内置 AI 上下文，防止与 N.E.K.O 冲突             |
| `eventPushEnabled`        | `true`  | 启用游戏事件推送，将游戏事件通过 WebSocket 推送给 N.E.K.O     |
| `commandExecutionEnabled` | `false` | 启用指令执行，允许 N.E.K.O 请求执行 Minecraft 指令（需玩家确认） |
| `weatherEventEnabled`     | `true`  | 启用天气变化事件推送                                 |
| `timeEventEnabled`        | `true`  | 启用昼夜变化事件推送                                 |

## WebSocket 协议

本模组在 `127.0.0.1:{port}` 上启动 WebSocket 服务器，仅接受本地连接。所有消息均为 JSON 格式。

### 请求消息

客户端发送的消息需包含 `type` 字段和可选的 `request_id` 字段：

```json
{
  "type": "消息类型",
  "request_id": "可选的请求ID，用于匹配响应",
  "data": { ... }
}
```

#### 支持的请求类型

| 类型                 | 说明                | data 字段                                             |
| ------------------ | ----------------- | --------------------------------------------------- |
| `ping`             | 心跳检测              | 无                                                   |
| `get_maid_status`  | 获取所有女仆状态          | 无                                                   |
| `command_maid`     | 控制女仆行为            | `maid_id`, `command`, `args`                        |
| `send_chat`        | 让女仆发送聊天消息         | `maid_id`, `message`                                |
| `get_game_context` | 获取游戏上下文           | `category`, `maid_id`(可选)                           |
| `use_skill`        | 使用/查询技能           | `skill_name`, `maid_id`(可选)                         |
| `attack_target`    | 指定女仆攻击目标（实验性，未暴露给LLM） | `maid_id`, `target_entity_id` 或 `target_entity_ids` |
| `execute_command`  | 请求执行 Minecraft 指令 | `command`                                           |
| `get_config`       | 获取当前配置            | 无                                                   |
| `set_monitored_maid` | 设置监控的女仆ID（用于背包物品变化检测） | `maid_id`                           |

#### command\_maid 支持的指令

| command           | args                                 | 说明      |
| ----------------- | ------------------------------------ | ------- |
| `switch_follow`   | `{"follow": true/false}`             | 切换跟随/停留 |
| `switch_sit`      | `{"sit": true/false}`                | 切换坐下/站起 |
| `switch_task`     | `{"task": "任务ID"}`                   | 切换女仆任务  |
| `switch_schedule` | `{"schedule": "DAY/NIGHT/ALL"}`      | 切换日程模式  |
| `equip_item`      | `{"slot": 槽位号}` 或 `{"item": "物品ID"}` | 装备物品到主手 |

#### get\_game\_context 支持的类别

| category          | 说明               |
| ----------------- | ---------------- |
| `world`           | 世界信息（时间、天气、在线玩家） |
| `status`          | 女仆状态（生命值、任务、日程）  |
| `equipment`       | 女仆装备与背包          |
| `user`            | 女仆主人信息（含着火/溺水状态） |
| `effects`         | 女仆当前药水效果         |
| `position`        | 女仆与主人的位置（含亮度/地下） |
| `nearby_entities` | 女仆附近实体           |
| `awareness`       | 感知系统综合数据（一次返回所有 awareness 需要的信息） |

### 响应消息

服务端返回的消息格式：

```json
{
  "type": "响应类型",
  "request_id": "对应的请求ID",
  "data": { ... }
}
```

#### 响应类型

| 类型                         | 说明               |
| -------------------------- | ---------------- |
| `pong`                     | 心跳响应             |
| `maid_status`              | 女仆状态数据           |
| `command_result`           | 指令执行结果           |
| `chat_result`              | 聊天发送结果           |
| `game_context`             | 游戏上下文数据          |
| `skill_result`             | 技能查询/使用结果        |
| `attack_target_result`     | 攻击目标设置结果（实验性，未暴露给LLM） |
| `command_execution_result` | Minecraft 指令执行结果 |
| `config`                   | 当前配置             |
| `event`                    | 游戏事件推送           |
| `chat_message`             | 聊天消息推送           |
| `error`                    | 错误信息             |

### 事件推送

当启用事件推送时，服务端会主动向客户端推送以下事件：

| 事件类型                | 说明                          | data 字段                                          |
| ------------------- | --------------------------- | ------------------------------------------------- |
| `maid_hurt`         | 女仆受伤                        | `maid_id`, `maid_name`, `damage`, `source`        |
| `maid_death`        | 女仆死亡                        | `maid_id`, `maid_name`, `killer`(可选), `cause`    |
| `player_death`      | 玩家死亡                        | `player_name`, `cause`                            |
| `advancement`       | 玩家解锁成就（仅含有 toast 的成就）       | `player_name`, `title`, `description`             |
| `biome_change`      | 群系切换（10秒防抖，避免边界反复触发）        | `maid_id`, `maid_name`, `biome`, `old_biome`      |
| `weather_change`    | 天气变化                        | `is_raining`, `is_thundering`                     |
| `time_phase_change` | 昼夜变化                        | `phase`("day"/"night"), `day_time`                |
| `inventory_change`  | 背包物品变化（开→快照，关→diff，无变化不推送）  | `maid_id`, `player_name`, `added`, `removed`      |
| `chat`              | 玩家聊天消息                      | `sender`, `message`                               |

## 感知系统

Python 侧插件按配置的 `awareness_interval` 轮询游戏状态（通过 `awareness` category 一次获取所有数据），检测以下情况：

### 需要回复的事件（ai_behavior="respond"）

| 检测项       | 条件              | 冷却   | 示例发言                   |
| --------- | --------------- | ---- | ---------------------- |
| 复仇情绪      | 死亡后复活           | 一次性  | "刚才那只骷髅呢？我要打回去！"      |
| 低血量警告     | 玩家血量 < 30%      | 5分钟  | "你血量好低！要小心啊！"         |
| 着火警告      | 玩家着火            | 2分钟  | "着火了！快灭火！"             |
| 溺水警告      | 玩家溺水            | 2分钟  | "快上岸！要淹到了！"            |
| 近处敌对生物    | 新敌对生物 < 10格     | 3分钟  | "危险！附近有苦力怕x2！"        |
| 食物分享      | 有食物 + 玩家血量 < 70% | 5分钟  | "你饿不饿？我这里有点吃的～"       |
| 矿洞暗处      | 地下 + 亮度 < 7     | 10分钟 | "这里好暗...要不要我帮忙插火把？"   |
| 玩家远离      | 距离 > 50格        | 1分钟  | "伙伴走好远了...要去哪里呀？"     |
| 玩家归来      | 距离 < 30格（从远变近）  | 1分钟  | "伙伴回来了！太好了～"          |

### 仅注入上下文（ai_behavior="read"）

| 检测项     | 条件             | 说明                   |
| ------- | -------------- | -------------------- |
| 玩家手持物品  | 物品变化时（2次检测防抖）  | "伙伴手持物品: minecraft:diamond_swordx1" |
| 附近结构/地标 | 新发现的结构（128格内）  | "附近发现结构: minecraft:village (距离45.0格)" |

### 陪玩式感知

在普通安全提醒之外，Python 侧插件还维护了一层低打扰的陪玩上下文：

| 能力 | 说明 |
| ---- | ---- |
| 短期共同经历 | 记录最近 Minecraft 事件、聊天、感知变化和活动变化，按时间顺序整理成摘要 |
| 活动状态推断 | 基于 awareness 数据和短期证据推断玩家大致处于挖矿、地下探索、建家、钓鱼、赶路、整理、刷怪、闲置、战斗、远离等阶段 |
| 安静陪伴触发 | 玩家稳定处于适合陪伴的状态一段时间后，按场景低频触发一句简短自然的陪玩回应 |
| 短期共同目标 | 当前会话内维护“正在一起做什么”，如一起下矿、建家、下棋、赶路，不替代宿主长期记忆 |
| 低优先级聚合 | 活动变化、短期记忆等 `read` 上下文会短窗口合并，避免短时间大量 push |
| 高优先级直通 | 聊天、死亡、低血量、溺水、着火、近处敌怪等仍会立即 `respond` |

当前陪玩触发偏保守：不明确的 `unknown`、泛化的 `exploring`、战斗中、玩家远离、整理物品和刷怪收尾时不会触发安静陪伴，避免乱报和打扰。

### N.E.K.O 插件侧配置

以下配置位于 `neko_minecraft/plugin.toml` 的 `[minecraft_bridge]` 段：

| 配置项 | 默认值 | 说明 |
| ------ | ------ | ---- |
| `awareness_interval` | `5` | awareness 轮询间隔，单位秒 |
| `playmate_memory_items` | `24` | 短期共同经历最多保存条数 |
| `playmate_memory_summary_length` | `120` | 单条短期记忆摘要最大长度 |
| `playmate_memory_inject_items` | `8` | 注入共同经历时最多使用条数 |
| `playmate_memory_inject_chars` | `700` | 注入共同经历文本最大长度 |
| `playmate_activity_debounce_checks` | `2` | 活动状态需要连续命中几次才确认 |
| `playmate_activity_cooldown` | `120` | 活动状态变化冷却时间，单位秒 |
| `playmate_quiet_stable_seconds` | `90` | 同一活动稳定多久后允许安静陪伴触发 |
| `playmate_quiet_cooldown` | `300` | 安静陪伴冷却时间，单位秒 |
| `playmate_aggregate_window` | `8` | 低优先级上下文聚合窗口，单位秒 |
| `playmate_throttle_window` | `30` | push 节流统计窗口，单位秒 |
| `playmate_throttle_limit` | `6` | 节流窗口内允许的 push 次数 |
| `playmate_suggestion_cooldown` | `600` | 轻量主动建议冷却时间，单位秒 |

## 游戏内指令

| 指令                          | 说明                            |
| --------------------------- | ----------------------------- |
| `/neko accept <pending_id>` | 确认执行 N.E.K.O 请求的 Minecraft 指令 |
| `/neko reject <pending_id>` | 拒绝 N.E.K.O 请求的 Minecraft 指令   |

当 N.E.K.O 请求执行指令时，所有在线玩家会收到带有可点击按钮的提示消息。

## 项目结构

### Minecraft Mod 端（Java/NeoForge）

```
src/main/java/com/neko_tlm_bridge/
├── NekoTlmBridge.java          # 模组主类，生命周期管理与 handler 初始化
├── client/
│   └── NekoConfigScreen.java   # 配置界面
├── config/
│   └── ModConfig.java          # 配置定义
├── event/
│   └── GameEventHandler.java   # 游戏事件监听与推送（死亡/天气/昼夜/群系/背包/成就）
├── tlm/
│   ├── LittleMaidCompat.java       # 车万女仆 API 扩展注册
│   ├── NekoBridgeTool.java         # AI 工具：消息转发到 N.E.K.O
│   ├── NekoExtraMaidBrain.java     # 女仆额外行为注册
│   ├── NekoAttackTargetBehavior.java  # 自定义攻击行为
│   ├── NekoAttackTargetStore.java     # 攻击目标存储与管理
│   └── NekoWebSocketServerHolder.java # WebSocket 服务器引用持有
└── ws/
    ├── NekoWebSocketServer.java     # WebSocket 服务器实现
    ├── NekoCommand.java             # 游戏内指令注册
    ├── PendingCommandManager.java   # 待确认指令管理
    ├── Protocol.java                # 协议常量定义
    └── handler/                     # 消息处理器（模块化拆分）
        ├── MessageHandlerInterface.java  # Handler 公共接口
        ├── MessageRouter.java            # 消息路由分发 + 主线程队列
        ├── MaidStatusHandler.java        # 女仆状态查询
        ├── CommandMaidHandler.java       # 女仆控制命令（跟随/坐下/任务/日程/装备）
        ├── GameContextHandler.java       # 游戏上下文查询（7种 category + awareness）
        ├── ChatHandler.java             # 聊天消息发送
        ├── CommandExecutionHandler.java  # 服务器命令执行（需玩家确认）
        ├── AttackTargetHandler.java     # 攻击目标管理
        ├── SkillHandler.java            # 技能查询
        ├── ConfigHandler.java           # 配置查询与监控女仆设置
        └── MaidHelper.java              # 女仆查找共享工具方法
```

### N.E.K.O 插件端（Python）

```
neko_minecraft/
├── __init__.py          # 插件主类：生命周期、消息分发、@llm_tool 声明、UI
├── instructions.py      # AI 指令模板（注入到 LLM 上下文的系统提示词）
├── task_resolver.py     # 任务名解析与模糊匹配（中文同义词 → TLM 任务 ID）
├── bridge.py            # WebSocket 桥接层（连接、重连、心跳、收发队列）
├── config.py            # 配置加载/保存/同步（TOML + JSON 双格式支持）
├── events.py            # 游戏事件格式化（事件数据 → 角色化文本 + 优先级）
├── awareness.py         # 感知系统（定时轮询、状态检测、cooldown 管理）
├── playmate/            # 陪玩式感知增强（短期记忆、活动推断、安静陪伴、push 聚合）
│   ├── __init__.py      # 子包导出入口
│   ├── context.py       # 陪玩上下文总协调器
│   ├── memory.py        # 短期共同经历记忆
│   ├── activity.py      # 玩家活动状态推断
│   ├── quiet.py         # 安静陪伴触发器
│   └── push.py          # Minecraft 上下文 push 聚合与节流
├── tools.py             # LLM 工具业务逻辑（10个 do_* 函数）
├── tool_defs.py         # LLM 工具元数据常量（name/description/parameters）
├── config.json          # 默认配置
├── plugin.toml          # 插件描述与运行时配置
├── ui/
│   └── panel.tsx        # 仪表盘 UI 面板
└── i18n/
    ├── zh-CN.json       # 中文翻译
    └── en.json          # 英文翻译
```

## 构建

```bash
./gradlew build
```

构建产物位于 `build/libs/` 目录下。

## 许可证

MIT License

## 致谢

- [车万女仆 (Touhou Little Maid)](https://github.com/TartaricAcid/TouhouLittleMaid) — 提供了优秀的女仆系统与 AI 扩展 API
- [N.E.K.O](https://github.com/Project-N-E-K-O/N.E.K.O) — 自然语言 AI 控制框架，很好用的猫娘👍👍👍
