package com.neko_tlm_bridge.ws.handler;

import com.google.gson.JsonObject;
import com.neko_tlm_bridge.config.ModConfig;
import com.neko_tlm_bridge.ws.NekoCommand;
import com.neko_tlm_bridge.ws.PendingCommandManager;
import com.neko_tlm_bridge.ws.Protocol;
import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
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
        String command = data.has("command") ? data.get("command").getAsString().trim() : "";
        String maidId = data.has("maid_id") ? data.get("maid_id").getAsString().trim() : "";

        if (command.isBlank()) {
            return createErrorResponse(requestId, "Command is empty");
        }
        if (maidId.isBlank()) {
            return createErrorResponse(requestId, "Maid id is required to resolve the client player");
        }

        ServerPlayer targetPlayer = resolveTargetPlayer(maidId);
        if (targetPlayer == null) {
            return createErrorResponse(requestId, "The assigned maid owner is not online");
        }

        String pendingId = pendingCommandManager.addPendingCommand(
                requestId, command, conn, targetPlayer.getUUID());
        NekoCommand.sendCommandRequest(targetPlayer, pendingId, command);
        LOGGER.info("Command execution request queued: {} (pending_id={}, request_id={})", command, pendingId, requestId);

        // No immediate response — response is sent when command is approved/rejected/expired
        return null;
    }

    private ServerPlayer resolveTargetPlayer(String maidId) {
        EntityMaid maid = MaidHelper.findMaidById(server, maidId);
        if (maid != null && maid.getOwner() instanceof ServerPlayer player) {
            return player;
        }
        MaidHelper.UnloadedMaid unloaded = MaidHelper.findUnloadedMaid(server, maidId);
        return unloaded == null ? null : unloaded.owner();
    }
}
