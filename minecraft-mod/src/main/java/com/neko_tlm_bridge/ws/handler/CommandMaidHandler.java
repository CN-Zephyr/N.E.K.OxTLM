package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.api.task.FunctionCallSwitchResult;
import com.github.tartaricacid.touhoulittlemaid.api.task.IMaidTask;
import com.github.tartaricacid.touhoulittlemaid.entity.ai.brain.MaidSchedule;
import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.github.tartaricacid.touhoulittlemaid.entity.task.TaskManager;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.resources.ResourceLocation;
import org.java_websocket.WebSocket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 女仆控制命令处理器 — 处理 command_maid 请求，包含跟随/坐下/任务/日程/装备等子命令 */
public class CommandMaidHandler implements MessageHandlerInterface {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private final MinecraftServer server;

    public CommandMaidHandler(MinecraftServer server) {
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
        String command = data.has("command") ? data.get("command").getAsString() : "";
        JsonObject args = data.has("args") ? data.getAsJsonObject("args") : new JsonObject();

        EntityMaid maid = MaidHelper.findMaidById(server, maidId);
        if (maid == null) {
            return createErrorResponse(requestId, "Maid not found: " + maidId);
        }
        JsonObject resultData = new JsonObject();
        boolean success = executeCommand(maid, command, args, resultData);
        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_COMMAND_RESULT);
        if (requestId != null) response.addProperty("request_id", requestId);
        resultData.addProperty("success", success);
        resultData.addProperty("command", command);
        response.add("data", resultData);
        return response;
    }

    private boolean executeCommand(EntityMaid maid, String command, JsonObject args, JsonObject resultData) {
        try {
            switch (command) {
                case "switch_follow" -> {
                    boolean follow = args.has("follow") && args.get("follow").getAsBoolean();
                    boolean isHome = maid.isHomeModeEnable();
                    if (follow) {
                        boolean wasSitting = maid.isMaidInSittingPose();
                        if (wasSitting) {
                            maid.setInSittingPose(false);
                        }
                        if (!isHome) {
                            resultData.addProperty("state", wasSitting ? "following_stood_up" : "already_following");
                            return true;
                        }
                        maid.restrictTo(net.minecraft.core.BlockPos.ZERO,
                                com.github.tartaricacid.touhoulittlemaid.config.subconfig.MaidConfig.MAID_NON_HOME_RANGE.get());
                        maid.setHomeModeEnable(false);
                        resultData.addProperty("state", "following");
                        return true;
                    } else {
                        if (isHome) {
                            resultData.addProperty("state", "already_stopped");
                            return true;
                        }
                        maid.getSchedulePos().setHomeModeEnable(maid, maid.blockPosition());
                        maid.setHomeModeEnable(true);
                        resultData.addProperty("state", "stopped");
                        return true;
                    }
                }
                case "switch_sit" -> {
                    boolean sit = args.has("sit") && args.get("sit").getAsBoolean();
                    boolean isSitting = maid.isMaidInSittingPose();
                    if (sit) {
                        if (isSitting) {
                            resultData.addProperty("state", "already_sitting");
                            return true;
                        }
                        maid.setInSittingPose(true);
                        resultData.addProperty("state", "sitting");
                        return true;
                    } else {
                        if (!isSitting) {
                            resultData.addProperty("state", "already_standing");
                            return true;
                        }
                        maid.setInSittingPose(false);
                        resultData.addProperty("state", "standing");
                        return true;
                    }
                }
                case "switch_task" -> {
                    if (args.has("task")) {
                        String taskName = args.get("task").getAsString();
                        try {
                            ResourceLocation taskRL = ResourceLocation.parse(taskName);
                            var taskOpt = TaskManager.findTask(taskRL);
                            if (taskOpt.isPresent()) {
                                IMaidTask task = taskOpt.get();
                                FunctionCallSwitchResult result = task.onFunctionCallSwitch(maid);
                                maid.setTask(task);
                                resultData.addProperty("switch_result", result.name());
                                return true;
                            }
                            resultData.addProperty("error", "Task not found: " + taskName);
                            JsonArray taskList = new JsonArray();
                            for (IMaidTask t : TaskManager.getNotHiddenTaskList(maid)) {
                                taskList.add(t.getUid().toString());
                            }
                            resultData.add("available_tasks", taskList);
                            return false;
                        } catch (Exception e) {
                            LOGGER.error("Error switching task: {}", e.getMessage());
                            resultData.addProperty("error", "Error switching task: " + e.getMessage());
                            return false;
                        }
                    }
                    resultData.addProperty("error", "Missing required argument: task");
                    return false;
                }
                case "switch_schedule" -> {
                    if (args.has("schedule")) {
                        String schedule = args.get("schedule").getAsString();
                        try {
                            MaidSchedule maidSchedule = MaidSchedule.valueOf(schedule.toUpperCase());
                            maid.setSchedule(maidSchedule);
                            resultData.addProperty("schedule", maidSchedule.name());
                            return true;
                        } catch (IllegalArgumentException e) {
                            LOGGER.error("Invalid schedule: {}", schedule);
                            resultData.addProperty("error", "Invalid schedule: " + schedule + ". Valid values: DAY, NIGHT, ALL");
                            return false;
                        }
                    }
                    resultData.addProperty("error", "Missing required argument: schedule");
                    return false;
                }
                case "set_home" -> {
                    resultData.addProperty("error", "set_home command is not implemented yet");
                    return false;
                }
                case "equip_item" -> {
                    if (args.has("slot")) {
                        try {
                            int slot = args.get("slot").getAsInt();
                            var backpack = maid.getAvailableBackpackInv();
                            if (slot < 0 || slot >= backpack.getSlots()) {
                                resultData.addProperty("error", "Invalid slot: " + slot + ". Valid range: 0-" + (backpack.getSlots() - 1));
                                return false;
                            }
                            ItemStack targetItem = backpack.getStackInSlot(slot);
                            if (targetItem.isEmpty()) {
                                resultData.addProperty("error", "Slot " + slot + " is empty");
                                return false;
                            }
                            ItemStack mainHandItem = maid.getMainHandItem();
                            if (!mainHandItem.isEmpty()) {
                                backpack.setStackInSlot(slot, mainHandItem);
                            } else {
                                backpack.setStackInSlot(slot, ItemStack.EMPTY);
                            }
                            maid.setItemInHand(net.minecraft.world.InteractionHand.MAIN_HAND, targetItem.copy());
                            resultData.addProperty("equipped_item", BuiltInRegistries.ITEM.getKey(targetItem.getItem()).toString());
                            resultData.addProperty("slot", slot);
                            return true;
                        } catch (NumberFormatException e) {
                            resultData.addProperty("error", "Invalid slot number");
                            return false;
                        }
                    }
                    if (args.has("item")) {
                        String itemId = args.get("item").getAsString();
                        try {
                            ResourceLocation itemRL = ResourceLocation.parse(itemId);
                            var itemOpt = BuiltInRegistries.ITEM.getOptional(itemRL);
                            if (itemOpt.isEmpty()) {
                                resultData.addProperty("error", "Item not found: " + itemId);
                                return false;
                            }
                            var backpack = maid.getAvailableBackpackInv();
                            int foundSlot = -1;
                            for (int i = 0; i < backpack.getSlots(); i++) {
                                ItemStack stack = backpack.getStackInSlot(i);
                                if (!stack.isEmpty() && BuiltInRegistries.ITEM.getKey(stack.getItem()).equals(itemRL)) {
                                    foundSlot = i;
                                    break;
                                }
                            }
                            if (foundSlot < 0) {
                                resultData.addProperty("error", "Item " + itemId + " not found in maid inventory");
                                return false;
                            }
                            ItemStack targetItem = backpack.getStackInSlot(foundSlot);
                            ItemStack mainHandItem = maid.getMainHandItem();
                            if (!mainHandItem.isEmpty()) {
                                backpack.setStackInSlot(foundSlot, mainHandItem);
                            } else {
                                backpack.setStackInSlot(foundSlot, ItemStack.EMPTY);
                            }
                            maid.setItemInHand(net.minecraft.world.InteractionHand.MAIN_HAND, targetItem.copy());
                            resultData.addProperty("equipped_item", itemId);
                            resultData.addProperty("slot", foundSlot);
                            return true;
                        } catch (Exception e) {
                            resultData.addProperty("error", "Error equipping item: " + e.getMessage());
                            return false;
                        }
                    }
                    resultData.addProperty("error", "Missing required argument: slot (int) or item (item ID string)");
                    return false;
                }
                default -> {
                    resultData.addProperty("error", "Unknown command: " + command);
                    return false;
                }
            }
        } catch (Exception e) {
            LOGGER.error("Error executing command {}: {}", command, e.getMessage());
            return false;
        }
    }
}
