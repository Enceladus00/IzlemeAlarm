import { AlertTriangle } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Counterparty, CustomerAnalysis as Analysis } from '@/api/schemas/customers';
import { ChartTableToggle } from '@/components/charts/ChartTableToggle';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';
import { formatDate, formatMoney, formatNumber } from '@/utils/format';
import { ANALYSIS_PERIODS, useCustomerAnalysis, type AnalysisPeriod } from './api';

const SERIES = { incoming: 'var(--series-1)', outgoing: 'var(--series-2)' } as const;

function monthLabel(month: string, language: string) {
  const [year, value] = month.split('-').map(Number);
  return new Intl.DateTimeFormat(language === 'en' ? 'en-GB' : 'tr-TR', { month: 'short', year: 'numeric' }).format(new Date(year!, value! - 1, 1));
}

/** E12 — monthly in/out, income warning and counterparties for one customer (compliance). */
export function CustomerAnalysis({ customerNo }: { customerNo: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [days, setDays] = useState<AnalysisPeriod>(90);
  const analysis = useCustomerAnalysis(customerNo, days);
  const data = analysis.data;

  return (
    <section aria-label={t('customers.analysisTitle')} className="mt-4 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t('customers.analysisTitle')}</h2>
          {data && (
            <p className="text-[13px] text-muted">
              {t('customers.analysisHint', { from: formatDate(data.date_from, language), to: formatDate(data.date_to, language) })}
            </p>
          )}
        </div>
        <Field label={t('customers.analysisPeriod')}>
          <Select value={String(days)} onChange={(event) => setDays(Number(event.target.value) as AnalysisPeriod)}>
            {ANALYSIS_PERIODS.map((period) => (
              <option key={period} value={period}>
                {t('customers.analysisDays', { count: period })}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {analysis.isError && !data ? (
        <ErrorState error={analysis.error} onRetry={() => void analysis.refetch()} />
      ) : !data ? (
        <div className="h-60 animate-pulse rounded-lg bg-neutral-soft" aria-hidden />
      ) : (
        <div className={cn('space-y-4 transition-opacity', analysis.isFetching && 'opacity-70')}>
          <IncomeWarning check={data.income_check} />
          <MonthlyCard monthly={data.monthly} />
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <CounterpartyCard title={t('customers.flowTitleIn')} rows={data.counterparties.incoming} />
            <CounterpartyCard title={t('customers.flowTitleOut')} rows={data.counterparties.outgoing} />
          </div>
        </div>
      )}
    </section>
  );
}

/** Shown only when the threshold is crossed (guide: 121.850 / 28.000 = 4,4 ×). */
function IncomeWarning({ check }: { check: Analysis['income_check'] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  if (!check.exceeded || !check.peak_month || !check.peak_direction) return null;
  return (
    <InlineAlert tone="warning">
      <span className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          <strong className="block">{t('customers.incomeWarningTitle')}</strong>
          {t('customers.incomeWarning', {
            month: monthLabel(check.peak_month, language),
            direction: t(`customers.incomeDirection.${check.peak_direction}`),
            amount: formatMoney(check.peak_amount, check.currency, language),
            income: formatMoney(check.monthly_income, check.currency, language),
            ratio: formatNumber(check.ratio, language, { maximumFractionDigits: 1 }),
            threshold: formatNumber(check.threshold, language),
          })}
        </span>
      </span>
    </InlineAlert>
  );
}

function MonthlyCard({ monthly }: { monthly: Analysis['monthly'] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const currencies = useMemo(() => {
    const all = [...new Set(monthly.map((row) => row.currency))];
    return all.sort((a, b) => (a === 'TRY' ? -1 : b === 'TRY' ? 1 : a.localeCompare(b)));
  }, [monthly]);
  const [picked, setPicked] = useState<string | null>(null);
  const currency = picked && currencies.includes(picked) ? picked : currencies[0];
  const rows = monthly.filter((row) => row.currency === currency).map((row) => ({ ...row, in: Number(row.incoming), out: Number(row.outgoing) }));
  const top = Math.max(1, ...rows.flatMap((row) => [row.in, row.out]));
  const [active, setActive] = useState<number | null>(null);
  const money = (value: number | string) => formatMoney(value, currency ?? '', language);
  const current = active !== null ? rows[active] : undefined;

  return (
    <Card>
      <CardHeader
        title={t('customers.monthlyTitle')}
        actions={
          currencies.length > 1 && (
            <Select aria-label={t('customers.monthlyCurrency')} value={currency} onChange={(event) => setPicked(event.target.value)}>
              {currencies.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
          )
        }
      />
      <div className="px-5 pb-5">
        {rows.length === 0 ? (
          <p className="text-[13px] text-muted">{t('customers.monthlyEmpty')}</p>
        ) : (
          <ChartTableToggle
            chart={(toggle) => (
              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="flex items-center gap-3 text-muted">
                    {(['incoming', 'outgoing'] as const).map((key) => (
                      <span key={key} className="inline-flex items-center gap-1.5">
                        <span className="size-2.5 rounded-sm" style={{ background: SERIES[key] }} aria-hidden />
                        {key === 'incoming' ? t('customers.monthlyIncoming') : t('customers.monthlyOutgoing')}
                      </span>
                    ))}
                  </span>
                  {toggle}
                </div>
                <p className="mb-1 h-4 text-xs font-medium tabular-nums" aria-hidden>
                  {current ? (
                    t('customers.monthlyReadout', { month: monthLabel(current.month, language), incoming: money(current.in), outgoing: money(current.out) })
                  ) : (
                    <span className="text-muted">{t('customers.monthlyIdle')}</span>
                  )}
                </p>
                <div
                  role="img"
                  aria-label={t('customers.monthlyChart', { currency })}
                  className="flex h-44 items-end gap-3 border-b border-border"
                  onMouseLeave={() => setActive(null)}
                >
                  {rows.map((row, index) => (
                    // Grouped bars: incoming and outgoing side by side, 2px apart.
                    <div key={row.month} className="flex h-full min-w-0 flex-1 items-end justify-center gap-[2px]" onMouseEnter={() => setActive(index)} data-testid="month-group">
                      {(['in', 'out'] as const).map((key) => (
                        <div
                          key={key}
                          className={cn('w-full max-w-8 rounded-t-[4px]', active !== null && active !== index && 'opacity-60')}
                          style={{ height: row[key] === 0 ? 0 : `${Math.max(2, (row[key] / top) * 100)}%`, background: key === 'in' ? SERIES.incoming : SERIES.outgoing }}
                        />
                      ))}
                    </div>
                  ))}
                </div>
                <div className="mt-1 flex gap-3 text-[11px] text-muted">
                  {rows.map((row) => (
                    <span key={row.month} className="min-w-0 flex-1 truncate text-center">
                      {monthLabel(row.month, language)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            table={
              <table className="w-full text-[13px]" aria-label={t('customers.monthlyChart', { currency })}>
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted">
                    <th scope="col" className="py-1.5 font-medium">{t('customers.month')}</th>
                    <th scope="col" className="py-1.5 text-right font-medium">{t('customers.monthlyIncoming')}</th>
                    <th scope="col" className="py-1.5 text-right font-medium">{t('customers.monthlyOutgoing')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.month} className="border-b border-border last:border-0">
                      <td className="py-1.5">{monthLabel(row.month, language)}</td>
                      <td className="py-1.5 text-right tabular-nums">{money(row.incoming)}</td>
                      <td className="py-1.5 text-right tabular-nums">{money(row.outgoing)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          />
        )}
      </div>
    </Card>
  );
}

function CounterpartyCard({ title, rows }: { title: string; rows: Counterparty[] }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  // Shares within each currency: amounts in different currencies are never added.
  const totals = new Map<string, number>();
  for (const row of rows) totals.set(row.currency, (totals.get(row.currency) ?? 0) + Number(row.amount));
  return (
    <Card>
      <CardHeader title={title} description={t('customers.flowHint')} />
      <div className="overflow-x-auto px-2 pb-3">
        {rows.length === 0 ? (
          <p className="px-3 py-2 text-[13px] text-muted">{t('customers.flowEmpty')}</p>
        ) : (
          <table className="w-full min-w-[520px] text-[13px]" aria-label={title}>
            <thead>
              <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                <th scope="col" className="px-3 py-2 font-medium">{t('customers.counterparty')}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t('customers.txCount')}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t('customers.amount')}</th>
                <th scope="col" className="w-32 px-3 py-2 font-medium">{t('customers.share')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const share = Number(row.amount) / (totals.get(row.currency) || 1);
                return (
                  <tr key={`${row.account_no}-${row.currency}`} className="border-b border-border last:border-0">
                    <td className="px-3 py-2">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="font-semibold">{row.customer_name}</span>
                        {row.is_new && <Badge tone="warning">{t('customers.newBadge')}</Badge>}
                      </span>
                      <span className="font-mono text-xs text-muted">{row.account_no}</span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.count, language)}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">{formatMoney(row.amount, row.currency, language)}</td>
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-2">
                        <span className="h-2 flex-1 rounded bg-neutral-soft" aria-hidden>
                          <span className="block h-2 rounded" style={{ width: `${Math.max(2, share * 100)}%`, background: 'var(--series-1)' }} />
                        </span>
                        <span className="w-10 text-right text-xs tabular-nums">{formatNumber(share, language, { style: 'percent', maximumFractionDigits: 0 })}</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}
