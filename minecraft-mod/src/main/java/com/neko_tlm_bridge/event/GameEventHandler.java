package com.neko_tlm_bridge.event;

import com.github.tartaricacid.touhoulittlemaid.api.game.gomoku.Point;
import com.github.tartaricacid.touhoulittlemaid.api.game.gomoku.Statue;
import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import com.github.tartaricacid.touhoulittlemaid.tileentity.TileEntityGomoku;
import com.github.tartaricacid.touhoulittlemaid.tileentity.TileEntityWChess;
import com.github.tartaricacid.touhoulittlemaid.tileentity.TileEntityCChess;
import com.github.tartaricacid.touhoulittlemaid.tileentity.TileEntityJoy;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.neko_tlm_bridge.config.ModConfig;
import com.neko_tlm_bridge.ws.NekoWebSocketServer;
import com.neko_tlm_bridge.ws.Protocol;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
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

    // Chess game tracking
    private static final String BOARD_GAMES_TASK_UID = "touhou_little_maid:board_games";
    private static final long CHESS_CHECK_INTERVAL = 20; // Check every 1 second (20 ticks)
    private static final int CHESS_SEARCH_RANGE = 4; // Search for chess boards within 4 blocks
    private static long lastChessCheckTick = 0;

    // Current chess game state (null = no game in progress)
    private static ChessGameState currentChessGame = null;
    // Board positions that have ended but not yet reset — skip these to prevent re-triggering
    private static BlockPos endedBoardPos = null;

    /** Tracks the state of an ongoing chess game */
    private static class ChessGameState {
        String gameType;       // "gomoku", "wchess", "cchess"
        BlockPos boardPos;
        int lastMoveCount;
        boolean lastPlayerTurn;
        boolean gameEndNotified;
        // For mid-game commentary: next move count at which to trigger commentary
        int nextCommentaryAt;

        ChessGameState(String gameType, BlockPos boardPos, int moveCount, boolean playerTurn) {
            this.gameType = gameType;
            this.boardPos = boardPos;
            this.lastMoveCount = moveCount;
            this.lastPlayerTurn = playerTurn;
            this.gameEndNotified = false;
            this.nextCommentaryAt = moveCount + 3 + (int)(Math.random() * 6); // 3-8 moves later
        }
    }

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

                // Chess game detection (throttled)
                if (currentTick - lastChessCheckTick >= CHESS_CHECK_INTERVAL) {
                    lastChessCheckTick = currentTick;
                    checkChessGame(maid, server);
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

    // ── Chess game detection ──

    private static void checkChessGame(EntityMaid maid, net.minecraft.server.MinecraftServer server) {
        boolean isPlayingChess = BOARD_GAMES_TASK_UID.equals(maid.getTask().getUid().toString());

        if (!isPlayingChess) {
            // Maid is not on board_games task — clear all chess state
            if (currentChessGame != null) {
                LOGGER.info("[Chess] Maid left board_games task, clearing game state (was: {})", currentChessGame.gameType);
                currentChessGame = null;
            }
            endedBoardPos = null;
            return;
        }

        // Maid is on board_games task — find nearby chess board
        TileEntityJoy boardEntity = findNearbyChessBoard(maid);
        if (boardEntity == null) {
            // No board found nearby — maid might be walking to one
            return;
        }

        BlockPos boardPos = boardEntity.getWorldPosition();

        // Skip boards that have ended but not yet been reset
        if (endedBoardPos != null && endedBoardPos.equals(boardPos)) {
            // Check if the board has been reset (game is in progress again)
            if (!isGameEnded(boardEntity)) {
                // Board has been reset — allow new game detection
                LOGGER.info("[Chess] Board at {} has been reset, allowing new game", boardPos);
                endedBoardPos = null;
            } else {
                // Still ended — skip to prevent re-triggering
                return;
            }
        }

        String gameType = getGameType(boardEntity);

        if (currentChessGame == null || !currentChessGame.boardPos.equals(boardPos)) {
            // Check if this board is already in an ended state — skip it
            if (isGameEnded(boardEntity)) {
                LOGGER.info("[Chess] Board at {} is already ended, skipping", boardPos);
                endedBoardPos = boardPos;
                return;
            }

            // New game detected
            currentChessGame = new ChessGameState(gameType, boardPos,
                    getMoveCount(boardEntity), isPlayerTurn(boardEntity));

            // Find the opponent (player near the board)
            String opponent = findNearbyPlayerName(boardEntity, server);

            LOGGER.info("[Chess] Game start: type={}, opponent={}, boardPos={}", gameType, opponent, boardPos);

            JsonObject eventData = new JsonObject();
            eventData.addProperty("event_type", Protocol.EVENT_CHESS_GAME_START);
            eventData.addProperty("maid_id", maid.getStringUUID());
            eventData.addProperty("maid_name", maid.getName().getString());
            eventData.addProperty("game_type", gameType);
            eventData.addProperty("opponent", opponent);
            if ("gomoku".equals(gameType)) {
                eventData.addProperty("maid_skill", maid.getGameRecordManager().getGomokuWinCount());
            }
            webSocketServer.broadcastEvent(eventData);
            return;
        }

        // Existing game — check for state changes
        int currentMoveCount = getMoveCount(boardEntity);
        boolean currentPlayerTurn = isPlayerTurn(boardEntity);

        // Check if game ended
        boolean gameEnded = isGameEnded(boardEntity);
        if (gameEnded && !currentChessGame.gameEndNotified) {
            currentChessGame.gameEndNotified = true;
            String result = getGameResult(boardEntity, maid);
            String opponent = findNearbyPlayerName(boardEntity, server);

            LOGGER.info("[Chess] Game end: type={}, result={}, moves={}, opponent={}", currentChessGame.gameType, result, currentMoveCount, opponent);

            JsonObject eventData = new JsonObject();
            eventData.addProperty("event_type", Protocol.EVENT_CHESS_GAME_END);
            eventData.addProperty("maid_id", maid.getStringUUID());
            eventData.addProperty("maid_name", maid.getName().getString());
            eventData.addProperty("game_type", currentChessGame.gameType);
            eventData.addProperty("result", result);
            eventData.addProperty("opponent", opponent);
            eventData.addProperty("move_count", currentMoveCount);
            if ("gomoku".equals(currentChessGame.gameType)) {
                eventData.addProperty("maid_skill", maid.getGameRecordManager().getGomokuWinCount());
            }
            addBoardData(eventData, boardEntity);
            webSocketServer.broadcastEvent(eventData);

            // Mark this board as ended to prevent re-triggering until reset
            endedBoardPos = boardPos;
            currentChessGame = null;
            return;
        }

        // Check for mid-game commentary trigger
        if (!currentChessGame.gameEndNotified
                && currentMoveCount > currentChessGame.lastMoveCount
                && currentMoveCount >= currentChessGame.nextCommentaryAt) {

            LOGGER.info("[Chess] Mid-game commentary: type={}, move={}, maidTurn={}, nextAt={}",
                    currentChessGame.gameType, currentMoveCount, !currentPlayerTurn,
                    currentMoveCount + 3 + (int)(Math.random() * 6));

            JsonObject eventData = new JsonObject();
            eventData.addProperty("event_type", Protocol.EVENT_CHESS_MID_GAME);
            eventData.addProperty("maid_id", maid.getStringUUID());
            eventData.addProperty("maid_name", maid.getName().getString());
            eventData.addProperty("game_type", currentChessGame.gameType);
            eventData.addProperty("is_maid_turn", !currentPlayerTurn);
            eventData.addProperty("move_count", currentMoveCount);
            if ("gomoku".equals(currentChessGame.gameType)) {
                eventData.addProperty("maid_skill", maid.getGameRecordManager().getGomokuWinCount());
            }
            addBoardData(eventData, boardEntity);
            webSocketServer.broadcastEvent(eventData);

            // Schedule next commentary
            currentChessGame.nextCommentaryAt = currentMoveCount + 3 + (int)(Math.random() * 6);
        }

        // Update tracked state
        currentChessGame.lastMoveCount = currentMoveCount;
        currentChessGame.lastPlayerTurn = currentPlayerTurn;
    }

    private static TileEntityJoy findNearbyChessBoard(EntityMaid maid) {
        BlockPos maidPos = maid.blockPosition();
        for (int dx = -CHESS_SEARCH_RANGE; dx <= CHESS_SEARCH_RANGE; dx++) {
            for (int dy = -CHESS_SEARCH_RANGE; dy <= CHESS_SEARCH_RANGE; dy++) {
                for (int dz = -CHESS_SEARCH_RANGE; dz <= CHESS_SEARCH_RANGE; dz++) {
                    BlockPos checkPos = maidPos.offset(dx, dy, dz);
                    BlockEntity be = maid.level().getBlockEntity(checkPos);
                    if (be instanceof TileEntityGomoku || be instanceof TileEntityWChess || be instanceof TileEntityCChess) {
                        return (TileEntityJoy) be;
                    }
                }
            }
        }
        return null;
    }

    private static String getGameType(TileEntityJoy board) {
        if (board instanceof TileEntityGomoku) return "gomoku";
        if (board instanceof TileEntityWChess) return "wchess";
        if (board instanceof TileEntityCChess) return "cchess";
        return "unknown";
    }

    private static int getMoveCount(TileEntityJoy board) {
        if (board instanceof TileEntityGomoku gomoku) return gomoku.getChessCounter();
        if (board instanceof TileEntityWChess wchess) return wchess.getChessCounter();
        if (board instanceof TileEntityCChess cchess) return cchess.getChessCounter();
        return 0;
    }

    private static boolean isPlayerTurn(TileEntityJoy board) {
        if (board instanceof TileEntityGomoku gomoku) return gomoku.isPlayerTurn();
        if (board instanceof TileEntityWChess wchess) return wchess.isPlayerTurn();
        if (board instanceof TileEntityCChess cchess) return cchess.isPlayerTurn();
        return true;
    }

    private static boolean isGameEnded(TileEntityJoy board) {
        if (board instanceof TileEntityGomoku gomoku) {
            return gomoku.getStatue() != Statue.IN_PROGRESS;
        }
        if (board instanceof TileEntityWChess wchess) {
            return wchess.isCheckmate() || wchess.isRepeat() || wchess.isMoveNumberLimit();
        }
        if (board instanceof TileEntityCChess cchess) {
            return cchess.isCheckmate() || cchess.isRepeat() || cchess.isMoveNumberLimit();
        }
        return false;
    }

    private static String getGameResult(TileEntityJoy board, EntityMaid maid) {
        if (board instanceof TileEntityGomoku gomoku) {
            Statue statue = gomoku.getStatue();
            if (statue == Statue.DRAW) return "draw";
            // In gomoku, if maid's game record shows WIN, maid won; otherwise lost
            return maid.getGameRecordManager().isWin() ? "win" : "lose";
        }
        if (board instanceof TileEntityWChess wchess) {
            if (wchess.isRepeat() || wchess.isMoveNumberLimit()) return "draw";
            return maid.getGameRecordManager().isWin() ? "win" : "lose";
        }
        if (board instanceof TileEntityCChess cchess) {
            if (cchess.isRepeat() || cchess.isMoveNumberLimit()) return "draw";
            return maid.getGameRecordManager().isWin() ? "win" : "lose";
        }
        return "unknown";
    }

    private static String findNearbyPlayerName(TileEntityJoy board, net.minecraft.server.MinecraftServer server) {
        BlockPos boardPos = board.getWorldPosition();
        for (net.minecraft.server.level.ServerLevel level : server.getAllLevels()) {
            for (Player player : level.players()) {
                if (player.blockPosition().distManhattan(boardPos) <= 4) {
                    return player.getName().getString();
                }
            }
        }
        return "";
    }

    private static void addBoardData(JsonObject eventData, TileEntityJoy board) {
        if (board instanceof TileEntityGomoku gomoku) {
            StringBuilder sb = new StringBuilder(225);
            byte[][] data = gomoku.getChessData();
            for (int x = 0; x < 15; x++) {
                for (int y = 0; y < 15; y++) {
                    sb.append(data[x][y]);
                }
            }
            eventData.addProperty("board", sb.toString());
        } else if (board instanceof TileEntityWChess wchess) {
            eventData.addProperty("fen", wchess.getChessData().toFen());
        } else if (board instanceof TileEntityCChess cchess) {
            eventData.addProperty("fen", cchess.getChessData().toFen());
        }
    }
}
