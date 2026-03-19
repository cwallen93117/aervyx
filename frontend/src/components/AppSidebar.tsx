"use client";

type SidebarItem = {
  id: string;
  label: string;
  description: string;
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
    default:
      return <span>{id.slice(0, 1).toUpperCase()}</span>;
  }
}

const itemThemes: Record<string, string> = {
  events: "theme-events",
  tasks: "theme-tasks",
  scoring: "theme-scoring",
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
              <p className="eyebrow">FlightComp Platform</p>
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
      {!compact ? (
        <div className="sidebar-context">
          <span className="context-label">Selected event</span>
          <strong>{eventName ?? "No event selected"}</strong>
        </div>
      ) : null}
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
                  <span>{item.description}</span>
                </div>
              ) : null}
            </div>
          </button>
        ))}
      </nav>
    </aside>
  );
}
