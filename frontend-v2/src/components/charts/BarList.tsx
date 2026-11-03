import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { formatNumber } from '@/utils/format';

export interface BarListItem {
  key: string;
  label: ReactNode;
  value: number;
  /** CSS colour for the bar; defaults to the first series colour. */
  color?: string;
}

/**
 * Horizontal bars on one baseline. Every value is printed at the bar tip,
 * so nothing depends on hover and the list reads as a table to assistive tech.
 */
export function BarList({ items, label }: { items: BarListItem[]; label: string }) {
  const { i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const max = Math.max(1, ...items.map((item) => item.value));

  return (
    <table className="w-full border-separate border-spacing-y-1.5 text-[13px]" aria-label={label}>
      <tbody>
        {items.map((item) => (
          <tr key={item.key}>
            <th scope="row" className="w-px pr-3 text-left font-medium whitespace-nowrap text-fg">
              {item.label}
            </th>
            <td className="w-full">
              <div className="flex items-center gap-2">
                <div className="h-3.5 flex-1">
                  {item.value > 0 && (
                    <div
                      className="h-full rounded-r-[4px]"
                      style={{
                        width: `${Math.max(1.5, (item.value / max) * 100)}%`,
                        background: item.color ?? 'var(--series-1)',
                      }}
                    />
                  )}
                </div>
                <span className="w-12 text-right font-semibold text-fg tabular-nums">{formatNumber(item.value, language)}</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
