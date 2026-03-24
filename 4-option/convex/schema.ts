import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  candle_series: defineTable({
    name: v.string(),       // "btc_min" | "call_min" | "put_min"
    ticks: v.array(v.number()),
    closes: v.array(v.number()),
  }).index("by_name", ["name"]),
});
