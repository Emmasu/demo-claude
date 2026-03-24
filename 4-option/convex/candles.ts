import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const MAX_DAYS_MIN  = 7;    // minute-resolution series
const MAX_DAYS_HOUR = 90;   // hourly-resolution series
const MAX_DAYS_DAY  = 365;  // daily-resolution series

// Returns all stored candle series
export const getAll = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db.query("candle_series").collect();
  },
});

// Appends new candles to a named series, trims to MAX_DAYS
export const append = mutation({
  args: {
    name: v.string(),
    newTicks: v.array(v.number()),
    newCloses: v.array(v.number()),
  },
  handler: async (ctx, { name, newTicks, newCloses }) => {
    const maxDays = name.endsWith('_day') ? MAX_DAYS_DAY : name.endsWith('_hour') ? MAX_DAYS_HOUR : MAX_DAYS_MIN;
    const cutoff = Date.now() - maxDays * 24 * 3600 * 1000;

    const existing = await ctx.db
      .query("candle_series")
      .withIndex("by_name", (q) => q.eq("name", name))
      .first();

    let ticks: number[] = existing ? [...existing.ticks] : [];
    let closes: number[] = existing ? [...existing.closes] : [];

    // Only append candles newer than what's already stored
    const lastTs = ticks[ticks.length - 1] ?? 0;
    for (let i = 0; i < newTicks.length; i++) {
      if (newTicks[i] > lastTs) {
        ticks.push(newTicks[i]);
        closes.push(newCloses[i]);
      }
    }

    // Trim to MAX_DAYS rolling window
    const startIdx = ticks.findIndex((t) => t >= cutoff);
    if (startIdx > 0) {
      ticks = ticks.slice(startIdx);
      closes = closes.slice(startIdx);
    }

    if (existing) {
      await ctx.db.patch(existing._id, { ticks, closes });
    } else {
      await ctx.db.insert("candle_series", { name, ticks, closes });
    }
  },
});
