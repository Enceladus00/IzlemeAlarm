import { ArrowRightLeft, SearchX } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
import type { Transaction } from '@/api/schemas/transactions';
import { BarList } from '@/components/charts/BarList';
import { ChartTableToggle } from '@/components/charts/ChartTableToggle';
import { TrendChart } from '@/components/charts/TrendChart';
import { TransactionTable } from '@/components/TransactionTable';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { Spinner } from '@/components/ui/Spinner';
import { StatCard } from '@/components/ui/StatCard';
import { cn } from '@/utils/cn';
import { formatDate, formatMoney, formatNumber } from '@/utils/format';
import { TX_PAGE_SIZE, useTransactionSummary, useTransactions } from './api';
import {
  EMPTY_TX_FILTERS,
  parseTxFilters,
  toTxQuery,
  txFiltersToParams,
  validateTxFilters,
  type Direction,
  type TxFilters,
} from './filters';
import { useAccounts, useCustomers } from '@/features/customers/api';
import { CounterpartyFlow, CounterpartyTable } from './CounterpartyFlow';
import { centsToDecimal, toCents } from './flow';
import { FocusPicker } from './FocusPicker';
import { NetworkGraph } from './NetworkGraph';
import { type CurrencyTotal, type FocusOption } from './summary';

function moneyList(totals: CurrencyTotal[], language: string): string {
  if (totals.length === 0) return '0';
  return totals.map((total) => formatMoney(centsToDecimal(total.cents), total.currency, language)).join(' · ');
}

function parseFocus(value: string | null): FocusOption | null {
  const match = /^(customer|account):(.+)$/.exec(value ?? '');
  return match ? { type: match[1] as FocusOption['type'], id: match[2]!, name: match[2]! } : null;
}

export default function TransactionAnalysisPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const [params, setParams] = useSearchParams();
  const applied = parseTxFilters(params);
  const appliedErrors = validateTxFilters(applied);
  const appliedValid = Object.keys(appliedErrors).length === 0;
  const [draft, setDraft] = useState<TxFilters>(applied);
  const [draftErrors, setDraftErrors] = useState<ReturnType<typeof validateTxFilters>>({});

  // Keep the form in sync when the URL changes (e.g. a link from an alert).
  const paramsKey = params.toString();
  useEffect(() => {
    setDraft(parseTxFilters(new URLSearchParams(paramsKey)));
    setDraftErrors({});
  }, [paramsKey]);

  const query = useMemo(() => toTxQuery(applied), [paramsKey]); // eslint-disable-line react-hooks/exhaustive-deps
  // Transfers are only listed for one customer or account; without one the
  // page shows server-side totals, not an arbitrary slice of the ledger.
  const focus = parseFocus(params.get('focus'));
  const listQuery = useMemo(() => {
    if (focus) {
      return { ...query, customer_no: undefined, [focus.type === 'customer' ? 'customer_no' : 'account_no']: focus.id };
    }
    return query.customer_no ? query : null;
  }, [query, focus?.type, focus?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const transactions = useTransactions(listQuery ?? {}, appliedValid && listQuery !== null);
  const loaded: Transaction[] = transactions.data?.pages.flatMap((page) => page.items) ?? [];
  const total = transactions.data?.pages[0]?.total ?? 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const errors = validateTxFilters(draft);
    setDraftErrors(errors);
    if (Object.keys(errors).length === 0) setParams(txFiltersToParams(draft), { replace: false });
  };

  const setField = <K extends keyof TxFilters>(key: K, value: TxFilters[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const errorText = (key: keyof TxFilters) => {
    const code = draftErrors[key];
    return code ? t(`txAnalysis.${code}`) : undefined;
  };

  return (
    <>
      <PageHeader breadcrumb={t('txAnalysis.breadcrumb')} title={t('nav.transactions')} description={t('txAnalysis.description')} />

      <Card className="mb-4">
        <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t('txAnalysis.customerNo')} hint={t('txAnalysis.customerHint')}>
            <Input value={draft.customer} onChange={(e) => setField('customer', e.target.value)} maxLength={20} />
          </Field>
          <Field label={t('txAnalysis.direction')} error={errorText('direction')}>
            <Select value={draft.direction} onChange={(e) => setField('direction', e.target.value as Direction)}>
              {(['all', 'incoming', 'outgoing'] as const).map((value) => (
                <option key={value} value={value}>
                  {t(`txAnalysis.directions.${value}`)}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('txAnalysis.dateFrom')}>
              <Input type="date" value={draft.from} onChange={(e) => setField('from', e.target.value)} />
            </Field>
            <Field label={t('txAnalysis.dateTo')} error={errorText('to')}>
              <Input type="date" value={draft.to} onChange={(e) => setField('to', e.target.value)} />
            </Field>
          </div>
          <Field label={t('txAnalysis.minAmount')} error={errorText('min')}>
            <Input type="number" inputMode="decimal" min="0.01" step="any" value={draft.min} onChange={(e) => setField('min', e.target.value)} />
          </Field>
          <Field label={t('txAnalysis.maxAmount')} error={errorText('max')}>
            <Input type="number" inputMode="decimal" min="0.01" step="any" value={draft.max} onChange={(e) => setField('max', e.target.value)} />
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit" variant="primary">
              {t('txAnalysis.analyze')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDraft(EMPTY_TX_FILTERS);
                setDraftErrors({});
                setParams(new URLSearchParams());
              }}
            >
              {t('txAnalysis.reset')}
            </Button>
          </div>
        </form>
      </Card>

      {!appliedValid ? (
        <InlineAlert tone={appliedErrors.direction ? 'info' : 'danger'} live>
          {Object.values(appliedErrors).map((code) => t(`txAnalysis.${code}`)).join(' ')}
        </InlineAlert>
      ) : (
        <Results
          list={listQuery ? { transactions: loaded, error: transactions.isError ? transactions.error : null, pending: transactions.isPending, retry: () => void transactions.refetch() } : null}
          total={total}
          customerNo={focus?.type === 'customer' ? focus.id : applied.customer}
          baseQuery={query}
          direction={applied.direction}
          focusParam={params.get('focus')}
          onFocus={(focus) => setParams(txFiltersToParams(applied, focus), { replace: true })}
          hasMore={!!transactions.hasNextPage}
          loadingMore={transactions.isFetchingNextPage}
          onLoadMore={() => void transactions.fetchNextPage()}
          language={language}
        />
      )}
    </>
  );
}

function Results({
  list,
  total,
  customerNo,
  baseQuery,
  direction,
  focusParam,
  onFocus,
  hasMore,
  loadingMore,
  onLoadMore,
  language,
}: {
  list: { transactions: Transaction[]; error: unknown; pending: boolean; retry: () => void } | null;
  total: number;
  customerNo: string;
  baseQuery: ReturnType<typeof toTxQuery>;
  direction: Direction;
  focusParam: string | null;
  onFocus: (focus: string | null) => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  language: string;
}) {
  const { t } = useTranslation();
  // K12: totals, timeline and flow come from the server over every matching transfer.
  const serverSummary = useTransactionSummary(baseQuery);
  const fmt = (value: number) => formatNumber(value, language);
  if (serverSummary.isError) return <ErrorState error={serverSummary.error} onRetry={() => void serverSummary.refetch()} />;
  if (!serverSummary.data)
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <StatCard key={index} loading label=" " value="" />
        ))}
      </div>
    );
  const data = serverSummary.data;
  if (data.transfer_count === 0)
    return (
      <Card>
        <EmptyState icon={SearchX} title={t('txAnalysis.emptyTitle')}>
          {t('txAnalysis.emptyBody')}
        </EmptyState>
      </Card>
    );
  const focused = data.by_currency.some((row) => row.incoming !== null);
  const totalsOf = (pick: (row: (typeof data.by_currency)[number]) => { amount: string | null; count: number | null }): CurrencyTotal[] =>
    data.by_currency
      .map((row) => ({ currency: row.currency, ...pick(row) }))
      .filter((row) => row.count)
      .map((row) => ({ currency: row.currency, count: row.count ?? 0, cents: toCents(row.amount ?? '0') }));
  const summary = {
    count: data.transfer_count,
    uniqueAccounts: data.account_count,
    totals: focused ? null : totalsOf((row) => ({ amount: row.total, count: row.count })),
    incoming: focused ? totalsOf((row) => ({ amount: row.incoming, count: row.incoming_count })) : null,
    outgoing: focused ? totalsOf((row) => ({ amount: row.outgoing, count: row.outgoing_count })) : null,
  };
  const timeline = {
    granularity: data.timeline.granularity,
    buckets: data.timeline.points.map((point) => ({ date: point.date, count: point.count })),
  };

  const directionBars = summary.totals
    ? summary.totals.map((row) => ({ key: row.currency, label: <span className="font-mono">{row.currency}</span>, value: row.count }))
    : [
        ...summary.incoming!.map((row) => ({
          key: `in-${row.currency}`,
          label: `${t('txAnalysis.directions.incoming')} · ${row.currency}`,
          value: row.count,
          color: 'var(--series-1)',
        })),
        ...summary.outgoing!.map((row) => ({
          key: `out-${row.currency}`,
          label: `${t('txAnalysis.directions.outgoing')} · ${row.currency}`,
          value: row.count,
          color: 'var(--series-2)',
        })),
      ];

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">{t('txAnalysis.summary', { total: data.transfer_count })}</p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={t('txAnalysis.metricTransfers')} value={fmt(summary.count)} />
        {summary.totals ? (
          <div className="sm:col-span-2">
            <StatCard
              label={t('txAnalysis.metricTotal')}
              value={<span className="text-xl break-words">{moneyList(summary.totals, language)}</span>}
              caption={t('txAnalysis.metricTotalHint')}
            />
          </div>
        ) : (
          <>
            <StatCard label={t('txAnalysis.metricIncoming')} value={<span className="text-xl break-words">{moneyList(summary.incoming!, language)}</span>} />
            <StatCard label={t('txAnalysis.metricOutgoing')} value={<span className="text-xl break-words">{moneyList(summary.outgoing!, language)}</span>} />
          </>
        )}
        <StatCard label={t('txAnalysis.metricAccounts')} value={fmt(summary.uniqueAccounts)} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={summary.totals ? t('txAnalysis.flowTitleNoCustomer') : t('txAnalysis.flowTitle')}
            description={t('txAnalysis.flowCaption')}
          />
          <div className="px-5 pt-3 pb-5">
            <BarList label={summary.totals ? t('txAnalysis.flowTitleNoCustomer') : t('txAnalysis.flowTitle')} items={directionBars} />
            {summary.totals && <p className="mt-3 text-xs text-muted">{t('txAnalysis.flowNoCustomerNote')}</p>}
          </div>
        </Card>
        <Card>
          <CardHeader
            title={t('txAnalysis.timelineTitle')}
            description={timeline.granularity === 'day' ? t('txAnalysis.timelineDaily') : t('txAnalysis.timelineWeekly')}
          />
          <div className="px-5 pt-3 pb-5">
            <ChartTableToggle
              chart={(toggle) => (
                <TrendChart
                  title={t('txAnalysis.timelineTitle')}
                  series={[{ key: 'count', label: t('txAnalysis.timelineSeries'), color: 'var(--series-1)' }]}
                  points={timeline.buckets.map((bucket) => ({ date: bucket.date, values: { count: bucket.count } }))}
                  toolbar={toggle}
                />
              )}
              table={
                <div className="max-h-64 overflow-y-auto">
                  <table className="w-full text-[13px]">
                    <thead className="sticky top-0 bg-surface">
                      <tr className="border-b border-border text-left text-xs text-muted">
                        <th scope="col" className="py-1.5 font-medium">{t('charts.date')}</th>
                        <th scope="col" className="py-1.5 text-right font-medium">{t('txAnalysis.timelineSeries')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timeline.buckets.map((bucket) => (
                        <tr key={bucket.date} className="border-b border-border last:border-0">
                          <td className="py-1.5">{formatDate(bucket.date, language)}</td>
                          <td className="py-1.5 text-right tabular-nums">{fmt(bucket.count)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              }
            />
          </div>
        </Card>
      </div>

      <AccountMovement
        baseQuery={baseQuery}
        direction={direction}
        focusParam={focusParam}
        onFocus={onFocus}
      />

      <Card>
        <CardHeader
          title={t('txAnalysis.transfersTitle')}
          description={list ? t('txAnalysis.transfersShown', { shown: list.transactions.length, total }) : undefined}
        />
        <div className="px-2 pt-3 pb-3">
          {!list ? (
            <EmptyState icon={ArrowRightLeft} title={t('txAnalysis.transfersPickTitle')} className="py-6">
              {t('txAnalysis.transfersPickBody')}
            </EmptyState>
          ) : list.error ? (
            <ErrorState error={list.error} onRetry={list.retry} />
          ) : list.pending ? (
            <p className="flex items-center gap-2 px-3 text-[13px] text-muted" role="status">
              <Spinner className="size-4" />
              {t('txAnalysis.transfersLoading')}
            </p>
          ) : (
            <TransactionTable
              transactions={list.transactions}
              label={t('txAnalysis.transfersTitle')}
              focusCustomerNo={customerNo || undefined}
              showAlertLinked
            />
          )}
        </div>
      </Card>
      {list && hasMore && (
        <div className="flex justify-center">
          <Button loading={loadingMore} onClick={onLoadMore}>
            {t('txAnalysis.loadMore', { count: Math.min(TX_PAGE_SIZE, total - list.transactions.length) })}
          </Button>
        </div>
      )}
    </div>
  );
}

function AccountMovement({
  baseQuery,
  direction,
  focusParam,
  onFocus,
}: {
  baseQuery: ReturnType<typeof toTxQuery>;
  direction: Direction;
  focusParam: string | null;
  onFocus: (focus: string | null) => void;
}) {
  const { t } = useTranslation();
  const parsed = parseFocus(focusParam);
  // The picker knows the name; a focus that came in through the URL is looked up once.
  const [chosen, setChosen] = useState<FocusOption | null>(null);
  const known = chosen && parsed && chosen.type === parsed.type && chosen.id === parsed.id ? chosen : null;
  const lookupCustomer = useCustomers({ q: parsed?.id ?? '', limit: 1 }, Boolean(parsed && !known && parsed.type === 'customer'));
  const lookupAccount = useAccounts({ q: parsed?.id ?? '', limit: 1 }, Boolean(parsed && !known && parsed.type === 'account'));
  const focus: FocusOption | null = !parsed
    ? null
    : (known ??
      (parsed.type === 'customer'
        ? (() => {
            const item = lookupCustomer.data?.items.find((entry) => entry.customer_no === parsed.id);
            return item ? { ...parsed, name: item.full_name } : parsed;
          })()
        : (() => {
            const item = lookupAccount.data?.items.find((entry) => entry.account_no === parsed.id);
            return item ? { ...parsed, name: item.customer_name, customerNo: item.customer_no, currency: item.currency } : parsed;
          })()));

  // The page's date/amount filters, re-scoped to the focus.
  const focusQuery = focus
    ? {
        date_from: baseQuery.date_from,
        date_to: baseQuery.date_to,
        min_amount: baseQuery.min_amount,
        max_amount: baseQuery.max_amount,
        direction: direction === 'all' ? undefined : direction,
        [focus.type === 'customer' ? 'customer_no' : 'account_no']: focus.id,
      }
    : null;
  const focused = useTransactionSummary(focusQuery);
  const [view, setView] = useState<'rows' | 'network'>('rows');
  const graphFilters = {
    date_from: baseQuery.date_from,
    date_to: baseQuery.date_to,
    min_amount: baseQuery.min_amount,
    max_amount: baseQuery.max_amount,
  };

  return (
    <Card>
      <CardHeader title={t('txAnalysis.movementTitle')} description={t('txAnalysis.movementDescription')} />
      <div className="space-y-4 p-5">
        <FocusPicker
          focus={focus}
          onChange={(option) => {
            setChosen(option);
            onFocus(option ? `${option.type}:${option.id}` : null);
          }}
        />

        {!focus ? (
          <EmptyState icon={ArrowRightLeft} title={t('txAnalysis.focusNone')} className="py-6">
            {t('txAnalysis.movementDescription')}
          </EmptyState>
        ) : focused.isError ? (
          <ErrorState error={focused.error} onRetry={() => void focused.refetch()} />
        ) : focused.isPending ? (
          <p className="flex items-center gap-2 text-[13px] text-muted" role="status">
            <Spinner className="size-4" />
            {t('txAnalysis.focusLoading', { name: focus.name })}
          </p>
        ) : focused.data.routes.length === 0 ? (
          <InlineAlert tone="info">{t('txAnalysis.focusEmpty')}</InlineAlert>
        ) : (
          <div className={cn('space-y-3', focused.isFetching && 'opacity-70')}>
            <div className="inline-flex rounded-md border border-border p-0.5" role="group" aria-label={t('txAnalysis.viewLabel')}>
              {(['rows', 'network'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={view === value}
                  onClick={() => setView(value)}
                  className={cn(
                    'rounded px-3 py-1 text-[13px] font-medium',
                    view === value ? 'bg-accent text-accent-fg' : 'text-muted hover:bg-surface-muted',
                  )}
                >
                  {t(`txAnalysis.views.${value}`)}
                </button>
              ))}
            </div>
            {view === 'network' ? (
              <NetworkGraph key={`${focus.type}:${focus.id}`} summary={focused.data} focusName={focus.name} filters={graphFilters} />
            ) : (
              <ChartTableToggle
                chart={(toggle) => (
                  <>
                    <div className="mb-2 flex justify-end">{toggle}</div>
                    <CounterpartyFlow summary={focused.data} focusName={focus.name} />
                  </>
                )}
                table={<CounterpartyTable summary={focused.data} />}
              />
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
