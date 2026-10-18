import type { NotificationList, NotificationSettings, NotificationTest } from "@/api/types"
import { api } from "@/lib/api"

export type EventKey = "readiness" | "missed" | "sync_failure"

export const getNotifications = () => api<NotificationList>("/api/notifications")
export const markNotificationsRead = () => api<NotificationList>("/api/notifications/read", { method: "POST" })
export const getNotificationSettings = () => api<NotificationSettings>("/api/notifications/settings")
export const testNotification = () => api<NotificationTest>("/api/notifications/test", { method: "POST" })

/** `ntfy_url` is write-only: omit it to keep the saved address, send "" to remove it. */
export interface NotificationChange {
  ntfy_url?: string
  events?: Partial<Record<EventKey, boolean>>
  readiness_time?: string
}
export const saveNotificationSettings = (change: NotificationChange) =>
  api<NotificationSettings>("/api/notifications/settings", { method: "PUT", json: change })

export const EVENTS: { key: EventKey; label: string; hint: string }[] = [
  { key: "readiness", label: "Daily readiness", hint: "Today's readiness score and planned session, once a day." },
  { key: "missed", label: "Missed session", hint: "Yesterday's planned session had no activity." },
  { key: "sync_failure", label: "Sync failure", hint: "The intervals.icu sync is failing. Sent once until it recovers." },
]

/** "07:30" -> true; "" (first sync of the day) -> true; anything else -> false. */
export const validTime = (t: string) => t === "" || /^([01]\d|2[0-3]):[0-5]\d$/.test(t)

/** Badge text: nothing for zero, "9+" past nine. */
export const badge = (unread: number) => (unread <= 0 ? "" : unread > 9 ? "9+" : String(unread))
