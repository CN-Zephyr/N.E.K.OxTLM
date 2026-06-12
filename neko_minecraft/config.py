"""配置管理 — 插件配置的加载、保存和同步，支持 TOML 和 JSON 双格式"""

import json


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
                _load_playmate_config(plugin, bridge)
                return
        except Exception as e:
            plugin.logger.warning(f"Failed to load plugin.toml: {e}")

    try:
        config_path = plugin.config_dir / "config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            plugin._ws_url = config.get("ws_url", plugin._ws_url)
            plugin._heartbeat_interval = config.get("heartbeat_interval", plugin._heartbeat_interval)
            plugin._reconnect_interval = config.get("reconnect_interval", plugin._reconnect_interval)
            plugin._max_reconnect_interval = config.get("max_reconnect_interval", plugin._max_reconnect_interval)
            plugin._assigned_maid_id = config.get("assigned_maid_id", "")
            plugin._assigned_maid_name = config.get("assigned_maid_name", "")
            plugin._awareness_interval = config.get("awareness_interval", plugin._awareness_interval)
            _load_playmate_config(plugin, config)
    except Exception as e:
        plugin.logger.warning(f"Failed to load config: {e}")


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


def save_config(plugin):
    toml_path = plugin.config_dir / "plugin.toml"
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
        existing["minecraft_bridge"]["assigned_maid_id"] = plugin._assigned_maid_id
        existing["minecraft_bridge"]["assigned_maid_name"] = plugin._assigned_maid_name

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
        plugin.logger.warning(f"Failed to save plugin.toml: {e}")

    try:
        config_path = plugin.config_dir / "config.json"
        config = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        config["assigned_maid_id"] = plugin._assigned_maid_id
        config["assigned_maid_name"] = plugin._assigned_maid_name
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        plugin.logger.warning(f"Failed to save config: {e}")


def sync_config(plugin, config_data):
    plugin._command_execution_enabled = config_data.get("command_execution_enabled", False)
    plugin._chat_bubble_enabled = config_data.get("chat_bubble_enabled", True)
    plugin._chat_box_enabled = config_data.get("chat_box_enabled", True)
