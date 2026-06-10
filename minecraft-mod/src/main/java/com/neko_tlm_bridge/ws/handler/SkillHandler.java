package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.github.tartaricacid.touhoulittlemaid.ai.agent.skill.SkillInstance;
import com.github.tartaricacid.touhoulittlemaid.ai.agent.skill.SkillLoader;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.server.MinecraftServer;
import org.java_websocket.WebSocket;

import java.util.Map;

/** 技能查询处理器 — 处理 use_skill 请求，查询车万女仆 AI 技能信息 */
public class SkillHandler implements MessageHandlerInterface {
    private final MinecraftServer server;

    public SkillHandler(MinecraftServer server) {
        this.server = server;
    }

    @Override
    public JsonObject handle(JsonObject request, WebSocket conn) {
        String requestId = request.has("request_id") ? request.get("request_id").getAsString() : null;
        if (server == null) {
            return createErrorResponse(requestId, "Server not ready");
        }
        JsonObject data = request.has("data") ? request.getAsJsonObject("data") : new JsonObject();
        String skillName = data.has("skill_name") ? data.get("skill_name").getAsString() : "";
        String maidId = data.has("maid_id") ? data.get("maid_id").getAsString() : "";

        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_SKILL_RESULT);
        if (requestId != null) response.addProperty("request_id", requestId);
        JsonObject resultData = new JsonObject();

        if (skillName.isEmpty()) {
            resultData.addProperty("success", false);
            resultData.addProperty("error", "skill_name is required");
            Map<String, SkillInstance> allSkills = SkillLoader.getAllSkills();
            JsonArray availableArray = new JsonArray();
            for (var entry : allSkills.entrySet()) {
                availableArray.add(entry.getKey());
            }
            resultData.add("available_skills", availableArray);
            response.add("data", resultData);
            return response;
        }

        EntityMaid maid = maidId.isEmpty() ? MaidHelper.findFirstMaid(server) : MaidHelper.findMaidById(server, maidId);
        if (maid == null) {
            resultData.addProperty("success", false);
            resultData.addProperty("error", "Maid not found");
            response.add("data", resultData);
            return response;
        }

        SkillInstance skill = SkillLoader.getSkill(skillName);
        if (skill != null) {
            resultData.addProperty("success", true);
            resultData.addProperty("skill_name", skillName);
            resultData.addProperty("description", skill.description());
            resultData.addProperty("body", skill.body());
            if (skill.references() != null && !skill.references().isEmpty()) {
                JsonObject refs = new JsonObject();
                for (var entry : skill.references().entrySet()) {
                    refs.addProperty(entry.getKey(), entry.getValue());
                }
                resultData.add("references", refs);
            }
        } else {
            resultData.addProperty("success", false);
            resultData.addProperty("error", "Skill not found: " + skillName);
            Map<String, SkillInstance> allSkills = SkillLoader.getAllSkills();
            JsonArray availableArray = new JsonArray();
            for (var entry : allSkills.entrySet()) {
                availableArray.add(entry.getKey());
            }
            resultData.add("available_skills", availableArray);
        }

        response.add("data", resultData);
        return response;
    }
}
