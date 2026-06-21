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

        int minOpLevel = ModConfig.COMMAND_CONFIRMATION_MIN_OP_LEVEL.get();
        if (!source.hasPermission(minOpLevel)) {
            // 权限不足时拒绝，避免低权限玩家执行高危指令
            source.sendFailure(Component.literal("权限不足，无法确认指令"));
            return 0;
        }

        PendingCommandManager manager = wsServer.getPendingCommandManager();
        PendingCommandManager.PendingCommand pending = manager.getAndRemove(pendingId);

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
        if (parse.getExceptions().size() > 0 || parse.getContext().getRange().isEmpty()) {
            // 解析错误：发送错误消息给玩家
            CommandSyntaxException exception = null;
            if (parse.getExceptions().size() == 1) {
                exception = parse.getExceptions().values().iterator().next();
            } else if (parse.getContext().getRange().isEmpty()) {
                exception = CommandSyntaxException.BUILT_IN_EXCEPTIONS.dispatcherUnknownCommand().create();
            }
            if (exception != null) {
                source.sendFailure(Component.literal(exception.getMessage()));
            }
        } else {
            try {
                result = commands.getDispatcher().execute(parse);
            } catch (CommandSyntaxException e) {
                source.sendFailure(Component.literal(e.getMessage()));
            } catch (Exception e) {
                source.sendFailure(Component.literal("命令执行出错: " + e.getMessage()));
            }
        }

        source.sendSuccess(() -> Component.translatable("neko_tlm_bridge.command.executed", command), true);

        if (pending.conn != null && pending.conn.isOpen()) {
            JsonObject response = new JsonObject();
            response.addProperty("type", Protocol.TYPE_COMMAND_EXECUTION_RESULT);
            if (pending.originalRequestId != null) {
                response.addProperty("request_id", pending.originalRequestId);
            }
            JsonObject data = new JsonObject();
            data.addProperty("approved", true);
            data.addProperty("success", result > 0);
            data.addProperty("command", command);
            data.addProperty("approved_by", source.getTextName());
            response.add("data", data);
            pending.conn.send(GSON.toJson(response));
        }

        LOGGER.info("Player {} accepted command: {} (pending_id={})", source.getTextName(), command, pendingId);
        return 1;
    }

    private static int rejectCommand(CommandSourceStack source, String pendingId) {
        NekoWebSocketServer wsServer = NekoWebSocketServerHolder.getServer();
        if (wsServer == null) {
            source.sendFailure(Component.literal("N.E.K.O bridge is not running"));
            return 0;
        }

        PendingCommandManager manager = wsServer.getPendingCommandManager();
        PendingCommandManager.PendingCommand pending = manager.getAndRemove(pendingId);

        if (pending == null) {
            source.sendFailure(Component.translatable("neko_tlm_bridge.command.not_found", pendingId));
            return 0;
        }

        source.sendSuccess(() -> Component.translatable("neko_tlm_bridge.command.rejected", pending.command), true);

        if (pending.conn != null && pending.conn.isOpen()) {
            JsonObject response = new JsonObject();
            response.addProperty("type", Protocol.TYPE_COMMAND_EXECUTION_RESULT);
            if (pending.originalRequestId != null) {
                response.addProperty("request_id", pending.originalRequestId);
            }
            JsonObject data = new JsonObject();
            data.addProperty("approved", false);
            data.addProperty("command", pending.command);
            data.addProperty("rejected_by", source.getTextName());
            response.add("data", data);
            pending.conn.send(GSON.toJson(response));
        }

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

    public static void broadcastCommandRequest(MinecraftServer server, String pendingId, String command) {
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

        server.getPlayerList().broadcastSystemMessage(message, false);
    }
}
