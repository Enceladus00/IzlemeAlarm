import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TransactionSummary } from '@/api/schemas/transactions';
import { cn } from '@/utils/cn';
import { formatDate, formatMoney, formatNumber } from '@/utils/format';
import { buildCounterpartyFlow, type CounterpartyRow } from './counterparties';
import { centsToDecimal, toCents } from './flow';

const PAGE = 15;
const IN = 'var(--series-1)';
const OUT = 'var(--series-2)';
const ALERT = 'var(--status-critical)';

const ratio = (part: bigint, whole: bigint) => (whole > 0n ? Number((part * 10000n) / whole) / 10000 : 0);

/**
 * Focus-centred view: one row per counterparty, money in from it as a bar to
 * the left of the axis, money out to it to the right. Bar length is amount
 * (not count), the red part is the alert-linked share, and the rule codes are
 * listed. A counterparty that both sends and receives sits on one row, so
 * back-and-forth flows are visible as two bars on the same line.
 */
export function CounterpartyFlow({ summary, focusName }: { summary: TransactionSummary; focusName: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const flow = useMemo(() => buildCounterpartyFlow(summary.routes), [summary.routes]);
  const [currency, setCurrency] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);
  const active = currency && flow.currencies.includes(currency) ? currency : (flow.currencies[0] ?? '');
  const rows = flow.rows.filter((row) => row.currency === active);
  const money = (cents: bigint) => formatMoney(centsToDecimal(cents), active, language);
  const totalIn = rows.reduce((sum, row) => sum + row.inCents, 0n);
  const totalOut = rows.reduce((sum, row) => sum + row.outCents, 0n);
  const maxSide = rows.reduce((max, row) => (row.inCents > max ? row.inCents : row.outCents > max ? row.outCents : max), 0n);
  const both = rows.filter((row) => row.inCents > 0n && row.outCents > 0n).length;
  const other = summary.other_routes.by_currency.find((entry) => entry.currency === active);
  const internal = flow.internal.find((entry) => entry.currency === active);

  return (
    <div className="space-y-5">
      {flow.currencies.length > 1 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('txAnalysis.cpCurrency')}>
          {flow.currencies.map((code) => (
            <button
              key={code}
              type="button"
              aria-pressed={code === active}
              onClick={() => {
                setCurrency(code);
                setShown(PAGE);
              }}
              className={cn(
                'rounded-full border px-2.5 py-0.5 text-xs font-medium',
                code === active ? 'border-accent bg-accent/10' : 'border-border text-muted',
              )}
            >
              {code}
            </button>
          ))}
        </div>
      )}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={t('txAnalysis.cpIn')} value={money(totalIn)} color={IN} />
        <Stat label={t('txAnalysis.cpOut')} value={money(totalOut)} color={OUT} />
        <Stat label={t('txAnalysis.cpNet')} value={money(totalIn - totalOut)} />
        <Stat
          label={t('txAnalysis.cpPassThrough')}
          value={totalIn > 0n ? `${formatNumber(ratio(totalOut, totalIn) * 100, language, { maximumFractionDigits: 0 })}%` : '—'}
          hint={t('txAnalysis.cpPassThroughHint')}
        />
      </dl>

      <div>
        <div className="mb-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] items-end gap-3 text-[11px] font-medium tracking-wide text-muted uppercase">
          <span className="text-right">{t('txAnalysis.cpInFrom')}</span>
          <span className="text-center">{t('txAnalysis.cpCounterparty', { name: focusName })}</span>
          <span>{t('txAnalysis.cpOutTo')}</span>
        </div>
        <ul className="divide-y divide-border rounded-lg border border-border">
          {rows.slice(0, shown).map((row) => (
            <Row key={`${row.account}|${row.currency}`} row={row} maxSide={maxSide} money={money} />
          ))}
        </ul>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <span>
            {t('txAnalysis.cpSummary', { count: rows.length, both })}
            {internal && ` ${t('txAnalysis.cpInternal', { count: internal.count, amount: money(internal.cents) })}`}
            {other && ` ${t('txAnalysis.cpOther', { routes: summary.other_routes.route_count, amount: money(toCents(other.amount)) })}`}
          </span>
          {rows.length > shown && (
            <button type="button" className="font-medium text-accent hover:underline" onClick={() => setShown((n) => n + PAGE)}>
              {t('txAnalysis.cpMore', { count: Math.min(PAGE, rows.length - shown) })}
            </button>
          )}
        </div>
      </div>

      <FlowTimeline summary={summary} currency={active} />

      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <Legend color={IN} label={t('txAnalysis.cpLegendIn')} />
        <Legend color={OUT} label={t('txAnalysis.cpLegendOut')} />
        <Legend color={ALERT} label={t('txAnalysis.cpLegendAlert')} />
      </ul>
    </div>
  );
}

function Row({ row, maxSide, money }: { row: CounterpartyRow; maxSide: bigint; money: (cents: bigint) => string }) {
  const { t } = useTranslation();
  const tooltip = t('txAnalysis.cpRowTooltip', {
    name: row.label || row.account,
    in: money(row.inCents),
    inCount: row.inCount,
    out: money(row.outCents),
    outCount: row.outCount,
    share: Math.round(row.flaggedShare * 100),
  });
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] items-center gap-3 px-3 py-2" title={tooltip}>
      <Bar cents={row.inCents} max={maxSide} share={row.flaggedShare} color={IN} side="left" label={money(row.inCents)} count={row.inCount} />
      <div className="min-w-0 text-center">
        <div className="truncate text-[13px] font-medium">{row.label || row.account}</div>
        <div className="flex items-center justify-center gap-1.5 text-xs text-muted">
          <span className="font-mono">{row.account}</span>
          {row.rules.map((rule) => (
            <span key={rule} className="rounded bg-danger/10 px-1 font-mono text-[11px] text-danger">
              {rule}
            </span>
          ))}
        </div>
      </div>
      <Bar cents={row.outCents} max={maxSide} share={row.flaggedShare} color={OUT} side="right" label={money(row.outCents)} count={row.outCount} />
    </li>
  );
}

function Bar({
  cents,
  max,
  share,
  color,
  side,
  label,
  count,
}: {
  cents: bigint;
  max: bigint;
  share: number;
  color: string;
  side: 'left' | 'right';
  label: string;
  count: number;
}) {
  const width = Math.max(cents > 0n ? 2 : 0, ratio(cents, max) * 100);
  return (
    <div className={cn('flex min-w-0 items-center gap-2', side === 'left' && 'flex-row-reverse')}>
      <div className={cn('flex h-4 flex-1', side === 'left' && 'justify-end')}>
        {cents > 0n && (
          <div
            className={cn('flex h-full overflow-hidden', side === 'left' ? 'flex-row-reverse rounded-l' : 'rounded-r')}
            style={{ width: `${width}%`, background: color, opacity: 0.85 }}
          >
            {share > 0 && <div style={{ width: `${Math.max(4, share * 100)}%`, background: ALERT }} />}
          </div>
        )}
      </div>
      <span className="w-28 shrink-0 text-xs tabular-nums whitespace-nowrap">
        {cents > 0n ? (
          <>
            <span className="font-medium">{label}</span> <span className="text-muted">×{count}</span>
          </>
        ) : (
          <span className="text-subtle">—</span>
        )}
      </span>
    </div>
  );
}

/** Money in above the axis, money out below, per bucket: shows pass-through and bursts. */
function FlowTimeline({ summary, currency }: { summary: TransactionSummary; currency: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const points = summary.flow_timeline.filter((point) => point.currency === currency);
  if (points.length === 0) return null;
  const values = points.map((point) => ({ ...point, in: toCents(point.incoming), out: toCents(point.outgoing) }));
  const max = values.reduce((m, p) => (p.in > m ? p.in : p.out > m ? p.out : m), 1n);
  const height = 56;
  return (
    <figure>
      <figcaption className="mb-2 text-[13px] font-medium">
        {t(summary.timeline.granularity === 'week' ? 'txAnalysis.cpTimelineWeekly' : 'txAnalysis.cpTimelineDaily')}
      </figcaption>
      <div className="flex items-stretch gap-px overflow-x-auto rounded-lg border border-border bg-surface-muted p-2" role="img" aria-label={t('txAnalysis.cpTimelineAria')}>
        {values.map((point) => (
          <div
            key={point.date}
            className="flex min-w-[6px] flex-1 flex-col"
            title={t('txAnalysis.cpTimelineTooltip', {
              date: formatDate(point.date, language),
              in: formatMoney(centsToDecimal(point.in), currency, language),
              out: formatMoney(centsToDecimal(point.out), currency, language),
            })}
          >
            <div className="flex flex-col justify-end" style={{ height }}>
              <div style={{ height: `${ratio(point.in, max) * 100}%`, background: IN }} className="rounded-t-sm" />
            </div>
            <div className="h-px bg-border-strong" />
            <div style={{ height }}>
              <div style={{ height: `${ratio(point.out, max) * 100}%`, background: OUT }} className="rounded-b-sm" />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted">
        <span>{formatDate(values[0]!.date, language)}</span>
        <span>{formatDate(values[values.length - 1]!.date, language)}</span>
      </div>
    </figure>
  );
}

function Stat({ label, value, color, hint }: { label: string; value: string; color?: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border px-3 py-2" title={hint}>
      <dt className="flex items-center gap-1.5 text-xs text-muted">
        {color && <span className="size-2 rounded-full" style={{ background: color }} aria-hidden />}
        {label}
      </dt>
      <dd className="mt-0.5 text-[15px] font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className="h-2 w-4 rounded-sm" style={{ background: color }} aria-hidden />
      {label}
    </li>
  );
}

/** Exact numbers for the same rows (screen readers, export by copy). */
export function CounterpartyTable({ summary }: { summary: TransactionSummary }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const flow = useMemo(() => buildCounterpartyFlow(summary.routes), [summary.routes]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-[13px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
            <th scope="col" className="px-3 py-2 font-medium">{t('txAnalysis.cpTable.counterparty')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('txAnalysis.cpIn')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('txAnalysis.cpOut')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('txAnalysis.cpTable.flagged')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('txAnalysis.cpTable.rules')}</th>
          </tr>
        </thead>
        <tbody>
          {flow.rows.map((row) => (
            <tr key={`${row.account}|${row.currency}`} className="border-b border-border last:border-0">
              <td className="px-3 py-2">
                {row.label} <span className="font-mono text-xs text-muted">{row.account}</span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatMoney(centsToDecimal(row.inCents), row.currency, language)} ×{row.inCount}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatMoney(centsToDecimal(row.outCents), row.currency, language)} ×{row.outCount}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{Math.round(row.flaggedShare * 100)}%</td>
              <td className="px-3 py-2 font-mono text-xs">{row.rules.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
