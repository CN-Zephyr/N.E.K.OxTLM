"""WebSocket 桥接层 — 管理 Python 插件与 Minecraft mod 之间的 WebSocket 连接、重连、心跳和收发队列"""

import asyncio
import json
import queue
import subprocess
import sys
import threading

import websockets
from websockets.exceptions import ConnectionClosed


def _is_java_running():
    """检测 Java 进程（Minecraft）是否在运行"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq javaw.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            if "javaw.exe" in result.stdout:
                return True
            # 也检查 java.exe（服务端可能用这个）
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq java.exe", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return "java.exe" in result.stdout
        else:
            result = subprocess.run(
                ["pgrep", "-x", "java"], capture_output=True, timeout=5,
            )
            return result.returncode == 0
    except Exception:
        return True  # 检测失败时假设还在运行，避免误判


class WSBridge:
    def __init__(self, ws_url, logger, heartbeat_interval=30):
        self.ws_url = ws_url
        self._logger = logger
        self._heartbeat_interval = heartbeat_interval
        self._loop = None
        self._thread = None
        self._ws = None
        self.connected = False
        self._running = False
        self.mc_exited = False
        self._send_queue = queue.Queue()
        self._recv_queue = queue.Queue()

    def start(self):
        self._running = True
        self.mc_exited = False
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
                if not _is_java_running():
                    self._logger.info("[WSBridge] Java process not found, MC has exited")
                    self.mc_exited = True
                    break
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
