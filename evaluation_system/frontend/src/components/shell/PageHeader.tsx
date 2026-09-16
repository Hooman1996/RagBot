import type { ReactNode } from "react";

export function PageHeader({ title, description, meta }: { title: string; description: string; meta?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {meta && <div className="page-header__meta">{meta}</div>}
    </header>
  );
}
