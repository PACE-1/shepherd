import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AiCoachSettings, AskCoach, CoachInsight } from "@/screens/Coach"

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })
const NONE = { configured: false, provider: "", base_url: "", model: "", has_key: false }

function mock(routes: Record<string, (body: unknown) => Response>) {
  const calls: { url: string; method?: string; body: unknown }[] = []
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, method: init?.method, body })
    return (routes[url] ?? (() => json({}, 404)))(body)
  }))
  return calls
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("AI coach settings", () => {
  it("fills a preset, saves it with the key, and clears the key field", async () => {
    let saved = false
    const calls = mock({ "/api/llm": (b) => { saved = saved || !!b; return saved ? json({ configured: true, provider: "anthropic", base_url: "https://api.anthropic.com", model: "claude-sonnet-5-5", has_key: true }) : json(NONE) } })
    render(<AiCoachSettings />)
    await userEvent.click(await screen.findByRole("button", { name: "Anthropic" }))
    await userEvent.type(screen.getByLabelText("Provider API key"), "sk-abc")
    await userEvent.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText(/Connected to Anthropic: claude-sonnet-5-5/)).toBeTruthy()
    const post = calls.find((c) => c.method === "POST")
    expect(post?.body).toEqual({ provider: "anthropic", base_url: "https://api.anthropic.com", model: "claude-sonnet-5-5", api_key: "sk-abc" })
    expect((screen.getByLabelText("Provider API key") as HTMLInputElement).value).toBe("")
  })

  it("shows the provider's refusal when the test fails, and never shows a stored key", async () => {
    mock({
      "/api/llm": () => json({ configured: true, provider: "openai", base_url: "http://localhost:11434/v1", model: "llama3.1", has_key: true }),
      "/api/llm/test": () => json({ detail: "The provider rejected the API key." }, 502),
    })
    render(<AiCoachSettings />)
    expect((await screen.findByLabelText("Provider API key") as HTMLInputElement).value).toBe("")
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }))
    expect((await screen.findByRole("alert")).textContent).toContain("The provider rejected the API key.")
  })

  it("disconnects", async () => {
    const calls = mock({ "/api/llm": () => json({ configured: true, provider: "openai", base_url: "http://x/v1", model: "m", has_key: false }) })
    render(<AiCoachSettings />)
    await userEvent.click(await screen.findByRole("button", { name: "Disconnect" }))
    expect(calls.some((c) => c.method === "DELETE")).toBe(true)
  })
})

describe("insights", () => {
  it("shows the reply, and points to Settings when no provider is connected", async () => {
    const run = vi.fn().mockResolvedValueOnce({ text: "Keep it easy.", model: "m" }).mockRejectedValueOnce(new Error("No AI provider is connected. Add one in Settings."))
    render(<CoachInsight label="Review this ride" run={run} />)
    await userEvent.click(screen.getByRole("button", { name: "Review this ride" }))
    expect((await screen.findByLabelText("Coach reply")).textContent).toBe("Keep it easy.")
    await userEvent.click(screen.getByRole("button", { name: "Review this ride" }))
    expect((await screen.findByRole("alert")).textContent).toContain("No AI provider")
    expect(screen.getByRole("link", { name: "Open Settings" }).getAttribute("href")).toBe("#/settings")
    expect(screen.queryByLabelText("Coach reply")).toBeNull()
  })

  it("asks a question with the earlier turns as history, and clears", async () => {
    const calls = mock({ "/api/insights/ask": () => json({ text: "Yes, go.", model: "m" }) })
    render(<AskCoach />)
    await userEvent.type(screen.getByLabelText("Your question"), "Am I ready?")
    await userEvent.click(screen.getByRole("button", { name: "Ask" }))
    expect(await screen.findByText("Yes, go.")).toBeTruthy()
    await userEvent.type(screen.getByLabelText("Your question"), "And tomorrow?{Enter}")
    await screen.findAllByText("Yes, go.")
    expect(calls[1].body).toEqual({ question: "And tomorrow?", history: [{ role: "user", content: "Am I ready?" }, { role: "assistant", content: "Yes, go." }] })
    await userEvent.click(screen.getByRole("button", { name: "Clear" }))
    expect(screen.queryByText("Yes, go.")).toBeNull()
  })
})
