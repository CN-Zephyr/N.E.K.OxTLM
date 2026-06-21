"""LLM 工具元数据常量 — 定义所有 @llm_tool 的 name、description 和 parameters，确保与 SDK 装饰器解耦"""

MC_MAID_STATUS = {
    "name": "mc_maid_status",
    "description": (
        "查询你在Minecraft世界中女仆的当前状态。"
        "返回所有女仆的信息，包括id(UUID格式)、名字、血量、位置、是否坐着、是否跟随、主人名字、手持物品等。"
        "当你需要了解自身或其他女仆的状态时，应调用此工具。"
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
        "【重要】如果玩家在跟随指令中还提到了要做什么工作（如'过来玩游戏''跟着我去打草''过来种田''跟我去挖矿''跟我去打怪'），在调用本工具的同时，必须也调用 mc_switch_task 切换到对应的工作模式。"
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
        "task参数传玩家描述的工作内容即可（如'打草'、'收甘蔗'、'种田'、'攻击'、'待机'、'小游戏'），系统会自动匹配到正确的模式ID。"
        "【必须调用】只要玩家明确要求你开始、停止或更换游戏内工作模式，就必须调用本工具，不能只用文字答应。"
        "典型必须调用场景：'打怪/保护我/清怪'、'种田/收田/收甘蔗/打草'、'剪羊毛/挤奶/喂动物'、'来玩游戏/下棋/小游戏'、'停下/休息/待机'。"
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
                "description": "玩家描述的工作内容，直接传玩家的原话即可，系统会自动匹配到对应的可用模式。例如：打怪、攻击、种田、收甘蔗、打草、喂动物、剪羊毛、挤奶、火把、照明、游戏、小游戏、待机。下矿/探洞/挖矿通常应匹配到火把或照明辅助模式。",
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
        "设置游戏内右上角显示的计划/目标。"
        "plan参数为计划内容，多行用换行分隔，传空字符串清除计划。"
        "适用于和玩家商量好目标后，将计划显示在游戏画面上作为提醒。"
        "计划是动态的：玩家完成某个目标时，应调用此工具更新计划（如加✓标记或移除已完成项）；玩家改变目标时也要同步更新。"
        "例如：'今天的目标：\n1. 找钻石\n2. 建庇护所'"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "计划内容，多行用换行分隔，空字符串清除计划",
            },
        },
        "required": ["plan"],
    },
}
