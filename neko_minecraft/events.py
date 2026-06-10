"""游戏事件格式化 — 将游戏事件数据转换为角色化文本，返回文本、优先级和副作用"""

def format_event(event_data, assigned_maid_id):
    """格式化事件数据，返回 (parts_text, priority, side_effects) 元组。

    side_effects 是一个字典，包含需要在调用方执行的副作用，如：
    {"pending_revenge": {...}, "was_dead": True}
    """
    event_type = event_data.get("event_type", "")
    maid_id = event_data.get("maid_id", "")
    maid_name = event_data.get("maid_name", "")

    # Only filter by maid_id for events that carry one
    if maid_id and assigned_maid_id and maid_id != assigned_maid_id:
        return None, None, None

    priority = 5
    parts_text = ""
    side_effects = {}

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
        killer = event_data.get("killer", "")
        side_effects["pending_revenge"] = {"killer": killer, "cause": cause}
        side_effects["was_dead"] = True
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
            return None, None, None  # No actual changes, skip
    else:
        priority = 5
        parts_text = f"游戏事件[{event_type}]"

    return parts_text, priority, side_effects
