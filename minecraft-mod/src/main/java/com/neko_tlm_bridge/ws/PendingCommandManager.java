package com.neko_tlm_bridge.ws;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.java_websocket.WebSocket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class PendingCommandManager {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private static final Gson GSON = new Gson();
    private final Map<String, PendingCommand> pendingCommands = new ConcurrentHashMap<>();
    private static final long EXPIRE_MS = 120_000;

    public static class PendingCommand {
        public final String pendingId;
        public final String originalRequestId;
        public final String command;
        public final WebSocket conn;
        public final UUID targetPlayerUuid;
        public final long createdAt;

        public PendingCommand(String pendingId, String originalRequestId, String command,
                              WebSocket conn, UUID targetPlayerUuid) {
            this.pendingId = pendingId;
            this.originalRequestId = originalRequestId;
            this.command = command;
            this.conn = conn;
            this.targetPlayerUuid = targetPlayerUuid;
            this.createdAt = System.currentTimeMillis();
        }
    }

    public String addPendingCommand(String originalRequestId, String command,
                                    WebSocket conn, UUID targetPlayerUuid) {
        String pendingId = UUID.randomUUID().toString().substring(0, 8);
        pendingCommands.put(pendingId,
                new PendingCommand(pendingId, originalRequestId, command, conn, targetPlayerUuid));
        return pendingId;
    }

    public PendingCommand get(String pendingId) {
        return pendingCommands.get(pendingId);
    }

    public PendingCommand getAndRemove(String pendingId) {
        return pendingCommands.remove(pendingId);
    }

    /** Removes requests owned by a disconnected N.E.K.O client before they can be confirmed later. */
    public int cancelForConnection(WebSocket conn) {
        if (conn == null) {
            return 0;
        }
        int cancelled = 0;
        for (Map.Entry<String, PendingCommand> entry : pendingCommands.entrySet()) {
            PendingCommand pending = entry.getValue();
            if (pending.conn == conn && pendingCommands.remove(entry.getKey(), pending)) {
                cancelled++;
                LOGGER.info("Cancelled pending command after client disconnect: {} ({})",
                        pending.command, pending.pendingId);
            }
        }
        return cancelled;
    }

    /** Revokes requests when the target client player logs out. */
    public int cancelForPlayer(UUID playerUuid) {
        if (playerUuid == null) {
            return 0;
        }
        int cancelled = 0;
        for (Map.Entry<String, PendingCommand> entry : pendingCommands.entrySet()) {
            PendingCommand pending = entry.getValue();
            if (playerUuid.equals(pending.targetPlayerUuid)
                    && pendingCommands.remove(entry.getKey(), pending)) {
                sendCancelledResult(pending, "The client player disconnected before confirmation");
                cancelled++;
            }
        }
        return cancelled;
    }

    /** Cancels all requests, for example when the server stops or command execution is disabled. */
    public int cancelAll(String reason) {
        int cancelled = 0;
        for (Map.Entry<String, PendingCommand> entry : pendingCommands.entrySet()) {
            PendingCommand pending = entry.getValue();
            if (pendingCommands.remove(entry.getKey(), pending)) {
                sendCancelledResult(pending, reason);
                cancelled++;
            }
        }
        return cancelled;
    }

    /** Cancels one request and wakes the Python caller if its socket is still alive. */
    public boolean cancel(String pendingId, String reason) {
        PendingCommand pending = pendingCommands.remove(pendingId);
        if (pending == null) {
            return false;
        }
        sendCancelledResult(pending, reason);
        return true;
    }

    public void expireOldCommands() {
        long now = System.currentTimeMillis();
        var iter = pendingCommands.entrySet().iterator();
        while (iter.hasNext()) {
            var entry = iter.next();
            PendingCommand cmd = entry.getValue();
            if (now - cmd.createdAt > EXPIRE_MS) {
                iter.remove();
                sendExpiredResult(cmd);
            }
        }
    }

    private void sendExpiredResult(PendingCommand cmd) {
        if (cmd.conn != null && cmd.conn.isOpen()) {
            JsonObject response = new JsonObject();
            response.addProperty("type", Protocol.TYPE_COMMAND_EXECUTION_RESULT);
            if (cmd.originalRequestId != null) {
                response.addProperty("request_id", cmd.originalRequestId);
            }
            JsonObject data = new JsonObject();
            data.addProperty("approved", false);
            data.addProperty("expired", true);
            data.addProperty("command", cmd.command);
            data.addProperty("message", "Command request expired (no player confirmation)");
            response.add("data", data);
            cmd.conn.send(GSON.toJson(response));
        }
        LOGGER.info("Expired pending command: {} ({})", cmd.command, cmd.pendingId);
    }

    private void sendCancelledResult(PendingCommand cmd, String reason) {
        if (cmd.conn != null && cmd.conn.isOpen()) {
            JsonObject response = new JsonObject();
            response.addProperty("type", Protocol.TYPE_COMMAND_EXECUTION_RESULT);
            if (cmd.originalRequestId != null) {
                response.addProperty("request_id", cmd.originalRequestId);
            }
            JsonObject data = new JsonObject();
            data.addProperty("approved", false);
            data.addProperty("cancelled", true);
            data.addProperty("command", cmd.command);
            data.addProperty("message", reason);
            response.add("data", data);
            try {
                cmd.conn.send(GSON.toJson(response));
            } catch (Exception e) {
                LOGGER.debug("Failed to send cancelled command result: {}", e.getMessage());
            }
        }
        LOGGER.info("Cancelled pending command: {} ({}) reason={}", cmd.command, cmd.pendingId, reason);
    }
}
