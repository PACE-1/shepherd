import { BellIcon } from "lucide-react"
import { useCallback, useEffect, useState } from "react"

import type { NotificationList } from "@/api/types"
import { Button } from "@/components/ui/button"
import { badge, getNotifications, markNotificationsRead } from "@/lib/notifications"

const POLL_MS = 60_000

/** The bell in the header: unread count, and the list of notices when opened. Quiet when the server is unreachable. */
export function NotificationsBell() {
  const [list, setList] = useState<NotificationList>({ items: [], unread: 0 })
  const [open, setOpen] = useState(false)
  const refresh = useCallback(() => getNotifications().then(setList, () => {}), [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])
  const text = badge(list.unread)
  return (
    <span className="relative">
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label={list.unread ? `Notifications, ${list.unread} unread` : "Notifications"}
        aria-expanded={open}
        onClick={() => {
          if (!open) refresh()
          setOpen(!open)
        }}
      >
        <BellIcon />
        {text && (
          <span aria-hidden className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-[10px] leading-4 text-primary-foreground">
            {text}
          </span>
        )}
      </Button>
      {open && (
        <div
          role="region"
          aria-label="Notifications list"
          className="absolute right-0 z-50 mt-1 w-80 max-w-[calc(100vw-2rem)] space-y-2 rounded-lg border bg-popover p-3 text-sm text-popover-foreground shadow-md"
        >
          {list.items.length === 0 ? (
            <p className="text-muted-foreground">Nothing yet. Readiness, missed sessions and sync problems show up here.</p>
          ) : (
            <ul className="max-h-80 space-y-2 overflow-y-auto">
              {list.items.map((i) => (
                <li key={i.id} className={i.read ? "text-muted-foreground" : ""}>
                  <p className="font-medium">{i.title}</p>
                  <p>{i.body}</p>
                  <p className="text-xs text-muted-foreground">{i.ts.replace("T", " ").slice(0, 16)}</p>
                </li>
              ))}
            </ul>
          )}
          <div className="flex justify-between gap-2">
            <Button size="sm" variant="outline" disabled={list.unread === 0} onClick={() => markNotificationsRead().then(setList, () => {})}>
              Mark all read
            </Button>
            <Button size="sm" variant="ghost" render={<a href="#/settings" />} onClick={() => setOpen(false)}>
              Settings
            </Button>
          </div>
        </div>
      )}
    </span>
  )
}
