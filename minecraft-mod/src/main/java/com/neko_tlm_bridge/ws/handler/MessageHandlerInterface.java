package com.neko_tlm_bridge.ws.handler;

import com.google.gson.JsonObject;
import com.neko_tlm_bridge.ws.Protocol;
import org.java_websocket.WebSocket;

/** WebSocket 消息处理器公共接口，所有 handler 必须实现此接口 */
public interface MessageHandlerInterface {
    JsonObject handle(JsonObject request, WebSocket conn);

    default JsonObject createErrorResponse(String requestId, String errorMessage) {
        JsonObject error = new JsonObject();
        error.addProperty("type", Protocol.TYPE_ERROR);
        if (requestId != null) error.addProperty("request_id", requestId);
        JsonObject data = new JsonObject();
        data.addProperty("message", errorMessage);
        error.add("data", data);
        return error;
    }
}
