import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/utils/cn';

/**
 * Marks a value the API cannot supply yet. The sample content is visually
 * distinct (dashed, purple) and labelled so it is never mistaken for real data.
 */
export function Placeholder({
  children,
  className,
}: {
  children?: ReactNode;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded border border-dashed border-placeholder bg-placeholder-soft px-1.5 py-0.5 text-placeholder',
        className,
      )}
      title={t('placeholder.tooltip')}
      data-placeholder="true"
    >
      {children !== undefined && <span>{children}</span>}
      <span className="text-[10px] font-semibold tracking-wide uppercase">{t('placeholder.badge')}</span>
      <span className="sr-only">{t('placeholder.tooltip')}</span>
    </span>
  );
}
