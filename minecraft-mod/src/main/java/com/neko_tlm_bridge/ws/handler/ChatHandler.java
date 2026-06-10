package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.config.ModConfig;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import org.java_websocket.WebSocket;

/** 聊天消息处理器 — 处理 send_chat 请求，让女仆在游戏内发送聊天消息和气泡 */
public class ChatHandler implements MessageHandlerInterface {
    private final MinecraftServer server;

    public ChatHandler(MinecraftServer server) {
        this.server = server;
    }

    @Override
    public JsonObject handle(JsonObject request, WebSocket conn) {
        String requestId = request.has("request_id") ? request.get("request_id").getAsString() : null;
        if (server == null) {
            return createErrorResponse(requestId, "Server not ready");
        }
        JsonObject data = request.has("data") ? request.getAsJsonObject("data") : new JsonObject();
        String maidId = data.has("maid_id") ? data.get("maid_id").getAsString() : "";
        String message = data.has("message") ? data.get("message").getAsString() : "";

        EntityMaid maid = MaidHelper.findMaidById(server, maidId);
        if (maid == null) {
            return createErrorResponse(requestId, "Maid not found: " + maidId);
        }
        String maidName = maid.getName().getString();
        if (ModConfig.CHAT_BOX_ENABLED.get()) {
            Component chatMessage = Component.literal("[" + maidName + "] " + message);
            server.getPlayerList().broadcastSystemMessage(chatMessage, false);
        }

        if (ModConfig.CHAT_BUBBLE_ENABLED.get()) {
            maid.getChatBubbleManager().addChatBubble(
                    com.github.tartaricacid.touhoulittlemaid.entity.chatbubble.implement.TextChatBubbleData.type2(
                            Component.literal(message)
                    )
            );
        }

        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_CHAT_RESULT);
        if (requestId != null) response.addProperty("request_id", requestId);
        JsonObject resultData = new JsonObject();
        resultData.addProperty("success", true);
        response.add("data", resultData);
        return response;
    }
}
