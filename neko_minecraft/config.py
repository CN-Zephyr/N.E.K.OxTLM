"""配置管理 — 插件配置的加载、保存和同步，支持 TOML 和 JSON 双格式"""

import json

from . import plan as _plan


COMPANION_MODE_PRESETS = {
    "quiet": {
        "playmate_quiet_stable_seconds": 240,
        "playmate_quiet_cooldown": 900,
        "playmate_suggestion_cooldown": 1500,
    },
    "standard": {
        "playmate_quiet_stable_seconds": 90,
        "playmate_quiet_cooldown": 300,
        "playmate_suggestion_cooldown": 600,
    },
    "active": {
        "playmate_quiet_stable_seconds": 45,
        "playmate_quiet_cooldown": 150,
        "playmate_suggestion_cooldown": 240,
    },
}

COMPANION_CUSTOM_FIELDS = [
    "playmate_quiet_stable_seconds",
    "playmate_quiet_cooldown",
    "playmate_suggestion_cooldown",
]


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


def load_config(plugin):
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None

    if tomllib:
        try:
            toml_path = plugin.config_dir / "plugin.toml"
            if toml_path.exists():
                with open(toml_path, "rb") as f:
                    config = tomllib.load(f)
                bridge = config.get("minecraft_bridge", {})
                plugin._ws_url = bridge.get("ws_url", plugin._ws_url)
                plugin._heartbeat_interval = bridge.get("heartbeat_interval", plugin._heartbeat_interval)
                plugin._reconnect_interval = bridge.get("reconnect_interval", plugin._reconnect_interval)
                plugin._max_reconnect_interval = bridge.get("max_reconnect_interval", plugin._max_reconnect_interval)
                plugin._assigned_maid_id = bridge.get("assigned_maid_id", "")
                plugin._assigned_maid_name = bridge.get("assigned_maid_name", "")
                plugin._awareness_interval = bridge.get("awareness_interval", plugin._awareness_interval)
                plugin._companion_mode = _normalize_companion_mode(
                    bridge.get("companion_mode", plugin._companion_mode),
                    plugin,
                )
                _load_plan_config(plugin, bridge)
                _load_playmate_config(plugin, bridge)
                _apply_companion_mode(plugin)
                return
        except Exception as e:
            plugin.logger.warning(f"Failed to load plugin.toml: {e}")


def _load_plan_config(plugin, config):
    state = _plan.normalize_plan_state(config.get("structured_plan", {}))
    text = str(config.get("current_plan", "") or "")
    if text:
        plugin._current_plan_text = text
        plugin._plan_state = state if state.get("title") or state.get("steps") else _plan.plan_from_text(text)
    elif state.get("title") or state.get("steps"):
        plugin._plan_state = state
        plugin._current_plan_text = _plan.plan_to_text(state)
    else:
        plugin._current_plan_text = ""
        plugin._plan_state = _plan.empty_plan()


def _load_playmate_config(plugin, config):
    plugin._playmate_memory_items = config.get("playmate_memory_items", plugin._playmate_memory_items)
    plugin._playmate_memory_summary_length = config.get("playmate_memory_summary_length", plugin._playmate_memory_summary_length)
    plugin._playmate_memory_inject_items = config.get("playmate_memory_inject_items", plugin._playmate_memory_inject_items)
    plugin._playmate_memory_inject_chars = config.get("playmate_memory_inject_chars", plugin._playmate_memory_inject_chars)
    plugin._playmate_activity_debounce_checks = config.get("playmate_activity_debounce_checks", plugin._playmate_activity_debounce_checks)
    plugin._playmate_activity_cooldown = config.get("playmate_activity_cooldown", plugin._playmate_activity_cooldown)
    plugin._playmate_quiet_stable_seconds = config.get("playmate_quiet_stable_seconds", plugin._playmate_quiet_stable_seconds)
    plugin._playmate_quiet_cooldown = config.get("playmate_quiet_cooldown", plugin._playmate_quiet_cooldown)
    plugin._playmate_aggregate_window = config.get("playmate_aggregate_window", plugin._playmate_aggregate_window)
    plugin._playmate_throttle_window = config.get("playmate_throttle_window", plugin._playmate_throttle_window)
    plugin._playmate_throttle_limit = config.get("playmate_throttle_limit", plugin._playmate_throttle_limit)
    plugin._playmate_minigame_feedback_cooldown = config.get("playmate_minigame_feedback_cooldown", plugin._playmate_minigame_feedback_cooldown)
    plugin._playmate_minigame_context_chars = config.get("playmate_minigame_context_chars", plugin._playmate_minigame_context_chars)
    plugin._playmate_suggestion_cooldown = config.get("playmate_suggestion_cooldown", plugin._playmate_suggestion_cooldown)
    plugin._playmate_debug_log_enabled = config.get("playmate_debug_log_enabled", plugin._playmate_debug_log_enabled)
    plugin._playmate_debug_log_max_bytes = config.get("playmate_debug_log_max_bytes", plugin._playmate_debug_log_max_bytes)


def _normalize_companion_mode(mode, plugin=None):
    mode = str(mode or "custom").strip().lower()
    if mode in ("quiet", "standard", "active", "custom"):
        return mode
    if plugin:
        plugin.logger.warning(f"Unknown companion_mode '{mode}', falling back to custom")
    return "custom"


def _apply_companion_mode(plugin):
    mode = _normalize_companion_mode(getattr(plugin, "_companion_mode", "custom"), plugin)
    plugin._companion_mode = mode
    preset = COMPANION_MODE_PRESETS.get(mode)
    if not preset:
        return
    for key, value in preset.items():
        setattr(plugin, f"_{key}", value)


def _coerce_custom_int(value, fallback, minimum=1):
    try:
        number = int(str(value).strip())
    except Exception:
        return fallback
    return max(minimum, number)


def apply_custom_companion_settings(plugin, values):
    for key in COMPANION_CUSTOM_FIELDS:
        if key not in values:
            continue
        current = getattr(plugin, f"_{key}", 1)
        setattr(plugin, f"_{key}", _coerce_custom_int(values.get(key), current))


def companion_settings(plugin):
    return {
        key: getattr(plugin, f"_{key}", COMPANION_MODE_PRESETS["standard"].get(key, 1))
        for key in COMPANION_CUSTOM_FIELDS
    }


def _runtime_config_payload(plugin):
    payload = {
        "ws_url": plugin._ws_url,
        "heartbeat_interval": getattr(plugin, "_heartbeat_interval", 30),
        "reconnect_interval": getattr(plugin, "_reconnect_interval", 5),
        "max_reconnect_interval": getattr(plugin, "_max_reconnect_interval", 60),
        "assigned_maid_id": plugin._assigned_maid_id,
        "assigned_maid_name": plugin._assigned_maid_name,
        "awareness_interval": getattr(plugin, "_awareness_interval", 5),
        "companion_mode": getattr(plugin, "_companion_mode", "custom"),
    }
    for key in COMPANION_CUSTOM_FIELDS:
        payload[key] = getattr(plugin, f"_{key}", COMPANION_MODE_PRESETS["standard"].get(key, 1))
    payload["current_plan"] = getattr(plugin, "_current_plan_text", "")
    payload["structured_plan"] = _plan.normalize_plan_state(getattr(plugin, "_plan_state", {}))
    return payload


def save_config(plugin):
    toml_path = plugin.config_dir / "plugin.toml"
    payload = _runtime_config_payload(plugin)
    toml_saved = False
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
        existing["minecraft_bridge"].update(payload)

        try:
            import tomlkit
            doc = tomlkit.document()
            for k, v in existing.items():
                doc.add(k, v)
            with open(toml_path, "w", encoding="utf-8") as f:
                tomlkit.dump(doc, f)
            toml_saved = True
        except ImportError:
            lines = []
            for section_key, section_val in existing.items():
                if not isinstance(section_val, dict):
                    continue
                _write_toml_section(lines, section_key, section_val)

            with open(toml_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            toml_saved = True
    except Exception as e:
        plugin.logger.warning(f"Failed to save plugin.toml: {e}")
    return toml_saved


def sync_config(plugin, config_data):
    plugin._command_execution_enabled = config_data.get("command_execution_enabled", False)
    plugin._chat_bubble_enabled = config_data.get("chat_bubble_enabled", True)
    plugin._chat_box_enabled = config_data.get("chat_box_enabled", True)
