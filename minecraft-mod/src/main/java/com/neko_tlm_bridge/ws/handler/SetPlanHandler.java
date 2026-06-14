package com.neko_tlm_bridge.ws.handler;

import com.google.gson.JsonObject;
import com.neko_tlm_bridge.ws.Protocol;
import com.neko_tlm_bridge.client.PlanOverlayRenderer;
import org.java_websocket.WebSocket;

public class SetPlanHandler implements MessageHandlerInterface {
    @Override
    public JsonObject handle(JsonObject request, WebSocket conn) {
        String requestId = request.has("request_id") ? request.get("request_id").getAsString() : null;
        JsonObject data = request.has("data") ? request.getAsJsonObject("data") : new JsonObject();
        String planText = data.has("plan") ? data.get("plan").getAsString() : "";

        PlanOverlayRenderer.setPlan(planText);

        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_PLAN_RESULT);
        if (requestId != null) response.addProperty("request_id", requestId);
        JsonObject responseData = new JsonObject();
        responseData.addProperty("success", true);
        responseData.addProperty("plan", planText);
        response.add("data", responseData);
        return response;
    }
}
