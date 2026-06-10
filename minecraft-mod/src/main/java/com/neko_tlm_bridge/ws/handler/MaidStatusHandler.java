package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.api.task.IMaidTask;
import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.github.tartaricacid.touhoulittlemaid.entity.task.TaskManager;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.item.ItemStack;
import org.java_websocket.WebSocket;

/** 女仆状态查询处理器 — 处理 get_maid_status 请求，返回所有女仆的详细信息 */
public class MaidStatusHandler implements MessageHandlerInterface {
    private final MinecraftServer server;

    public MaidStatusHandler(MinecraftServer server) {
        this.server = server;
    }

    @Override
    public JsonObject handle(JsonObject request, WebSocket conn) {
        String requestId = request.has("request_id") ? request.get("request_id").getAsString() : null;
        if (server == null) {
            return createErrorResponse(requestId, "Server not ready");
        }
        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_MAID_STATUS);
        if (requestId != null) response.addProperty("request_id", requestId);
        JsonArray maidsArray = new JsonArray();
        for (ServerLevel level : server.getAllLevels()) {
            for (EntityMaid maid : level.getEntitiesOfClass(EntityMaid.class, new AABB(level.getWorldBorder().getMinX(), level.getMinBuildHeight(), level.getWorldBorder().getMinZ(), level.getWorldBorder().getMaxX(), level.getMaxBuildHeight(), level.getWorldBorder().getMaxZ()))) {
                maidsArray.add(serializeMaid(maid));
            }
        }
        JsonObject data = new JsonObject();
        data.add("maids", maidsArray);
        response.add("data", data);
        return response;
    }

    private JsonObject serializeMaid(EntityMaid maid) {
        JsonObject obj = new JsonObject();
        obj.addProperty("id", maid.getStringUUID());
        obj.addProperty("name", maid.getName().getString());
        obj.addProperty("health", maid.getHealth());
        obj.addProperty("max_health", maid.getMaxHealth());
        JsonObject pos = new JsonObject();
        pos.addProperty("x", maid.getX());
        pos.addProperty("y", maid.getY());
        pos.addProperty("z", maid.getZ());
        obj.add("position", pos);
        obj.addProperty("dimension", maid.level().dimension().location().toString());
        obj.addProperty("is_sitting", maid.isMaidInSittingPose());
        obj.addProperty("is_following", !maid.isHomeModeEnable());
        IMaidTask currentTask = maid.getTask();
        obj.addProperty("task", currentTask != null ? currentTask.getUid().toString() : "");
        if (maid.getOwner() != null) {
            obj.addProperty("owner", maid.getOwner().getName().getString());
        }
        String mainHand = maid.getMainHandItem().isEmpty() ? ""
                : BuiltInRegistries.ITEM.getKey(maid.getMainHandItem().getItem()).toString();
        String offHand = maid.getOffhandItem().isEmpty() ? ""
                : BuiltInRegistries.ITEM.getKey(maid.getOffhandItem().getItem()).toString();
        obj.addProperty("main_hand_item", mainHand);
        obj.addProperty("off_hand_item", offHand);
        JsonArray availableTasks = new JsonArray();
        for (IMaidTask t : TaskManager.getNotHiddenTaskList(maid)) {
            JsonObject taskObj = new JsonObject();
            taskObj.addProperty("id", t.getUid().toString());
            taskObj.addProperty("name", t.getName().getString());
            availableTasks.add(taskObj);
        }
        obj.add("available_tasks", availableTasks);
        return obj;
    }
}
