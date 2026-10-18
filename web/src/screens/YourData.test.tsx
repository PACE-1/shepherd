import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it } from "vitest"

import { YourData } from "@/screens/YourData"

afterEach(cleanup)

it("links each export and says the backup has no keys", () => {
  render(<YourData />)
  expect(screen.getByRole("link", { name: "Activities (CSV)" }).getAttribute("href")).toBe("/api/export/activities.csv")
  expect(screen.getByRole("link", { name: "Full backup (.tar.gz)" }).getAttribute("href")).toBe("/api/export/backup")
  expect(screen.getByText(/leaves out your intervals.icu and AI keys/)).toBeTruthy()
})
