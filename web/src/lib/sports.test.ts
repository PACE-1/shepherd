import { describe, expect, it } from "vitest"

import { averagePace, sportKind } from "@/lib/sports"

describe("sportKind", () => {
  it("matches the server's mapping, and treats a missing type as a ride", () => {
    expect(["Ride", "GravelRide", "VirtualRun", "TrailRun", "OpenWaterSwim", "WeightTraining", null, undefined].map(sportKind)).toEqual([
      "cycling", "cycling", "running", "running", "swimming", "other", "cycling", "cycling"])
  })
})

describe("averagePace", () => {
  it("is seconds per km for a run and per 100 m for a swim, null without a distance", () => {
    expect(averagePace("running", 3000, 10)).toBe(300)
    expect(averagePace("swimming", 2000, 2)).toBe(100)
    expect(averagePace("running", 3000, 0)).toBeNull()
    expect(averagePace("running", null, 10)).toBeNull()
  })
})
