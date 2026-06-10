package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.api.task.IMaidTask;
import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.github.tartaricacid.touhoulittlemaid.entity.task.TaskManager;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.tlm.NekoAttackTargetStore;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.ai.memory.MemoryModuleType;
import net.minecraft.world.phys.AABB;
import org.java_websocket.WebSocket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.UUID;

/** 攻击目标管理处理器 — 处理 attack_target 请求，设置女仆的攻击目标队列 */
public class AttackTargetHandler implements MessageHandlerInterface {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private final MinecraftServer server;

    public AttackTargetHandler(MinecraftServer server) {
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
        String targetEntityId = data.has("target_entity_id") ? data.get("target_entity_id").getAsString() : "";
        JsonArray targetEntityIds = data.has("target_entity_ids") ? data.getAsJsonArray("target_entity_ids") : new JsonArray();

        if (maidId.isEmpty()) {
            return createErrorResponse(requestId, "maid_id is required");
        }
        if (targetEntityId.isEmpty() && targetEntityIds.isEmpty()) {
            return createErrorResponse(requestId, "target_entity_id or target_entity_ids is required");
        }

        EntityMaid maid = MaidHelper.findMaidById(server, maidId);
        if (maid == null) {
            return createErrorResponse(requestId, "Maid not found: " + maidId);
        }

        if (maid.isMaidInSittingPose()) {
            maid.setInSittingPose(false);
            LOGGER.info("Attack target: maid {} was sitting, stood up", maid.getName().getString());
        }

        if (maid.isHomeModeEnable()) {
            maid.restrictTo(net.minecraft.core.BlockPos.ZERO,
                    com.github.tartaricacid.touhoulittlemaid.config.subconfig.MaidConfig.MAID_NON_HOME_RANGE.get());
            maid.setHomeModeEnable(false);
            LOGGER.info("Attack target: maid {} was in home mode, disabled home mode", maid.getName().getString());
        }

        List<NekoAttackTargetStore.TargetEntry> allEntries = new java.util.ArrayList<>();
        LivingEntity firstTarget = null;

        if (!targetEntityId.isEmpty()) {
            UUID targetUUID;
            try {
                targetUUID = UUID.fromString(targetEntityId);
            } catch (IllegalArgumentException e) {
                return createErrorResponse(requestId, "Invalid target_entity_id: " + targetEntityId);
            }
            LivingEntity target = null;
            for (ServerLevel level : server.getAllLevels()) {
                Entity entity = level.getEntity(targetUUID);
                if (entity instanceof LivingEntity living && living.isAlive()) {
                    target = living;
                    break;
                }
            }
            if (target == null) {
                return createErrorResponse(requestId, "Target entity not found or not alive: " + targetEntityId);
            }
            allEntries.add(new NekoAttackTargetStore.TargetEntry(targetUUID, target.getName().getString()));
            firstTarget = target;
        }

        if (!targetEntityIds.isEmpty()) {
            for (int i = 0; i < targetEntityIds.size(); i++) {
                String eid = targetEntityIds.get(i).getAsString();
                UUID uuid;
                try {
                    uuid = UUID.fromString(eid);
                } catch (IllegalArgumentException e) {
                    continue;
                }
                LivingEntity target = null;
                for (ServerLevel level : server.getAllLevels()) {
                    Entity entity = level.getEntity(uuid);
                    if (entity instanceof LivingEntity living && living.isAlive()) {
                        target = living;
                        break;
                    }
                }
                if (target != null) {
                    allEntries.add(new NekoAttackTargetStore.TargetEntry(uuid, target.getName().getString()));
                    if (firstTarget == null) {
                        firstTarget = target;
                    }
                }
            }
        }

        if (allEntries.isEmpty()) {
            return createErrorResponse(requestId, "No valid target entities found");
        }

        if (allEntries.size() == 1) {
            NekoAttackTargetStore.setTarget(maid.getUUID(), allEntries.get(0).targetEntityId, allEntries.get(0).targetName);
        } else {
            NekoAttackTargetStore.setTargets(maid.getUUID(), allEntries);
        }

        try {
            IMaidTask currentTask = maid.getTask();
            String currentTaskId = currentTask != null ? currentTask.getUid().toString() : "";
            boolean isAttackTask = currentTaskId.endsWith(":attack")
                    || currentTaskId.endsWith(":ranged_attack")
                    || currentTaskId.endsWith(":crossbow_attack")
                    || currentTaskId.endsWith(":danmaku_attack")
                    || currentTaskId.endsWith(":trident_attack");

            if (!isAttackTask) {
                String[] attackTaskIds = {
                        "touhou_little_maid:attack",
                        "touhou_little_maid:ranged_attack",
                        "touhou_little_maid:crossbow_attack",
                        "touhou_little_maid:danmaku_attack",
                        "touhou_little_maid:trident_attack"
                };
                IMaidTask foundTask = null;
                for (String taskId : attackTaskIds) {
                    ResourceLocation taskRL = ResourceLocation.parse(taskId);
                    var taskOpt = TaskManager.findTask(taskRL);
                    if (taskOpt.isPresent()) {
                        foundTask = taskOpt.get();
                        break;
                    }
                }
                if (foundTask != null) {
                    foundTask.onFunctionCallSwitch(maid);
                    maid.setTask(foundTask);
                    LOGGER.info("Attack target: switched maid {} to attack task {}", maid.getName().getString(), foundTask.getUid());
                } else {
                    LOGGER.warn("Attack target: no attack task available for maid {}", maid.getName().getString());
                }
            }
        } catch (Exception e) {
            LOGGER.warn("Attack target: failed to switch attack task: {}", e.getMessage());
        }

        maid.getBrain().setMemory(MemoryModuleType.ATTACK_TARGET, firstTarget);
        maid.getBrain().setMemory(MemoryModuleType.LOOK_TARGET, new net.minecraft.world.entity.ai.behavior.EntityTracker(firstTarget, true));

        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_ATTACK_TARGET_RESULT);
        if (requestId != null) response.addProperty("request_id", requestId);
        JsonObject resultData = new JsonObject();
        resultData.addProperty("status", "dispatched");
        resultData.addProperty("maid_id", maidId);
        resultData.addProperty("message", "已通知" + maid.getName().getString() + "切换攻击模式，正在搜索目标");
        resultData.addProperty("target_count", allEntries.size());
        JsonArray targetNames = new JsonArray();
        for (NekoAttackTargetStore.TargetEntry e : allEntries) {
            targetNames.add(e.targetName);
        }
        resultData.add("target_names", targetNames);
        response.add("data", resultData);

        LOGGER.info("Set attack target for maid {} -> {} target(s): {}", maid.getName().getString(), allEntries.size(),
                allEntries.stream().map(e -> e.targetName).reduce((a, b) -> a + ", " + b).orElse(""));

        return response;
    }
}
