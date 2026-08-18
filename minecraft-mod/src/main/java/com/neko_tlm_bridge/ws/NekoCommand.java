package com.neko_tlm_bridge.ws;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.ParseResults;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.neko_tlm_bridge.config.ModConfig;
import com.neko_tlm_bridge.tlm.NekoWebSocketServerHolder;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Style;
import net.minecraft.ChatFormatting;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class NekoCommand {
    private static final Logger LOGGER = LoggerFactory.getLogger("NekoTlmBridge");
    private static final Gson GSON = new Gson();

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("neko")
                .then(Commands.literal("accept")
                        .then(Commands.argument("pending_id", StringArgumentType.word())
                                .executes(ctx -> acceptCommand(
                                        ctx.getSource(),
                                        StringArgumentType.getString(ctx, "pending_id")
                                ))))
                .then(Commands.literal("reject")
                        .then(Commands.argument("pending_id", StringArgumentType.word())
                                .executes(ctx -> rejectCommand(
                                        ctx.getSource(),
                                        StringArgumentType.getString(ctx, "pending_id")
                                ))))
                .then(Commands.literal("plan")
                        .then(Commands.literal("clear")
                                .executes(ctx -> clearPlanCommand(ctx.getSource())))
                        .then(Commands.argument("text", StringArgumentType.greedyString())
                                .executes(ctx -> setPlanCommand(
                                        ctx.getSource(),
                                        StringArgumentType.getString(ctx, "text")
                                ))))
        );
    }

    private static int acceptCommand(CommandSourceStack source, String pendingId) {
        NekoWebSocketServer wsServer = NekoWebSocketServerHolder.getServer();
        if (wsServer == null) {
            source.sendFailure(Component.literal("N.E.K.O bridge is not running"));
            return 0;
        }

        PendingCommandManager manager = wsServer.getPendingCommandManager();
        PendingCommandManager.PendingCommand pending = manager.get(pendingId);
        if (pending == null) {
            source.sendFailure(Component.translatable("neko_tlm_bridge.command.not_found", pendingId));
            return 0;
        }

        if (!(source.getEntity() instanceof ServerPlayer player)
                || pending.targetPlayerUuid == null
                || !pending.targetPlayerUuid.equals(player.getUUID())) {
            source.sendFailure(Component.literal("此指令确认仅限发起请求的客户端玩家"));
            return 0;
        }

        if (!ModConfig.COMMAND_EXECUTION_ENABLED.get()) {
            manager.cancel(pendingId, "Command execution was disabled in Minecraft mod config");
            source.sendFailure(Component.literal("指令执行已被关闭，待确认指令已取消"));
            return 0;
        }

        int minOpLevel = ModConfig.COMMAND_CONFIRMATION_MIN_OP_LEVEL.get();
        if (!source.hasPermission(minOpLevel)) {
            // 权限不足时拒绝，避免低权限玩家执行高危指令
            source.sendFailure(Component.literal("权限不足，无法确认指令"));
            return 0;
        }

        pending = manager.getAndRemove(pendingId);
        if (pending == null) {
            source.sendFailure(Component.translatable("neko_tlm_bridge.command.not_found", pendingId));
            return 0;
        }

        String command = pending.command;
        MinecraftServer server = source.getServer();

        // 用 CommandDispatcher.execute 获取返回值，同时保证玩家能看到命令输出和报错
        String trimmedCommand = command.startsWith("/") ? command.substring(1) : command;
        Commands commands = server.getCommands();
        ParseResults<CommandSourceStack> parse = commands.getDispatcher().parse(trimmedCommand, source);
        int result = 0;
        boolean success = false;
        String errorMessage = null;
        if (parse.getExceptions().size() > 0 || parse.getContext().getRange().isEmpty()) {
            // 解析错误：发送错误消息给玩家
            CommandSyntaxException exception = null;
            if (parse.getExceptions().size() == 1) {
                exception = parse.getExceptions().values().iterator().next();
            } else if (parse.getContext().getRange().isEmpty()) {
                exception = CommandSyntaxException.BUILT_IN_EXCEPTIONS.dispatcherUnknownCommand().create();
            }
            if (exception != null) {
                errorMessage = exception.getMessage();
                source.sendFailure(Component.literal(errorMessage));
            }
        } else {
            try {
                result = commands.getDispatcher().execute(parse);
                success = result > 0;
                if (!success) {
                    errorMessage = "命令未执行（返回值为 0）";
                    source.sendFailure(Component.literal(errorMessage));
                }
            } catch (CommandSyntaxException e) {
                errorMessage = e.getMessage();
                source.sendFailure(Component.literal(errorMessage));
            } catch (Exception e) {
                errorMessage = "命令执行出错: " + e.getMessage();
                source.sendFailure(Component.literal(errorMessage));
            }
        }

        if (success) {
            source.sendSuccess(() -> Component.translatable("neko_tlm_bridge.command.executed", command), false);
        }
        sendCommandResult(pending, true, success, source.getTextName(), errorMessage);

        LOGGER.info("Player {} accepted command: {} (pending_id={}, success={})",
                source.getTextName(), command, pendingId, success);
        return success ? 1 : 0;
    }

    private static int rejectCommand(CommandSourceStack source, String pendingId) {
        NekoWebSocketServer wsServer = NekoWebSocketServerHolder.getServer();
        if (wsServer == null) {
            source.sendFailure(Component.literal("N.E.K.O bridge is not running"));
            return 0;
        }

        PendingCommandManager manager = wsServer.getPendingCommandManager();
        PendingCommandManager.PendingCommand pending = manager.get(pendingId);

        if (pending == null) {
            source.sendFailure(Component.translatable("neko_tlm_bridge.command.not_found", pendingId));
            return 0;
        }

        if (!(source.getEntity() instanceof ServerPlayer player)
                || pending.targetPlayerUuid == null
                || !pending.targetPlayerUuid.equals(player.getUUID())) {
            source.sendFailure(Component.literal("此指令确认仅限发起请求的客户端玩家"));
            return 0;
        }

        pending = manager.getAndRemove(pendingId);
        if (pending == null) {
            source.sendFailure(Component.translatable("neko_tlm_bridge.command.not_found", pendingId));
            return 0;
        }

        String rejectedCommand = pending.command;
        source.sendSuccess(() -> Component.translatable("neko_tlm_bridge.command.rejected", rejectedCommand), false);
        sendCommandResult(pending, false, false, source.getTextName(), null);

        LOGGER.info("Player {} rejected command: {} (pending_id={})", source.getTextName(), pending.command, pendingId);
        return 0;
    }

    private static int setPlanCommand(CommandSourceStack source, String text) {
        com.neko_tlm_bridge.client.PlanOverlayRenderer.setPlan(text);
        source.sendSuccess(() -> Component.literal("Plan set: " + text), true);

        NekoWebSocketServer wsServer = NekoWebSocketServerHolder.getServer();
        if (wsServer != null) {
            wsServer.broadcastPlanUpdate(text);
        }
        return 1;
    }

    private static int clearPlanCommand(CommandSourceStack source) {
        com.neko_tlm_bridge.client.PlanOverlayRenderer.clearPlan();
        source.sendSuccess(() -> Component.literal("Plan cleared"), true);

        NekoWebSocketServer wsServer = NekoWebSocketServerHolder.getServer();
        if (wsServer != null) {
            wsServer.broadcastPlanUpdate("");
        }
        return 1;
    }

    public static void sendCommandRequest(ServerPlayer player, String pendingId, String command) {
        Component header = Component.translatable("neko_tlm_bridge.command.request_header")
                .withStyle(ChatFormatting.GOLD, ChatFormatting.BOLD);

        Component cmdDisplay = Component.literal(command)
                .withStyle(ChatFormatting.YELLOW);

        Component acceptBtn = Component.translatable("neko_tlm_bridge.command.accept")
                .withStyle(Style.EMPTY
                        .withClickEvent(new ClickEvent(ClickEvent.Action.RUN_COMMAND, "/neko accept " + pendingId))
                        .withColor(ChatFormatting.GREEN)
                        .withBold(true));

        Component separator = Component.literal("  ");

        Component rejectBtn = Component.translatable("neko_tlm_bridge.command.reject")
                .withStyle(Style.EMPTY
                        .withClickEvent(new ClickEvent(ClickEvent.Action.RUN_COMMAND, "/neko reject " + pendingId))
                        .withColor(ChatFormatting.RED)
                        .withBold(true));

        Component message = Component.empty()
                .append(header)
                .append(" ")
                .append(cmdDisplay)
                .append("  ")
                .append(acceptBtn)
                .append(separator)
                .append(rejectBtn);

        player.sendSystemMessage(message);
    }

    private static void sendCommandResult(PendingCommandManager.PendingCommand pending,
                                           boolean approved, boolean success,
                                           String actor, String errorMessage) {
        if (pending.conn == null || !pending.conn.isOpen()) {
            return;
        }
        JsonObject response = new JsonObject();
        response.addProperty("type", Protocol.TYPE_COMMAND_EXECUTION_RESULT);
        if (pending.originalRequestId != null) {
            response.addProperty("request_id", pending.originalRequestId);
        }
        JsonObject data = new JsonObject();
        data.addProperty("approved", approved);
        data.addProperty("success", success);
        data.addProperty("command", pending.command);
        if (approved) {
            data.addProperty("approved_by", actor);
        } else if (actor != null && !actor.isBlank()) {
            data.addProperty("rejected_by", actor);
        }
        if (errorMessage != null && !errorMessage.isBlank()) {
            data.addProperty("error", errorMessage);
        }
        response.add("data", data);
        try {
            pending.conn.send(GSON.toJson(response));
        } catch (Exception e) {
            LOGGER.debug("Failed to send command execution result: {}", e.getMessage());
        }
    }
}
