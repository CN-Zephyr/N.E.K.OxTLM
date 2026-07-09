"""WebSocket 桥接层 — 管理 Python 插件与 Minecraft mod 之间的 WebSocket 连接、重连、心跳和收发队列"""

import asyncio
import json
import queue
import subprocess
import sys
import threading
import time

import websockets
from websockets.exceptions import ConnectionClosed, InvalidMessage


_MINECRAFT_CLIENT_PROCESS_HINTS = (
    "net.minecraft.client.main.main",
    "net.minecraft.launchwrapper.launch",
    "cpw.mods.modlauncher.launcher",
    "net.fabricmc.loader.impl.launch.knot.knotclient",
    "org.quiltmc.loader.impl.launch.knot.knotclient",
    "com.mojang.rubydung.rubydung",
    "--gameDir",
    "--assetsDir",
    "--assetIndex",
    "--username",
    "-Dminecraft.launcher.brand",
)

_MINECRAFT_WINDOW_TITLE_HINTS = (
    "minecraft",
)


def _java_process_command_lines():
    if sys.platform == "win32":
        commands = [
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process "
                    "-Filter \"Name='javaw.exe' OR Name='java.exe'\" | "
                    "ForEach-Object { $_.CommandLine }"
                ),
            ],
            [
                "wmic",
                "process",
                "where",
                "name='javaw.exe' or name='java.exe'",
                "get",
                "CommandLine",
                "/value",
            ],
        ]
        for command in commands:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            except Exception:
                continue
            if result.returncode == 0 and result.stdout.strip():
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return None

    try:
        result = subprocess.run(["pgrep", "-af", "java"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        return None
    return []


def _java_process_window_titles():
    if sys.platform != "win32":
        return None
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$p = Get-Process -Name java,javaw -ErrorAction SilentlyContinue | "
            "Select-Object Id,ProcessName,MainWindowTitle; "
            "if ($p) { $p | ConvertTo-Json -Compress }"
        ),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None
    entries = []
    for item in data:
        if not isinstance(item, dict):
            continue
        entries.append({
            "pid": item.get("Id"),
            "name": str(item.get("ProcessName") or ""),
            "title": str(item.get("MainWindowTitle") or ""),
        })
    return entries


def _window_title_hints(title):
    lower = str(title or "").lower()
    return [hint for hint in _MINECRAFT_WINDOW_TITLE_HINTS if hint in lower]


def _java_command_args(command_line):
    text = str(command_line or "").strip()
    lower = text.lower()
    for marker in ("javaw.exe", "java.exe"):
        index = lower.find(marker)
        if index >= 0:
            return text[index + len(marker):].strip()
    for marker in ("/java ", "\\java ", " java "):
        index = lower.find(marker)
        if index >= 0:
            return text[index + len(marker):].strip()
    if lower.startswith("java "):
        return text[5:].strip()
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return text


def _looks_like_minecraft_java(command_line):
    lower = _java_command_args(command_line).lower()
    return any(hint.lower() in lower for hint in _MINECRAFT_CLIENT_PROCESS_HINTS)


def _minecraft_process_hints(command_line):
    lower = _java_command_args(command_line).lower()
    return [hint for hint in _MINECRAFT_CLIENT_PROCESS_HINTS if hint.lower() in lower]


def _short_process_command(command_line, limit=220):
    text = " ".join(str(command_line or "").split())
    if not text:
        return "<empty>"
    if len(text) <= limit:
        return text
    return text[:max(0, limit - 3)] + "..."


def _short_window_entry(entry, limit=160):
    title = str(entry.get("title") or "").strip() or "<no title>"
    if len(title) > limit:
        title = title[:max(0, limit - 3)] + "..."
    return f"pid={entry.get('pid')} name={entry.get('name')} title={title}"


def _log_process_check(logger, message):
    if not logger:
        return
    try:
        logger.info(f"[WSBridge] Minecraft process check: {message}")
    except Exception:
        pass


def _has_generic_java_process():
    if sys.platform == "win32":
        for image_name in ("javaw.exe", "java.exe"):
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                if image_name in result.stdout:
                    return True
            except Exception:
                continue
        return False
    try:
        result = subprocess.run(["pgrep", "-x", "java"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _is_java_running(logger=None):
    """Return True only when a Java process looks like Minecraft."""
    try:
        window_entries = _java_process_window_titles()
        if window_entries is not None:
            titled_entries = [entry for entry in window_entries if str(entry.get("title") or "").strip()]
            matches = [
                (entry, _window_title_hints(entry.get("title")))
                for entry in titled_entries
                if _window_title_hints(entry.get("title"))
            ]
            if matches:
                details = "; ".join(
                    f"hints={','.join(hints)} {_short_window_entry(entry)}"
                    for entry, hints in matches[:3]
                )
                if len(matches) > 3:
                    details += f"; +{len(matches) - 3} more matched"
                _log_process_check(logger, f"matched Minecraft Java window count={len(matches)}: {details}")
                return True

            details = "; ".join(_short_window_entry(entry) for entry in window_entries[:3])
            if len(window_entries) > 3:
                details += f"; +{len(window_entries) - 3} more Java processes"
            _log_process_check(
                logger,
                f"no Minecraft Java window title found; java_process_count={len(window_entries)}; windows={details}",
            )
            return False

        command_lines = _java_process_command_lines()
        if command_lines is None:
            fallback = _has_generic_java_process()
            _log_process_check(
                logger,
                f"command-line query unavailable; generic Java fallback running={fallback}",
            )
            return fallback
        if not command_lines:
            _log_process_check(logger, "no Java process command lines found")
            return False

        matches = []
        ignored = []
        for line in command_lines:
            hints = _minecraft_process_hints(line)
            if hints:
                matches.append((line, hints))
            else:
                ignored.append(line)

        if matches:
            details = "; ".join(
                f"hints={','.join(hints)} cmd={_short_process_command(line)}"
                for line, hints in matches[:3]
            )
            if len(matches) > 3:
                details += f"; +{len(matches) - 3} more matched"
            _log_process_check(logger, f"matched Minecraft Java process count={len(matches)}: {details}")
            return True

        details = "; ".join(_short_process_command(line) for line in ignored[:3])
        if len(ignored) > 3:
            details += f"; +{len(ignored) - 3} more ignored"
        _log_process_check(
            logger,
            f"Java processes found but none matched Minecraft hints; count={len(ignored)}; commands={details}",
        )
        return False
    except Exception as e:
        _log_process_check(
            logger,
            f"process check failed with {type(e).__name__}: {e}; assuming running to avoid false exit",
        )
        return True


class WSBridge:
    def __init__(self, ws_url, logger, heartbeat_interval=30, reconnect_interval=5, max_reconnect_interval=60):
        self.ws_url = ws_url
        self._logger = logger
        self._heartbeat_interval = heartbeat_interval
        self._reconnect_interval = max(1, int(reconnect_interval or 5))
        self._max_reconnect_interval = max(self._reconnect_interval, int(max_reconnect_interval or 60))
        self._handshake_retry_interval = min(max(self._reconnect_interval, 10), self._max_reconnect_interval)
        self._loop = None
        self._thread = None
        self._ws = None
        self.connected = False
        self._running = False
        self.last_error_type = ""
        self.last_error_message = ""
        self.last_error_time = 0
        self.next_reconnect_delay = 0
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

    def _record_error(self, error):
        self.last_error_type = type(error).__name__
        self.last_error_message = str(error)
        self.last_error_time = time.time()

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
        delay = self._reconnect_interval
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
                delay = self._reconnect_interval
                self.next_reconnect_delay = 0
                self.last_error_type = ""
                self.last_error_message = ""
                self.last_error_time = 0
                self._logger.info("[WSBridge] Connected to Minecraft!")
                await self._listen()
            except ConnectionClosed as e:
                self._record_error(e)
                self._logger.info(f"[WSBridge] Connection closed: {e}")
            except InvalidMessage as e:
                self._record_error(e)
                self._logger.warning(
                    f"[WSBridge] Invalid WebSocket response from {self.ws_url}: {e}. "
                    "The port is open, but it did not complete a WebSocket handshake; "
                    "check whether the Minecraft mod server is still starting, the port is wrong, or another program is using it."
                )
            except OSError as e:
                self._record_error(e)
                self._logger.warning(f"[WSBridge] OS error: {e}")
            except Exception as e:
                self._record_error(e)
                self._logger.warning(f"[WSBridge] Error: {type(e).__name__}: {e}")
            finally:
                self.connected = False
                self._ws = None

            if self._running:
                handshake_failed = self.last_error_type == "InvalidMessage"
                reconnect_delay = self._handshake_retry_interval if handshake_failed else delay
                reconnect_delay = min(max(1, reconnect_delay), self._max_reconnect_interval)
                self.next_reconnect_delay = reconnect_delay
                self._logger.info(f"[WSBridge] Reconnecting in {reconnect_delay}s...")
                try:
                    await asyncio.sleep(reconnect_delay)
                    if handshake_failed:
                        delay = self._reconnect_interval
                    else:
                        delay = min(reconnect_delay * 2, self._max_reconnect_interval)
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
                        if data.get("type") == "pong":
                            self._last_pong_time = time.time()
                        if data.get("type") != "pong":
                            if data.get("type") == "game_context":
                                self._logger.debug(f"[WSBridge] recv: {raw[:300]}")
                            else:
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
            self._last_pong_time = time.time()
            while self._running and self.connected:
                try:
                    await ws.send(json.dumps({"type": "ping"}))
                    await asyncio.sleep(self._heartbeat_interval)
                    # 检查 pong 超时：如果超过 3 倍心跳间隔没收到 pong，认为应用层卡死
                    if time.time() - self._last_pong_time > self._heartbeat_interval * 3:
                        self._logger.warning("[WSBridge] Pong timeout, closing connection to trigger reconnect")
                        await ws.close()
                        return
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
