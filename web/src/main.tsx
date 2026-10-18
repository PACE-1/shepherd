import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App.tsx"
import { ThemeProvider } from "@/components/theme-provider.tsx"
import { installErrorReporting } from "@/lib/errorReport.ts"
import { applyStoredPalette } from "@/lib/palette.ts"

installErrorReporting()
applyStoredPalette()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>
)
