package com.neko_tlm_bridge.ws.handler;

import com.github.tartaricacid.touhoulittlemaid.entity.passive.EntityMaid;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;

import java.util.List;
import java.util.UUID;

/** 女仆查找工具类 — 提供 findMaidById 和 findFirstMaid 等共享的静态方法 */
public final class MaidHelper {
    private MaidHelper() {}

    public static EntityMaid findMaidById(MinecraftServer server, String maidId) {
        try {
            UUID uuid = UUID.fromString(maidId);
            for (ServerLevel level : server.getAllLevels()) {
                Entity entity = level.getEntity(uuid);
                if (entity instanceof EntityMaid maid) {
                    return maid;
                }
            }
        } catch (IllegalArgumentException e) {
            for (ServerLevel level : server.getAllLevels()) {
                for (EntityMaid maid : level.getEntitiesOfClass(EntityMaid.class, new AABB(level.getWorldBorder().getMinX(), level.getMinBuildHeight(), level.getWorldBorder().getMinZ(), level.getWorldBorder().getMaxX(), level.getMaxBuildHeight(), level.getWorldBorder().getMaxZ()))) {
                    if (maid.getStringUUID().equals(maidId)) {
                        return maid;
                    }
                }
            }
        }
        return null;
    }

    public static EntityMaid findFirstMaid(MinecraftServer server) {
        for (ServerLevel level : server.getAllLevels()) {
            List<EntityMaid> maids = level.getEntitiesOfClass(EntityMaid.class,
                    new AABB(level.getWorldBorder().getMinX(), level.getMinBuildHeight(), level.getWorldBorder().getMinZ(),
                            level.getWorldBorder().getMaxX(), level.getMaxBuildHeight(), level.getWorldBorder().getMaxZ()));
            if (!maids.isEmpty()) {
                return maids.get(0);
            }
        }
        return null;
    }
}
