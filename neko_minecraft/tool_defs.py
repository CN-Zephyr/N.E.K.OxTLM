"""LLM 工具元数据常量 — 定义所有 @llm_tool 的 name、description 和 parameters，确保与 SDK 装饰器解耦"""

MC_MAID_STATUS = {
    "name": "mc_maid_status",
    "description": (
        "查询你在Minecraft世界中女仆的当前状态。"
        "返回所有女仆的信息，包括id(UUID格式)、名字、血量、位置、是否坐着、是否跟随、主人名字、手持物品等。"
        "返回数据还包含 available_tasks，可用于决定应该切换到哪个工作模式。"
        "当玩家要求切换工作/模式但你不确定具体任务ID或任务名时，先调用此工具查看可用模式，再调用 mc_switch_task；不要直接反问玩家。"
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

MC_SWITCH_FOLLOW = {
    "name": "mc_switch_follow",
    "description": (
        "切换女仆的跟随/驻守模式。"
        "当玩家要求女仆跟随、跟上、过来、不要走远时，action设为follow；"
        "当玩家要求女仆驻守、留在原地、不要跟随时，action设为stay。"
        "如果女仆正坐着且要跟随，会自动站起。"
        "【必须调用】玩家说'跟我来'、'过来'、'一起去'、'别离太远'时，不要只文字回应，必须调用本工具。"
        "【重要】如果玩家在跟随指令中还提到了要做什么工作（如'过来玩游戏''跟着我去打草''过来种田''过来收菜''跟我去挖矿''跟我去打怪'），在调用本工具的同时，必须也调用 mc_switch_task 切换到对应的工作模式。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "follow=跟随主人移动，stay=驻守原地不动",
                "enum": ["follow", "stay"],
            },
        },
    },
}

MC_SWITCH_SIT = {
    "name": "mc_switch_sit",
    "description": (
        "切换女仆的坐下/站起状态。"
        "当玩家要求女仆坐下、休息时，action设为sit；"
        "当玩家要求女仆站起、起来、站起来时，action设为stand。"
        "坐下和跟随是两个独立的状态：坐下控制姿势，跟随控制移动。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "sit=坐下，stand=站起",
                "enum": ["sit", "stand"],
            },
        },
    },
}

MC_SWITCH_TASK = {
    "name": "mc_switch_task",
    "description": (
        "切换女仆的工作模式/任务/职业，让女仆执行某种工作。"
        "task参数优先传 available_tasks 中的精确任务ID或任务名称；如果还没查过可用任务，可先调用 mc_maid_status。"
        "也可以传玩家描述的工作内容（如'收菜'、'收获'、'打草'、'收甘蔗'、'种田'、'攻击'、'待机'、'小游戏'），插件会尽力匹配，但不同 mod 的任务名可能不同，精确ID/名称更可靠。"
        "调用成功后工具会再次查询女仆状态验证 current_task 是否真的切换到 expected_task；请根据 verified 字段判断是否已经生效。"
        "如果返回 TASK_SWITCH_RECOVERABLE，说明这次没切成但会返回 available_tasks 和 retry_hint；应立刻选择最接近的精确 id/name 再次调用本工具，不要只口头说明失败。"
        "【必须调用】只要玩家明确要求你开始、停止或更换游戏内工作模式，就必须调用本工具，不能只用文字答应，也不要先反问。"
        "【短命令也必须调用】玩家只说'收菜'、'收获'、'打草'、'种田'、'打怪'、'休息'、'待机'、'下棋'时，已经是明确模式切换意图。"
        "【承接上下文】如果玩家先说过'收菜'，随后说'切换模式'、'换模式'、'切模式'，应承接上一轮工作意图并调用本工具；不知道具体模式ID时先调用 mc_maid_status 查 available_tasks。"
        "典型必须调用场景：'打怪/保护我/清怪'、'收菜/收获/收作物/种田/收田/收甘蔗/打草'、'剪羊毛/挤奶/喂动物'、'来玩游戏/下棋/小游戏'、'停下/休息/待机'。"
        "下矿/探洞/挖矿没有真正的挖矿工作模式时，应优先切换到'火把/照明'这类辅助模式；如果没有可用照明模式，则至少配合 mc_switch_follow 和 mc_switch_sit 参与行动。"
        "如果玩家要求女仆打怪、杀怪，切换到攻击模式即可（如'攻击'、'打怪'），女仆会自行搜索并攻击附近的敌对生物。"
        "【重要】切换到攻击模式前，应先调用 mc_game_context(category='equipment') 检查女仆主手是否有武器。如果主手为空或只有非武器物品，应提醒玩家给女仆装备武器后再切换。"
        "【重要】当玩家说'停下'、'别干了'、'休息'、'不做了'等要求停止当前工作时，必须调用此工具切换到待机模式（task传'待机'或'idle'），不能只回复文字而不操作。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要切换的任务。优先使用 mc_maid_status 返回的 available_tasks 中的精确任务ID或名称；也可传玩家原话作为兜底，例如：收菜、打怪、种田、待机。不同 mod 的任务名可能不同，精确ID/名称最可靠。",
            },
        },
        "required": ["task"],
    },
}

MC_SWITCH_SCHEDULE = {
    "name": "mc_switch_schedule",
    "description": (
        "切换女仆的日程安排。"
        "schedule=day白天工作、schedule=night夜晚工作、schedule=all全天工作。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "schedule": {
                "type": "string",
                "description": "日程安排：day(白天)、night(夜晚)、all(全天)",
                "enum": ["day", "night", "all"],
            },
        },
    },
}

MC_EQUIP_ITEM = {
    "name": "mc_equip_item",
    "description": (
        "将女仆背包中的物品装备到主手。"
        "item=物品ID（如item=minecraft:diamond_sword）或slot=背包槽位编号指定物品。"
    ),
    "parameters": {
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
}

MC_SEND_CHAT = {
    "name": "mc_send_chat",
    "description": (
        "在Minecraft游戏内显示聊天消息（聊天气泡+聊天框）。"
        "你的语音回复由TTS系统自动处理，此工具仅用于在游戏画面上显示文字。"
        "不要用它重复你已经在语音中说过的话，避免重复发言。"
        "适用场景：需要在游戏画面上显示重要提示、让其他玩家看到消息"
        "注意：管理员可能在配置中关闭了聊天气泡或聊天框，此时消息可能只以其中一种方式显示，或完全无法显示。"
    ),
    "parameters": {
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
}

MC_GAME_CONTEXT = {
    "name": "mc_game_context",
    "description": (
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
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "要查询的上下文分类",
                "enum": ["status", "world", "equipment", "user", "effects", "position", "nearby_entities"],
            },
        },
    },
}

MC_USE_SKILL = {
    "name": "mc_use_skill",
    "description": (
        "触发车万女仆AI系统中已注册的Skill（技能/提示词包）。"
        "普通Skill触发时将行为规范注入对话上下文；"
        "knowledge类型Skill触发RAG子对话，从知识库中检索相关信息。"
        "不要编造skill_name，只能使用已知的Skill名称。如果不确定有哪些可用Skill，不要调用此工具。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "要触发的Skill名称，必须是已注册的Skill名称，不要编造",
            },
        },
        "required": ["skill_name"],
    },
}

MC_EXECUTE_COMMAND = {
    "name": "mc_execute_command",
    "description": (
        "请求执行Minecraft服务器指令。"
        "command=指令内容（如/time set day、/weather clear、/tp等）。"
        "指令发送后，游戏内会显示确认提示，需要玩家点击确认后才会执行。"
        "如果玩家拒绝或超时（120秒），指令不会被执行。"
        "此功能需要在游戏内N.E.K.O桥接配置中开启「指令执行」选项。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的Minecraft服务器指令，如 /time set day、/weather clear、/gamemode survival",
            },
        },
        "required": ["command"],
    },
    "timeout": 120,
}

MC_SET_PLAN = {
    "name": "mc_set_plan",
    "description": (
        "设置或更新游戏内右上角显示的当前 Minecraft 目标板。"
        "这是插件侧的轻量目标板，只负责保存、显示和注入当前游戏目标；不要把它当作 N.E.K.O 宿主的长期任务系统。"
        "新建目标时优先传 title 和 steps；完成进度变化时传 completed_steps 或 uncompleted_steps（1 基序号）；"
        "追加步骤时传 append_steps；clear=true 或 plan='' 可清除目标板。"
        "兼容旧用法：plan 参数仍可传多行文本，系统会解析成结构化目标板并显示。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "兼容旧用法的计划文本，多行用换行分隔；空字符串清除目标板",
            },
            "title": {
                "type": "string",
                "description": "当前目标板标题，例如'今天先把据点搭起来'",
            },
            "steps": {
                "type": "array",
                "description": "替换全部步骤。每项是一条具体 Minecraft 步骤，按显示顺序排列",
                "items": {"type": "string"},
            },
            "completed_steps": {
                "type": "array",
                "description": "标记为完成的步骤序号，使用 1 基序号，例如 [1, 3]",
                "items": {"type": "integer"},
            },
            "uncompleted_steps": {
                "type": "array",
                "description": "重新标记为未完成的步骤序号，使用 1 基序号",
                "items": {"type": "integer"},
            },
            "append_steps": {
                "type": "array",
                "description": "追加到当前目标板末尾的新步骤",
                "items": {"type": "string"},
            },
            "clear": {
                "type": "boolean",
                "description": "是否清除当前目标板",
            },
        },
    },
}
