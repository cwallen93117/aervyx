"use client";

import type { ReactNode } from "react";

export function SectionCard({ title, description, children, actions }: { title: string; description?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="panel section-card">
      <div className="section-card-header">
        <div>
          <h3>{title}</h3>
          {description ? <p className="hint">{description}</p> : null}
        </div>
        {actions ? <div className="section-card-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
