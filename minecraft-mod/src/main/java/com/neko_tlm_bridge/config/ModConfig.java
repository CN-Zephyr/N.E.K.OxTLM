package com.neko_tlm_bridge.config;

import net.neoforged.neoforge.common.ModConfigSpec;
import net.neoforged.neoforge.common.ModConfigSpec.Builder;

public class ModConfig {
    public static final ModConfigSpec SPEC;

    public static final ModConfigSpec.IntValue WEBSOCKET_PORT;
    public static final ModConfigSpec.BooleanValue NEKO_MODE_ENABLED;

    public static final ModConfigSpec.BooleanValue EVENT_PUSH_ENABLED;
    public static final ModConfigSpec.BooleanValue COMMAND_EXECUTION_ENABLED;
    public static final ModConfigSpec.BooleanValue CHAT_BUBBLE_ENABLED;
    public static final ModConfigSpec.BooleanValue CHAT_BOX_ENABLED;
    public static final ModConfigSpec.BooleanValue WEATHER_EVENT_ENABLED;
    public static final ModConfigSpec.BooleanValue TIME_EVENT_ENABLED;

    static {
        Builder builder = new Builder();

        builder.push("websocket");
        WEBSOCKET_PORT = builder
                .translation("neko_tlm_bridge.config.websocket.port")
                .defineInRange("port", 48920, 1024, 65535);
        builder.pop();

        builder.push("bridge");
        NEKO_MODE_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.nekoModeEnabled")
                .define("nekoModeEnabled", true);
        EVENT_PUSH_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.eventPushEnabled")
                .define("eventPushEnabled", true);
        COMMAND_EXECUTION_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.commandExecutionEnabled")
                .define("commandExecutionEnabled", false);
        CHAT_BUBBLE_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.chatBubbleEnabled")
                .define("chatBubbleEnabled", true);
        CHAT_BOX_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.chatBoxEnabled")
                .define("chatBoxEnabled", true);
        WEATHER_EVENT_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.weatherEventEnabled")
                .define("weatherEventEnabled", true);
        TIME_EVENT_ENABLED = builder
                .translation("neko_tlm_bridge.config.bridge.timeEventEnabled")
                .define("timeEventEnabled", true);
        builder.pop();

        SPEC = builder.build();
    }
}
