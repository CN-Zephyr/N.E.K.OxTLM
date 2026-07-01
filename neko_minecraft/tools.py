"""LLM 工具业务逻辑 — 10个 do_* 函数，实现女仆状态查询、行为控制、聊天、技能等工具的具体逻辑"""

from plugin.sdk.plugin import Ok, Err

from . import task_resolver
from . import plan as _plan


async def do_maid_status(plugin):
    if not plugin.connected:
        return {"output": {"error": "Not connected to Minecraft"}, "is_error": True, "error": "NOT_CONNECTED"}
    result = await plugin._send_request({"type": "get_maid_status"})
    if result.get("type") == "error":
        return {"output": result.get("data", {}), "is_error": True, "error": "REQUEST_FAILED"}
    return {"maids": result.get("data", {}).get("maids", [])}


async def do_switch_follow(plugin, *, action="follow"):
    plugin.logger.info(f"[Entry] switch_follow called with action='{action}'")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    maid_id = plugin._resolve_maid_id()
    if not maid_id:
        return Err("No maid assigned")
    follow = action != "stay"
    result = await plugin._send_request({
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
        maid = plugin._maid_status_cache.get(maid_id, {})
        if maid.get("is_sitting", False):
            sit_result = await plugin._send_request({
                "type": "command_maid",
                "data": {"maid_id": maid_id, "command": "switch_sit", "args": {"sit": False}},
            })
            if sit_result.get("type") != "error":
                sit_data = sit_result.get("data", {})
                if sit_data.get("success") is not False:
                    extra["stood_up"] = True
                    plugin.logger.info("[Entry] switch_follow: maid was sitting, auto stood up")
    return Ok({"success": True, "action": action, **extra})


async def do_switch_sit(plugin, *, action="sit"):
    plugin.logger.info(f"[Entry] switch_sit called with action='{action}'")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    maid_id = plugin._resolve_maid_id()
    if not maid_id:
        return Err("No maid assigned")
    sit = action == "sit"
    result = await plugin._send_request({
        "type": "command_maid",
        "data": {"maid_id": maid_id, "command": "switch_sit", "args": {"sit": sit}},
    })
    if result.get("type") == "error":
        return Err(str(result.get("data", {})))
    result_data = result.get("data", {})
    if result_data.get("success") is False:
        return Err(result_data.get("error", "Command failed"))
    return Ok({"success": True, "action": action})


async def do_switch_task(plugin, *, task=""):
    plugin.logger.info(f"[Entry] switch_task called with task='{task}'")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    maid_id = plugin._resolve_maid_id()
    if not maid_id:
        return Err("No maid assigned")
    if not task:
        return Err("请提供task参数")

    maid = plugin._maid_status_cache.get(maid_id, {})
    available = maid.get("available_tasks", [])
    plugin.logger.info(f"[switch_task] Cache hit={bool(maid)}, available_tasks count={len(available)}")

    if not available:
        try:
            status_result = await plugin._send_request({"type": "get_maid_status"}, timeout=5)
            if status_result.get("type") != "error":
                for m in status_result.get("data", {}).get("maids", []):
                    plugin._maid_status_cache[m.get("id", "")] = m
                maid = plugin._maid_status_cache.get(maid_id, {})
                available = maid.get("available_tasks", [])
                plugin.logger.info(f"[switch_task] get_maid_status: found {len(maid.get('available_tasks', []))} tasks for maid {maid_id}")
            else:
                plugin.logger.warning(f"[switch_task] get_maid_status failed: {status_result.get('data', {})}")
        except Exception as e:
            plugin.logger.warning(f"[Entry] switch_task: failed to fetch maid status: {e}")

    if not available:
        try:
            ctx_result = await plugin._send_request({
                "type": "get_game_context",
                "data": {"maid_id": maid_id, "category": "status"},
            }, timeout=5)
            if ctx_result.get("type") != "error":
                available = ctx_result.get("data", {}).get("available_tasks", [])
                plugin.logger.info(f"[switch_task] get_game_context: found {len(available)} tasks")
            else:
                plugin.logger.warning(f"[switch_task] get_game_context failed: {ctx_result.get('data', {})}")
        except Exception as e:
            plugin.logger.warning(f"[Entry] switch_task: failed to query game_context: {e}")

    resolved_task = task_resolver.resolve_task_name(task, available)
    plugin.logger.info(f"[Entry] switch_task: '{task}' resolved to '{resolved_task}' (available={len(available)} tasks)")

    if resolved_task is None:
        lines = []
        for t in (available or []):
            if isinstance(t, dict):
                lines.append(f"- {t.get('id', '')}（{t.get('name', '')}）")
            else:
                lines.append(f"- {t}")
        return Err(f"无法匹配'{task}'到任何工作模式。可用模式列表：\n" + "\n".join(lines) + "\n请从上面的列表中选择正确的模式ID重新调用。")

    result = await plugin._send_request({
        "type": "command_maid",
        "data": {"maid_id": maid_id, "command": "switch_task", "args": {"task": resolved_task}},
    })
    if result.get("type") == "error":
        plugin.logger.warning(f"[Entry] switch_task failed: {result.get('data', {})}")
        return Err(str(result.get("data", {})))
    result_data = result.get("data", {})
    if result_data.get("success") is False:
        return Err(result_data.get("error", "Command failed"))
    plugin.logger.info(f"[Entry] switch_task success: task='{task}' -> '{resolved_task}'")
    return Ok({"success": True, "current_task": task, "matched_task_id": resolved_task})


async def do_switch_schedule(plugin, *, schedule="all"):
    plugin.logger.info(f"[Entry] switch_schedule called with schedule='{schedule}'")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    maid_id = plugin._resolve_maid_id()
    if not maid_id:
        return Err("No maid assigned")
    result = await plugin._send_request({
        "type": "command_maid",
        "data": {"maid_id": maid_id, "command": "switch_schedule", "args": {"schedule": schedule}},
    })
    if result.get("type") == "error":
        return Err(str(result.get("data", {})))
    result_data = result.get("data", {})
    if result_data.get("success") is False:
        return Err(result_data.get("error", "Command failed"))
    return Ok({"success": True, "current_schedule": schedule})


async def do_equip_item(plugin, *, item="", slot=None):
    plugin.logger.info(f"[Entry] equip_item called with item='{item}', slot={slot}")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    maid_id = plugin._resolve_maid_id()
    if not maid_id:
        return Err("No maid assigned")
    args = {}
    if item:
        args["item"] = item
    elif slot is not None:
        args["slot"] = slot
    else:
        return Err("请提供item或slot参数")
    result = await plugin._send_request({
        "type": "command_maid",
        "data": {"maid_id": maid_id, "command": "equip_item", "args": args},
    })
    if result.get("type") == "error":
        return Err(str(result.get("data", {})))
    result_data = result.get("data", {})
    if result_data.get("success") is False:
        return Err(result_data.get("error", "Command failed"))
    return Ok({"success": True, "equipped_item": item or f"slot:{slot}"})


async def do_send_chat(plugin, *, message, maid_id=None):
    if not plugin._chat_bubble_enabled and not plugin._chat_box_enabled:
        return Err("聊天功能已被管理员关闭（气泡和聊天框均未启用）")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    resolved_id = plugin._resolve_maid_id(maid_id)
    if not resolved_id:
        return Err("No maid_id available. Call mc_maid_status first or assign a maid in config.")
    result = await plugin._send_request({
        "type": "send_chat",
        "data": {"maid_id": resolved_id, "message": message},
    })
    if result.get("type") == "error":
        return Err(str(result.get("data", {})))
    result_data = result.get("data", {})
    if not result_data.get("success", False):
        return Err("Chat send failed")
    return Ok({"success": True})


async def do_game_context(plugin, category=None):
    if not plugin.connected:
        return {"output": {"error": "Not connected to Minecraft"}, "is_error": True, "error": "NOT_CONNECTED"}
    request_data = {"type": "get_game_context", "data": {}}
    if category:
        request_data["data"]["category"] = category
    maid_id = plugin._resolve_maid_id()
    if maid_id:
        request_data["data"]["maid_id"] = maid_id
    result = await plugin._send_request(request_data)
    if result.get("type") == "error":
        return {"output": result.get("data", {}), "is_error": True, "error": "REQUEST_FAILED"}
    return result.get("data", {})


async def do_use_skill(plugin, *, skill_name=""):
    plugin.logger.info(f"[Entry] use_skill called with skill_name='{skill_name}'")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    if not skill_name:
        return Err("请提供skill_name参数")
    maid_id = plugin._resolve_maid_id()
    request_data = {
        "type": "use_skill",
        "data": {"skill_name": skill_name},
    }
    if maid_id:
        request_data["data"]["maid_id"] = maid_id
    result = await plugin._send_request(request_data)
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


async def do_execute_command(plugin, *, command=""):
    plugin.logger.info(f"[Entry] execute_command called with command='{command}'")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    if not command:
        return Err("请提供command参数")
    result = await plugin._send_request(
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


async def do_set_plan(plugin, *, plan=None, title=None, steps=None, completed_steps=None,
                      uncompleted_steps=None, append_steps=None, clear=False):
    preview = plan if plan is not None else title if title is not None else ""
    plugin.logger.info(f"[Entry] set_plan called with preview='{str(preview)[:80]}'")
    has_update = (
        clear or plan is not None or title is not None or steps is not None
        or completed_steps is not None or uncompleted_steps is not None
        or bool(append_steps)
    )
    if not has_update:
        return Err("请提供 plan 文本，或 title/steps/completed_steps 等结构化计划参数")
    if not plugin.connected:
        return Err("Not connected to Minecraft")
    plan_state = _plan.update_plan_state(
        plugin._plan_state,
        plan=plan,
        title=title,
        steps=steps,
        completed_steps=completed_steps,
        uncompleted_steps=uncompleted_steps,
        append_steps=append_steps,
        clear=clear,
    )
    plan_text = _plan.plan_to_text(plan_state)
    result = await plugin._send_request({
        "type": "set_plan",
        "data": {"plan": plan_text},
    })
    if result.get("type") == "error":
        return Err(str(result.get("data", {})))
    result_data = result.get("data", {})
    if result_data.get("success") is False:
        return Err(result_data.get("error", "Set plan failed"))
    plugin._apply_plan_state(plan_state, save=True)
    return Ok({"success": True, **_plan.plan_summary(plan_state)})
