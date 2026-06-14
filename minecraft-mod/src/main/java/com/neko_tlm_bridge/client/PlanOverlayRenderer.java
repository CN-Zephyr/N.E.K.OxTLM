package com.neko_tlm_bridge.client;

import net.minecraft.client.DeltaTracker;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.LayeredDraw;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.neoforge.client.event.RegisterGuiLayersEvent;
import net.neoforged.neoforge.client.gui.VanillaGuiLayers;

public class PlanOverlayRenderer {
    private static String planText = "";

    public static void setPlan(String text) {
        planText = text != null ? text : "";
    }

    public static String getPlan() {
        return planText;
    }

    public static void clearPlan() {
        planText = "";
    }

    public static void onRegisterGuiLayers(RegisterGuiLayersEvent event) {
        event.registerAbove(VanillaGuiLayers.HOTBAR,
                ResourceLocation.fromNamespaceAndPath("neko_tlm_bridge", "plan_overlay"),
                PlanOverlayRenderer::renderOverlay);
    }

    private static void renderOverlay(GuiGraphics graphics, DeltaTracker deltaTracker) {
        if (planText.isEmpty()) return;

        net.minecraft.client.gui.Font font = net.minecraft.client.Minecraft.getInstance().font;
        String[] lines = planText.split("\n");
        int lineHeight = 10;
        int padding = 4;
        int screenWidth = graphics.guiWidth();

        int maxWidth = 0;
        for (String line : lines) {
            int w = font.width(line);
            if (w > maxWidth) maxWidth = w;
        }

        int boxWidth = maxWidth + padding * 2;
        int boxHeight = lines.length * lineHeight + padding * 2 - 2;
        int x = screenWidth - boxWidth - 5;
        int y = 5;

        // Semi-transparent background
        graphics.fill(x, y, x + boxWidth, y + boxHeight, 0x80000000);

        // Plan text lines
        for (int i = 0; i < lines.length; i++) {
            graphics.drawString(font, lines[i], x + padding, y + padding + i * lineHeight, 0xFFFFFF, true);
        }
    }
}
