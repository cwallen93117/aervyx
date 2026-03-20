"use client";

type SidebarItem = {
  id: string;
  label: string;
  description?: string;
};

function SidebarIcon({ id }: { id: string }) {
  switch (id) {
    case "events":
      return (
        <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
          <rect x="4" y="5" width="16" height="15" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path d="M8 3.8v3.4M16 3.8v3.4M4 9.2h16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M8 13h3M13 13h3M8 16.5h3M13 16.5h3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    case "tasks":
      return (
        <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
          <path d="M6 18.5c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2Zm8-13c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2Zm-7 6.5c0-1.1.9-2 2-2s2 .9 2 2-.9 2-2 2-2-.9-2-2Zm3.2-1.1 4.4-4.3M10.4 13.1l3.3 4.2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "scoring":
      return (
        <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
          <path d="M5 19.5h14M7.5 17V11M12 17V7.5M16.5 17v-4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
    case "live_tracking":
      return (
        <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
          <path d="M12 20.5s6-5.6 6-10a6 6 0 1 0-12 0c0 4.4 6 10 6 10Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          <circle cx="12" cy="10.5" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      );
    case "drivers":
      return (
        <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
          <path d="M6 8.5h12l1.5 4v5h-2.5v-1.8h-10V17.5H4.5v-5l1.5-4Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          <circle cx="8" cy="17.5" r="1.4" fill="currentColor" />
          <circle cx="16" cy="17.5" r="1.4" fill="currentColor" />
        </svg>
      );
    case "settings":
      return (
        <svg viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
          <path d="M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Zm0-4.2 1 .2.8 2.1a7.4 7.4 0 0 1 1.4.6l2-1 1.4 1.4-1 2c.2.5.4.9.5 1.4l2.2.8.1 1-.1 1-2.2.8a7.3 7.3 0 0 1-.5 1.4l1 2-1.4 1.4-2-1a7.4 7.4 0 0 1-1.4.6l-.8 2.1-1 .2-1-.2-.8-2.1a7.4 7.4 0 0 1-1.4-.6l-2 1-1.4-1.4 1-2a7.4 7.4 0 0 1-.6-1.4L2.2 13l-.2-1 .2-1 2.1-.8c.1-.5.3-.9.6-1.4l-1-2L5.3 5l2 1a7.4 7.4 0 0 1 1.4-.6l.8-2.1 1-.2Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      );
    default:
      return <span>{id.slice(0, 1).toUpperCase()}</span>;
  }
}

const itemThemes: Record<string, string> = {
  events: "theme-events",
  tasks: "theme-tasks",
  scoring: "theme-scoring",
  live_tracking: "theme-live-tracking",
  drivers: "theme-drivers",
  settings: "theme-settings",
};

export function AppSidebar({
  items,
  activeItem,
  onSelect,
  eventName,
  compact,
  onToggleCompact,
}: {
  items: SidebarItem[];
  activeItem: string;
  onSelect: (id: string) => void;
  eventName: string | null;
  compact: boolean;
  onToggleCompact: () => void;
}) {
  return (
    <aside className={compact ? "panel nav-sidebar compact-mode" : "panel nav-sidebar"}>
      <div className="sidebar-brand">
        <div className="sidebar-brand-row">
          {!compact ? (
            <div>
              <span className="context-label">Selected event</span>
              <p className="eyebrow">{eventName ?? "No event selected"}</p>
            </div>
          ) : null}
          <button
            type="button"
            className="sidebar-toggle"
            onClick={onToggleCompact}
            aria-label={compact ? "Expand navigation panel" : "Compact navigation panel"}
            title={compact ? "Expand navigation panel" : "Compact navigation panel"}
          >
            {compact ? ">" : "<"}
          </button>
        </div>
      </div>
      <nav className="sidebar-nav" aria-label="Primary">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === activeItem ? `nav-item active ${itemThemes[item.id] ?? ""}` : `nav-item ${itemThemes[item.id] ?? ""}`}
            onClick={() => onSelect(item.id)}
            title={compact ? item.label : undefined}
          >
            <div className="nav-item-main">
              <span className="nav-item-glyph" aria-hidden="true">
                <SidebarIcon id={item.id} />
              </span>
              {!compact ? (
                <div className="nav-item-copy">
                  <strong>{item.label}</strong>
                </div>
              ) : null}
            </div>
          </button>
        ))}
      </nav>
    </aside>
  );
}
