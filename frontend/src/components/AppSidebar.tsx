"use client";

type SidebarItem = {
  id: string;
  label: string;
  description: string;
};

export function AppSidebar({ items, activeItem, onSelect, eventName }: { items: SidebarItem[]; activeItem: string; onSelect: (id: string) => void; eventName: string | null }) {
  return (
    <aside className="panel nav-sidebar">
      <div className="sidebar-brand">
        <p className="eyebrow">FlightComp Platform</p>
        <h2>Flight Director</h2>
        <p className="sidebar-copy">Operations, tasking, and scoring in one workspace.</p>
      </div>
      <nav className="sidebar-nav" aria-label="Primary">
        {items.map((item) => (
          <button key={item.id} type="button" className={item.id === activeItem ? "nav-item active" : "nav-item"} onClick={() => onSelect(item.id)}>
            <strong>{item.label}</strong>
            <span>{item.description}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-context">
        <span className="context-label">Selected event</span>
        <strong>{eventName ?? "No event selected"}</strong>
      </div>
    </aside>
  );
}
