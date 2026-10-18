import { describe, expect, it } from "vitest"

import type { StrengthExercise } from "@/api/types"
import { loadText, prescription, range } from "@/lib/strength"

const ex = (o: Partial<StrengthExercise>): StrengthExercise => ({
  id: "x", name: "X", pattern: "squat", cue: "c", per_side: false, sets: [1, 3], reps: [8, 12], hold_s: null, rpe: [4, 6], effort: "e", rest: "r", ...o,
})

describe("strength lib", () => {
  it("formats ranges", () => {
    expect(range([2, 2])).toBe("2")
    expect(range([1, 3])).toBe("1-3")
    expect(range(undefined)).toBe("")
  })
  it("describes reps and holds", () => {
    expect(prescription(ex({}))).toBe("1-3 sets of 8-12 repetitions")
    expect(prescription(ex({ per_side: true, sets: [2, 2], reps: [6, 8] }))).toBe("2 sets of 6-8 repetitions each side")
    expect(prescription(ex({ hold_s: 30, reps: null, sets: [2, 2], per_side: true }))).toBe("2 holds of 30 s each side")
  })
  it("keeps the unit text with the load", () => {
    expect(loadText([180.4, 270], "arbitrary units (session-RPE), not comparable with TSS")).toBe(
      "180-270 arbitrary units (session-RPE), not comparable with TSS",
    )
  })
})
