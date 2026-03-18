"use client";

type SidebarItem = {
  id: string;
  label: string;
  description: string;
};

const itemGlyphs: Record<string, string> = {
  events: "E",
  tasks: "T",
  scoring: "S",
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
          <div>
            <p className="eyebrow">FlightComp Platform</p>
            {!compact ? <h2>Flight Director</h2> : null}
          </div>
          <button type="button" className="sidebar-toggle" onClick={onToggleCompact} aria-label={compact ? "Expand navigation panel" : "Compact navigation panel"} title={compact ? "Expand navigation panel" : "Compact navigation panel"}>
            {compact ? "»" : "«"}
          </button>
        </div>
        {!compact ? <p className="sidebar-copy">Operations, tasking, and scoring in one workspace.</p> : null}
      </div>
      <nav className="sidebar-nav" aria-label="Primary">
        {items.map((item) => (
          <button key={item.id} type="button" className={item.id === activeItem ? "nav-item active" : "nav-item"} onClick={() => onSelect(item.id)} title={compact ? item.label : undefined}>
            <span className="nav-item-glyph" aria-hidden="true">{itemGlyphs[item.id] ?? item.label.slice(0, 1)}</span>
            {!compact ? (
              <>
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </>
            ) : null}
          </button>
        ))}
      </nav>
      <div className="sidebar-context">
        {!compact ? (
          <>
            <span className="context-label">Selected event</span>
            <strong>{eventName ?? "No event selected"}</strong>
          </>
        ) : (
          <strong title={eventName ?? "No event selected"}>{eventName ? eventName.slice(0, 1).toUpperCase() : "?"}</strong>
        )}
      </div>
    </aside>
  );
}
