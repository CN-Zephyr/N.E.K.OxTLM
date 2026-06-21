package com.neko_tlm_bridge.ws.handler;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.ws.Protocol;
import org.java_websocket.WebSocket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;

/** 消息路由分发器 — 根据消息 type 字段分发到对应 handler，管理主线程执行队列 */
public class MessageRouter {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private static final Gson GSON = new Gson();
    private static final int MAX_QUEUE_SIZE = 500;
    private static final int MAX_TASKS_PER_TICK = 50;
    private static final long SLOW_TASK_THRESHOLD_MS = 50;

    private final Map<String, MessageHandlerInterface> handlers;
    private final ConcurrentLinkedQueue<Runnable> mainThreadTasks = new ConcurrentLinkedQueue<>();

    public MessageRouter(Map<String, MessageHandlerInterface> handlers) {
        this.handlers = handlers;
    }

    public void tick() {
        int processed = 0;
        Runnable task;
        while (processed < MAX_TASKS_PER_TICK && (task = mainThreadTasks.poll()) != null) {
            long start = System.currentTimeMillis();
            try {
                task.run();
            } catch (Exception e) {
                LOGGER.error("Error executing main thread task", e);
            }
            long elapsed = System.currentTimeMillis() - start;
            if (elapsed > SLOW_TASK_THRESHOLD_MS) {
                LOGGER.warn("Slow main thread task took {}ms, queue size={}", elapsed, mainThreadTasks.size());
            }
            processed++;
        }
    }

    public void routeMessage(String type, JsonObject request, WebSocket conn) {
        String requestId = request.has("request_id") ? request.get("request_id").getAsString() : null;
        MessageHandlerInterface handler = handlers.get(type);
        if (handler == null) {
            sendError(conn, requestId, "Unknown message type: " + type);
            return;
        }
        if (mainThreadTasks.size() >= MAX_QUEUE_SIZE) {
            LOGGER.warn("Main thread task queue full ({}), dropping message type={}", MAX_QUEUE_SIZE, type);
            sendError(conn, requestId, "Server busy, please retry later");
            return;
        }
        mainThreadTasks.add(() -> {
            try {
                JsonObject response = handler.handle(request, conn);
                if (response != null) {
                    sendJson(conn, response);
                }
            } catch (Exception e) {
                LOGGER.error("Error handling message type {}", type, e);
                sendError(conn, requestId, "Internal error: " + e.getMessage());
            }
        });
    }

    private void sendJson(WebSocket conn, JsonObject json) {
        if (conn != null && conn.isOpen()) {
            conn.send(GSON.toJson(json));
        }
    }

    private void sendError(WebSocket conn, String requestId, String errorMessage) {
        JsonObject error = new JsonObject();
        error.addProperty("type", Protocol.TYPE_ERROR);
        if (requestId != null) error.addProperty("request_id", requestId);
        JsonObject data = new JsonObject();
        data.addProperty("message", errorMessage);
        error.add("data", data);
        sendJson(conn, error);
    }
}
