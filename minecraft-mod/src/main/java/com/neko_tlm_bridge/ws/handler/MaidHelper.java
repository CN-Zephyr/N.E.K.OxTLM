package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

import java.util.UUID;

/** 女仆查找工具类 — 提供 findMaidById 和 findFirstMaid 等共享的静态方法 */
public final class MaidHelper {
    private MaidHelper() {}

    public static EntityMaid findMaidById(MinecraftServer server, String maidId) {
        if (server == null || maidId == null || maidId.isEmpty()) {
            return null;
        }
        try {
            UUID uuid = UUID.fromString(maidId);
            for (ServerLevel level : server.getAllLevels()) {
                Entity entity = level.getEntity(uuid);
                if (entity instanceof EntityMaid maid) {
                    return maid;
                }
            }
        } catch (IllegalArgumentException e) {
        }
        for (EntityMaid maid : getAllMaids(server)) {
            if (maid.getStringUUID().equals(maidId)) {
                return maid;
            }
        }
        return null;
    }

    public static java.util.List<EntityMaid> getAllMaids(MinecraftServer server) {
        java.util.List<EntityMaid> maids = new java.util.ArrayList<>();
        if (server == null) {
            return maids;
        }
        for (ServerLevel level : server.getAllLevels()) {
            for (Entity entity : level.getAllEntities()) {
                if (entity instanceof EntityMaid maid) {
                    maids.add(maid);
                }
            }
        }
        return maids;
    }

    public static EntityMaid findFirstMaid(MinecraftServer server) {
        java.util.List<EntityMaid> maids = getAllMaids(server);
        if (!maids.isEmpty()) {
            return maids.get(0);
        }
        return null;
    }
}
