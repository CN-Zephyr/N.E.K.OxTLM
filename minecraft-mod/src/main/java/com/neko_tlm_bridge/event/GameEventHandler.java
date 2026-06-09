package com.neko_tlm_bridge.event;

import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.config.ModConfig;
import com.neko_tlm_bridge.ws.NekoWebSocketServer;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.neoforged.bus.api.SubscribeEvent;
import net.neoforged.fml.common.EventBusSubscriber;
import net.neoforged.neoforge.event.entity.player.PlayerContainerEvent;
import net.neoforged.neoforge.event.entity.living.LivingDamageEvent;
import net.neoforged.neoforge.event.entity.living.LivingDeathEvent;
import net.neoforged.neoforge.event.entity.living.LivingIncomingDamageEvent;
import net.neoforged.neoforge.event.ServerChatEvent;
import net.neoforged.neoforge.items.ItemStackHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.Map;

@EventBusSubscriber
public class GameEventHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private static NekoWebSocketServer webSocketServer;

    // Track maid inventory snapshots when player opens backpack
    private static final Map<String, Map<Integer, String>> openInventorySnapshots = new HashMap<>();
    // The maid_id that the plugin wants us to monitor for inventory changes
    private static String monitoredMaidId = "";

    public static void setMonitoredMaidId(String maidId) {
        monitoredMaidId = maidId != null ? maidId : "";
    }

    public static void setWebSocketServer(NekoWebSocketServer server) {
        webSocketServer = server;
    }

    @SubscribeEvent
    public static void onLivingHurt(LivingIncomingDamageEvent event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;
        if (event.getEntity() instanceof EntityMaid maid) {
            JsonObject eventData = new JsonObject();
            eventData.addProperty("event_type", "maid_hurt");
            eventData.addProperty("maid_id", maid.getStringUUID());
            eventData.addProperty("maid_name", maid.getName().getString());
            eventData.addProperty("damage", event.getAmount());
            eventData.addProperty("health", maid.getHealth() - event.getAmount());
            eventData.addProperty("max_health", maid.getMaxHealth());
            if (event.getSource().getEntity() instanceof Player player) {
                eventData.addProperty("attacker", player.getName().getString());
            }
            webSocketServer.broadcastEvent(eventData);
        }
    }

    @SubscribeEvent
    public static void onServerChat(ServerChatEvent event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;
        String message = event.getRawText();
        net.minecraft.server.level.ServerPlayer player = event.getPlayer();
        JsonObject chatData = new JsonObject();
        chatData.addProperty("event_type", "chat");
        chatData.addProperty("sender", player.getName().getString());
        chatData.addProperty("message", message);
        chatData.addProperty("x", player.getX());
        chatData.addProperty("y", player.getY());
        chatData.addProperty("z", player.getZ());
        webSocketServer.broadcastChatMessage(chatData);
    }

    @SubscribeEvent
    public static void onLivingDeath(LivingDeathEvent event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;

        LivingEntity entity = event.getEntity();

        // Maid death
        if (entity instanceof EntityMaid maid) {
            JsonObject eventData = new JsonObject();
            eventData.addProperty("event_type", Protocol.EVENT_MAID_DEATH);
            eventData.addProperty("maid_id", maid.getStringUUID());
            eventData.addProperty("maid_name", maid.getName().getString());
            eventData.addProperty("cause", event.getSource().getMsgId());
            if (event.getSource().getEntity() instanceof LivingEntity killer) {
                eventData.addProperty("killer", killer.getName().getString());
            }
            webSocketServer.broadcastEvent(eventData);
        }

        // Player death
        if (entity instanceof Player player) {
            JsonObject eventData = new JsonObject();
            eventData.addProperty("event_type", Protocol.EVENT_PLAYER_DEATH);
            eventData.addProperty("player_name", player.getName().getString());
            eventData.addProperty("cause", event.getSource().getMsgId());
            if (event.getSource().getEntity() instanceof LivingEntity killer) {
                eventData.addProperty("killer", killer.getName().getString());
            }
            webSocketServer.broadcastEvent(eventData);
        }
    }

    // Weather and time tracking
    private static boolean lastRaining = false;
    private static boolean lastThundering = false;
    private static boolean lastIsNight = false;
    private static long lastWeatherCheckTick = 0;
    private static final long WEATHER_CHECK_INTERVAL = 100; // Check every 5 seconds (100 ticks)

    // Biome change tracking with debounce to prevent bouncing at boundaries
    private static String lastReportedBiome = "";
    private static String candidateBiome = "";
    private static long candidateBiomeStartTick = 0;
    private static final long BIOME_DEBOUNCE_TICKS = 200; // Must stay in new biome for 10 seconds

    public static void onServerTick(net.neoforged.neoforge.event.tick.ServerTickEvent.Post event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;

        net.minecraft.server.MinecraftServer server = event.getServer();
        if (server == null) return;

        ServerLevel overworld = server.getLevel(Level.OVERWORLD);
        if (overworld == null) return;

        long currentTick = overworld.getGameTime();

        // Biome change detection (runs every tick for debounce accuracy)
        if (!monitoredMaidId.isEmpty()) {
            EntityMaid maid = findMaidById(monitoredMaidId, server);
            if (maid != null) {
                String currentBiome = maid.level().getBiome(maid.blockPosition())
                        .unwrapKey()
                        .map(k -> k.location().toString())
                        .orElse("unknown");
                if (currentBiome.equals(lastReportedBiome)) {
                    // Back to reported biome, reset candidate
                    candidateBiome = "";
                } else if (currentBiome.equals(candidateBiome)) {
                    // Still in candidate biome, check debounce
                    if (currentTick - candidateBiomeStartTick >= BIOME_DEBOUNCE_TICKS) {
                        JsonObject eventData = new JsonObject();
                        eventData.addProperty("event_type", Protocol.EVENT_BIOME_CHANGE);
                        eventData.addProperty("maid_id", maid.getStringUUID());
                        eventData.addProperty("maid_name", maid.getName().getString());
                        eventData.addProperty("biome", currentBiome);
                        eventData.addProperty("old_biome", lastReportedBiome);
                        webSocketServer.broadcastEvent(eventData);
                        lastReportedBiome = currentBiome;
                        candidateBiome = "";
                    }
                } else {
                    // New biome detected, start debounce timer
                    candidateBiome = currentBiome;
                    candidateBiomeStartTick = currentTick;
                }
            }
        }

        // Weather and time checks (throttled)
        if (!ModConfig.WEATHER_EVENT_ENABLED.get() && !ModConfig.TIME_EVENT_ENABLED.get()) return;
        if (currentTick - lastWeatherCheckTick < WEATHER_CHECK_INTERVAL) return;
        lastWeatherCheckTick = currentTick;

        // Weather change detection
        if (ModConfig.WEATHER_EVENT_ENABLED.get()) {
            boolean isRaining = overworld.isRaining();
            boolean isThundering = overworld.isThundering();
            if (isRaining != lastRaining || isThundering != lastThundering) {
                JsonObject eventData = new JsonObject();
                eventData.addProperty("event_type", Protocol.EVENT_WEATHER_CHANGE);
                eventData.addProperty("raining", isRaining);
                eventData.addProperty("thundering", isThundering);
                webSocketServer.broadcastEvent(eventData);
                lastRaining = isRaining;
                lastThundering = isThundering;
            }
        }

        // Time phase change detection (day/night)
        if (ModConfig.TIME_EVENT_ENABLED.get()) {
            long dayTime = overworld.getDayTime() % 24000;
            boolean isNight = dayTime >= 12542 && dayTime < 23460;
            if (isNight != lastIsNight) {
                JsonObject eventData = new JsonObject();
                eventData.addProperty("event_type", Protocol.EVENT_TIME_PHASE_CHANGE);
                eventData.addProperty("phase", isNight ? "night" : "day");
                eventData.addProperty("day_time", overworld.getDayTime() % 24000);
                webSocketServer.broadcastEvent(eventData);
                lastIsNight = isNight;
            }
        }
    }

    @SubscribeEvent
    public static void onAdvancement(net.neoforged.neoforge.event.entity.player.AdvancementEvent.AdvancementEarnEvent event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;
        net.minecraft.advancements.AdvancementHolder holder = event.getAdvancement();
        net.minecraft.advancements.Advancement advancement = holder.value();
        // Only report displayable advancements (visible in toast)
        if (advancement.display().isEmpty()) return;

        JsonObject eventData = new JsonObject();
        eventData.addProperty("event_type", Protocol.EVENT_ADVANCEMENT);
        eventData.addProperty("player_name", event.getEntity().getName().getString());
        net.minecraft.advancements.DisplayInfo display = advancement.display().get();
        eventData.addProperty("title", display.getTitle().getString());
        eventData.addProperty("description", display.getDescription().getString());
        webSocketServer.broadcastEvent(eventData);
    }

    @SubscribeEvent
    public static void onContainerOpen(PlayerContainerEvent.Open event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;
        if (monitoredMaidId.isEmpty()) return;
        if (!(event.getEntity() instanceof Player player)) return;

        // Find the monitored maid
        EntityMaid maid = findMaidById(monitoredMaidId, player.getServer());
        if (maid == null) return;

        // Only snapshot if the player is the maid's owner
        if (maid.getOwner() == null || !maid.getOwner().getUUID().equals(player.getUUID())) return;

        Map<Integer, String> snapshot = new HashMap<>();
        ItemStackHandler inv = maid.getMaidInv();
        for (int i = 0; i < inv.getSlots(); i++) {
            ItemStack stack = inv.getStackInSlot(i);
            if (!stack.isEmpty()) {
                snapshot.put(i, BuiltInRegistries.ITEM.getKey(stack.getItem()).toString() + "|" + stack.getCount());
            }
        }
        openInventorySnapshots.put(player.getStringUUID(), snapshot);
    }

    @SubscribeEvent
    public static void onContainerClose(PlayerContainerEvent.Close event) {
        if (!ModConfig.EVENT_PUSH_ENABLED.get() || webSocketServer == null || !webSocketServer.hasClients()) return;
        if (monitoredMaidId.isEmpty()) return;
        if (!(event.getEntity() instanceof Player player)) return;

        Map<Integer, String> oldSnapshot = openInventorySnapshots.remove(player.getStringUUID());
        if (oldSnapshot == null) return;

        // Find the monitored maid
        EntityMaid maid = findMaidById(monitoredMaidId, player.getServer());
        if (maid == null) return;

        // Only track if the player is the maid's owner
        if (maid.getOwner() == null || !maid.getOwner().getUUID().equals(player.getUUID())) return;

        // Take new snapshot
        Map<Integer, String> newSnapshot = new HashMap<>();
        ItemStackHandler inv = maid.getMaidInv();
        for (int i = 0; i < inv.getSlots(); i++) {
            ItemStack stack = inv.getStackInSlot(i);
            if (!stack.isEmpty()) {
                newSnapshot.put(i, BuiltInRegistries.ITEM.getKey(stack.getItem()).toString() + "|" + stack.getCount());
            }
        }

        // Calculate diff (format: "item_id|count", e.g. "minecraft:diamond_sword|2")
        java.util.List<String> added = new java.util.ArrayList<>();
        java.util.List<String> removed = new java.util.ArrayList<>();

        for (Map.Entry<Integer, String> newEntry : newSnapshot.entrySet()) {
            String oldVal = oldSnapshot.get(newEntry.getKey());
            if (!newEntry.getValue().equals(oldVal)) {
                String newVal = newEntry.getValue();
                int sepIdx = newVal.lastIndexOf('|');
                String itemName = sepIdx > 0 ? newVal.substring(0, sepIdx) : newVal;
                int newCount = sepIdx > 0 ? Integer.parseInt(newVal.substring(sepIdx + 1)) : 1;
                if (oldVal == null) {
                    added.add(itemName + "x" + newCount);
                } else {
                    int oldSepIdx = oldVal.lastIndexOf('|');
                    String oldItemName = oldSepIdx > 0 ? oldVal.substring(0, oldSepIdx) : oldVal;
                    int oldCount = oldSepIdx > 0 ? Integer.parseInt(oldVal.substring(oldSepIdx + 1)) : 1;
                    if (itemName.equals(oldItemName)) {
                        if (newCount > oldCount) {
                            added.add(itemName + "x" + (newCount - oldCount));
                        } else if (newCount < oldCount) {
                            removed.add(itemName + "x" + (oldCount - newCount));
                        }
                    } else {
                        removed.add(oldItemName + "x" + oldCount);
                        added.add(itemName + "x" + newCount);
                    }
                }
            }
        }

        for (Map.Entry<Integer, String> oldEntry : oldSnapshot.entrySet()) {
            if (!newSnapshot.containsKey(oldEntry.getKey())) {
                String oldVal = oldEntry.getValue();
                int sepIdx = oldVal.lastIndexOf('|');
                String itemName = sepIdx > 0 ? oldVal.substring(0, sepIdx) : oldVal;
                int count = sepIdx > 0 ? Integer.parseInt(oldVal.substring(sepIdx + 1)) : 1;
                removed.add(itemName + "x" + count);
            }
        }

        if (added.isEmpty() && removed.isEmpty()) return;

        JsonObject eventData = new JsonObject();
        eventData.addProperty("event_type", Protocol.EVENT_INVENTORY_CHANGE);
        eventData.addProperty("maid_id", maid.getStringUUID());
        eventData.addProperty("maid_name", maid.getName().getString());
        eventData.addProperty("player_name", player.getName().getString());

        JsonArray addedArray = new JsonArray();
        for (String item : added) addedArray.add(item);
        eventData.add("added", addedArray);

        JsonArray removedArray = new JsonArray();
        for (String item : removed) removedArray.add(item);
        eventData.add("removed", removedArray);

        webSocketServer.broadcastEvent(eventData);
    }

    private static EntityMaid findMaidById(String maidId, net.minecraft.server.MinecraftServer server) {
        try {
            java.util.UUID uuid = java.util.UUID.fromString(maidId);
            if (server != null) {
                for (net.minecraft.server.level.ServerLevel level : server.getAllLevels()) {
                    net.minecraft.world.entity.Entity entity = level.getEntity(uuid);
                    if (entity instanceof EntityMaid maid) {
                        return maid;
                    }
                }
            }
        } catch (Exception ignored) {}
        return null;
    }
}
