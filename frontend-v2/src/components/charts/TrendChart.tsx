import { useId, useMemo, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { formatDate, formatNumber, parseApiDate } from '@/utils/format';
import { niceTicks } from './scale';
import { useElementWidth } from './useElementWidth';

export interface TrendSeries {
  key: string;
  label: string;
  /** CSS colour (a chart token such as var(--series-1)). */
  color: string;
}

export interface TrendPoint {
  date: string;
  values: Record<string, number>;
}

const HEIGHT = 240;
const MARGIN = { top: 16, right: 44, bottom: 28, left: 40 };

/**
 * Multi-series line chart on one shared count axis: 2px lines, crosshair
 * tooltip listing every series, keyboard navigation, a legend, and selective
 * end labels (dropped when they would collide).
 */
export function TrendChart({
  series,
  points,
  title,
  toolbar,
}: {
  series: TrendSeries[];
  points: TrendPoint[];
  title: string;
  /** Optional control rendered at the right end of the legend row. */
  toolbar?: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [containerRef, width] = useElementWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const hintId = useId();

  const plotWidth = Math.max(120, width - MARGIN.left - MARGIN.right);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const maxValue = Math.max(0, ...points.flatMap((point) => series.map((s) => point.values[s.key] ?? 0)));
  const ticks = niceTicks(maxValue);
  const top = ticks[ticks.length - 1] ?? 1;

  const x = (index: number) => MARGIN.left + (points.length <= 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
  const y = (value: number) => MARGIN.top + plotHeight - (value / top) * plotHeight;

  const paths = useMemo(
    () =>
      series.map((s) =>
        points.map((point, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${y(point.values[s.key] ?? 0).toFixed(1)}`).join(' '),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [series, points, plotWidth, top],
  );

  const shortDate = (value: string) => {
    const date = parseApiDate(value);
    return date
      ? new Intl.DateTimeFormat(language === 'en' ? 'en-GB' : 'tr-TR', { day: '2-digit', month: 'short' }).format(date)
      : value;
  };

  // Roughly one x label per 90px, always including the last day.
  const labelEvery = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(plotWidth / 90))));
  const lastIndex = points.length - 1;

  // End labels only when the two end values sit at least 14px apart.
  const endYs = series.map((s) => y(points[lastIndex]?.values[s.key] ?? 0));
  const showEndLabels = endYs.every((value, index) => endYs.every((other, j) => j === index || Math.abs(value - other) >= 14));

  const onPointerMove = (event: PointerEvent<SVGRectElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    setActive(Math.min(lastIndex, Math.max(0, Math.round(ratio * lastIndex))));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = active ?? lastIndex;
    let next: number | null = current;
    if (event.key === 'ArrowLeft') next = Math.max(0, current - 1);
    else if (event.key === 'ArrowRight') next = Math.min(lastIndex, current + 1);
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = lastIndex;
    else if (event.key === 'Escape') next = null;
    else return;
    event.preventDefault();
    setActive(next);
  };

  const activePoint = active !== null ? points[active] : undefined;
  const tooltipLeft = active !== null ? x(active) : 0;
  const tooltipOnLeft = tooltipLeft > width * 0.6;

  return (
    <div className="min-w-0">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label={t('charts.legend')}>
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-2">
              <span className="h-0.5 w-4 rounded-full" style={{ background: s.color }} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>
        {toolbar}
      </div>
      <div
        ref={containerRef}
        className="relative w-full overflow-hidden rounded-md focus-visible:outline-2"
        tabIndex={0}
        role="group"
        aria-label={title}
        aria-describedby={hintId}
        onKeyDown={onKeyDown}
        onBlur={() => setActive(null)}
      >
        <span id={hintId} className="sr-only">
          {t('charts.keyboardHint')}
        </span>
        <svg width={width} height={HEIGHT} className="block" aria-hidden>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} stroke="var(--chart-grid)" strokeWidth={1} />
              <text x={MARGIN.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-subtle text-[11px] tabular-nums">
                {formatNumber(tick, language)}
              </text>
            </g>
          ))}
          <line
            x1={MARGIN.left}
            x2={MARGIN.left + plotWidth}
            y1={y(0)}
            y2={y(0)}
            stroke="var(--chart-axis)"
            strokeWidth={1}
          />
          {points.map((point, index) =>
            index % labelEvery === 0 || index === lastIndex ? (
              index !== lastIndex && lastIndex - index < labelEvery / 2 ? null : (
                <text
                  key={point.date}
                  x={x(index)}
                  y={HEIGHT - 8}
                  textAnchor={index === 0 ? 'start' : index === lastIndex ? 'end' : 'middle'}
                  className="fill-subtle text-[11px]"
                >
                  {shortDate(point.date)}
                </text>
              )
            ) : null,
          )}
          {active !== null && (
            <line x1={x(active)} x2={x(active)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} stroke="var(--chart-axis)" strokeWidth={1} />
          )}
          {series.map((s, index) => (
            <path key={s.key} d={paths[index]} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {series.map((s) => {
            const markerIndex = active ?? lastIndex;
            const value = points[markerIndex]?.values[s.key] ?? 0;
            return (
              <circle key={s.key} cx={x(markerIndex)} cy={y(value)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            );
          })}
          {showEndLabels &&
            active === null &&
            series.map((s) => {
              const value = points[lastIndex]?.values[s.key] ?? 0;
              return (
                <text key={s.key} x={x(lastIndex) + 8} y={y(value)} dy="0.32em" className="fill-fg text-[11px] font-semibold tabular-nums">
                  {formatNumber(value, language)}
                </text>
              );
            })}
          <rect
            x={MARGIN.left}
            y={MARGIN.top}
            width={plotWidth}
            height={plotHeight}
            fill="transparent"
            onPointerMove={onPointerMove}
            onPointerLeave={() => setActive(null)}
          />
        </svg>
        <div aria-live="polite" className="sr-only">
          {activePoint &&
            `${formatDate(activePoint.date, language)}: ${series
              .map((s) => `${s.label} ${formatNumber(activePoint.values[s.key] ?? 0, language)}`)
              .join(', ')}`}
        </div>
        {activePoint && (
          <div
            className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-md"
            style={tooltipOnLeft ? { right: width - tooltipLeft + 12 } : { left: tooltipLeft + 12 }}
            aria-hidden
          >
            <p className="mb-1 text-muted">{formatDate(activePoint.date, language)}</p>
            {series.map((s) => (
              <p key={s.key} className="flex items-center gap-2">
                <span className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
                <span className="font-semibold text-fg tabular-nums">{formatNumber(activePoint.values[s.key] ?? 0, language)}</span>
                <span className="text-muted">{s.label}</span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
