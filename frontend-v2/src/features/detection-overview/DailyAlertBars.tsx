import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChartTableToggle } from '@/components/charts/ChartTableToggle';
import { cn } from '@/utils/cn';
import { formatDate, formatNumber } from '@/utils/format';
import { dayKind, type DayKind } from './dayKind';

export interface DailyCount {
  date: string;
  count: number;
}

const FILL: Record<DayKind, string> = {
  weekday: 'var(--series-1)',
  weekend: 'var(--status-neutral)',
  today: 'var(--accent)',
};

/** E10 — new alerts per day; weekends grey, today gold. One series, so no legend box. */
export function DailyAlertBars({ days, rows }: { days: number; rows: DailyCount[] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [active, setActive] = useState<number | null>(null);
  const top = Math.max(1, ...rows.map((row) => row.count));
  const kindLabel = (kind: DayKind) =>
    kind === 'today' ? t('overviewTabs.dailyToday') : kind === 'weekend' ? t('overviewTabs.dailyWeekend') : t('overviewTabs.dailyWeekday');
  const readout = (row: DailyCount) =>
    `${t('overviewTabs.dailyReadout', { date: formatDate(row.date, language), count: row.count })} · ${kindLabel(dayKind(row.date))}`;
  const current = active !== null ? rows[active] : undefined;

  return (
    <ChartTableToggle
      chart={(toggle) => (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="flex flex-wrap items-center gap-3 text-muted">
              {(['weekday', 'weekend', 'today'] as const).map((kind) => (
                <span key={kind} className="inline-flex items-center gap-1.5">
                  <span className="size-2.5 rounded-sm" style={{ background: FILL[kind] }} aria-hidden />
                  {kindLabel(kind)}
                </span>
              ))}
            </span>
            {toggle}
          </div>
          <p className="mb-1 h-4 text-xs font-medium tabular-nums" aria-hidden>
            {current ? readout(current) : <span className="text-muted">{t('overviewTabs.dailyReadoutIdle')}</span>}
          </p>
          <div
            role="img"
            aria-label={`${t('overviewTabs.dailyChartLabel')} · ${t('overviewTabs.days', { count: days })}`}
            className={cn('flex h-40 items-end border-b border-border', rows.length > 45 ? 'gap-px' : 'gap-[2px]')}
            onMouseLeave={() => setActive(null)}
          >
            {rows.map((row, index) => {
              const kind = dayKind(row.date);
              return (
                // Full-height hit target, thin visible bar anchored to the baseline.
                <div
                  key={row.date}
                  className="flex h-full min-w-0 flex-1 items-end"
                  onMouseEnter={() => setActive(index)}
                  data-kind={kind}
                  data-testid="daily-bar"
                >
                  <div
                    className={cn('w-full rounded-t-[4px] transition-opacity', active !== null && active !== index && 'opacity-60')}
                    style={{ height: row.count === 0 ? 0 : `${Math.max(2, (row.count / top) * 100)}%`, background: FILL[kind] }}
                  />
                </div>
              );
            })}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-muted tabular-nums">
            <span>{rows[0] && formatDate(rows[0].date, language)}</span>
            <span>{t('overviewTabs.dailyToday')}</span>
          </div>
        </div>
      )}
      table={
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-[13px]" aria-label={t('overviewTabs.dailyChartLabel')}>
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-border text-left text-xs text-muted">
                <th scope="col" className="py-1.5 font-medium">{t('charts.date')}</th>
                <th scope="col" className="py-1.5 font-medium" />
                <th scope="col" className="py-1.5 text-right font-medium">{t('overviewTabs.created')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const kind = dayKind(row.date);
                return (
                  <tr key={row.date} className="border-b border-border last:border-0">
                    <td className="py-1.5">{formatDate(row.date, language)}</td>
                    <td className="py-1.5 text-muted">{kind === 'weekday' ? '' : kindLabel(kind)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(row.count, language)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      }
    />
  );
}
