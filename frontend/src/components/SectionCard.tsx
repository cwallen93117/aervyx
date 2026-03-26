"use client";

import type { ReactNode } from "react";

export function SectionCard({
  title,
  description,
  children,
  actions,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const showHeader = Boolean(title || description || actions);
  return (
    <section className="panel section-card">
      {showHeader ? (
        <div className="section-card-header">
          <div>
            {title ? <h3>{title}</h3> : null}
            {description ? <p className="hint">{description}</p> : null}
          </div>
          {actions ? <div className="section-card-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
