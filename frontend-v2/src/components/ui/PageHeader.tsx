import type { ReactNode } from 'react';

export function PageHeader({
  breadcrumb,
  title,
  description,
  actions,
}: {
  breadcrumb?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {breadcrumb && <p className="mb-1 text-xs text-muted">{breadcrumb}</p>}
        <h1 className="text-2xl font-bold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[13px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{actions}</div>}
    </header>
  );
}
