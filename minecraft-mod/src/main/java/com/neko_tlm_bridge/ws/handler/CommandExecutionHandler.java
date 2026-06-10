package com.neko_tlm_bridge.ws.handler;

import com.google.gson.JsonObject;
import com.neko_tlm_bridge.config.ModConfig;
import com.neko_tlm_bridge.ws.NekoCommand;
import com.neko_tlm_bridge.ws.PendingCommandManager;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.server.MinecraftServer;
import org.java_websocket.WebSocket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 服务器命令执行处理器 — 处理 execute_command 请求，需玩家在游戏内确认后执行 */
public class CommandExecutionHandler implements MessageHandlerInterface {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private final MinecraftServer server;
    private final PendingCommandManager pendingCommandManager;

    public CommandExecutionHandler(MinecraftServer server, PendingCommandManager pendingCommandManager) {
        this.server = server;
        this.pendingCommandManager = pendingCommandManager;
    }

    @Override
    public JsonObject handle(JsonObject request, WebSocket conn) {
        String requestId = request.has("request_id") ? request.get("request_id").getAsString() : null;
        if (server == null) {
            return createErrorResponse(requestId, "Server not ready");
        }
        if (!ModConfig.COMMAND_EXECUTION_ENABLED.get()) {
            return createErrorResponse(requestId, "Command execution is disabled in config");
        }
        JsonObject data = request.has("data") ? request.getAsJsonObject("data") : new JsonObject();
        String command = data.has("command") ? data.get("command").getAsString() : "";

        if (command.isEmpty()) {
            return createErrorResponse(requestId, "Command is empty");
        }

        String pendingId = pendingCommandManager.addPendingCommand(requestId, command, conn);
        NekoCommand.broadcastCommandRequest(server, pendingId, command);
        LOGGER.info("Command execution request queued: {} (pending_id={}, request_id={})", command, pendingId, requestId);

        // No immediate response — response is sent when command is approved/rejected/expired
        return null;
    }
}
