import { ChevronLeft, ChevronRight, Search, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';
import { CUSTOMER_TYPE_VALUES, RISK_LEVELS } from '@/api/schemas/customers';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { Tabs } from '@/components/ui/Tabs';
import { cn } from '@/utils/cn';
import { formatDate, formatNumber } from '@/utils/format';
import { CUSTOMER_PAGE_SIZE, useAccounts, useCustomers } from './api';

type Tab = 'customers' | 'accounts';
const SEARCH_DEBOUNCE_MS = 300;

/** Customer and account lists (customer:view), filtered and paged on the server. */
export default function CustomersPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get('tab') === 'accounts' ? 'accounts' : 'customers';

  const update = (patch: Record<string, string | null>) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null || value === '') next.delete(key);
          else next.set(key, value);
        }
        if (!('page' in patch)) next.delete('page');
        return next;
      },
      { replace: true },
    );

  return (
    <>
      <PageHeader breadcrumb={t('customers.breadcrumb')} title={t('nav.customers')} description={t('customers.description')} />
      <Tabs
        label={t('customers.tabsLabel')}
        value={tab}
        onChange={(next) => setParams(next === 'accounts' ? { tab: 'accounts' } : {}, { replace: true })}
        items={[
          { value: 'customers', label: t('customers.tabCustomers'), content: <CustomerList params={params} update={update} /> },
          { value: 'accounts', label: t('customers.tabAccounts'), content: <AccountList params={params} update={update} /> },
        ]}
      />
    </>
  );
}

type Update = (patch: Record<string, string | null>) => void;

function useDebouncedSearch(value: string, onCommit: (value: string) => void) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (draft.trim() === value.trim()) return;
    const timer = setTimeout(() => onCommit(draft.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);
  return [draft, setDraft] as const;
}

function page(params: URLSearchParams): number {
  const value = Number(params.get('page') ?? '1');
  return Number.isInteger(value) && value > 1 ? value - 1 : 0;
}

function Pager({ current, total, onPage }: { current: number; total: number; onPage: (page: number) => void }) {
  const { t } = useTranslation();
  const pages = Math.max(1, Math.ceil(total / CUSTOMER_PAGE_SIZE));
  if (pages <= 1) return null;
  return (
    <nav className="flex items-center justify-end gap-2 px-5 py-3 text-xs text-muted" aria-label={t('customers.pagination')}>
      <Button size="sm" disabled={current === 0} onClick={() => onPage(current - 1)}>
        <ChevronLeft className="size-4" aria-hidden />
        {t('common.previous')}
      </Button>
      <span>{t('customers.pageOf', { page: current + 1, pages })}</span>
      <Button size="sm" disabled={current + 1 >= pages} onClick={() => onPage(current + 1)}>
        {t('common.next')}
        <ChevronRight className="size-4" aria-hidden />
      </Button>
    </nav>
  );
}

function SearchBox({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-[13px] font-medium">
        {label}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" aria-hidden />
        <Input id={id} type="search" maxLength={100} value={value} className="pl-9" onChange={(e) => onChange(e.target.value)} />
      </div>
    </div>
  );
}

function CustomerList({ params, update }: { params: URLSearchParams; update: Update }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const q = params.get('q') ?? '';
  const type = params.get('type') ?? '';
  const risk = params.get('risk') ?? '';
  const current = page(params);
  const [search, setSearch] = useDebouncedSearch(q, (value) => update({ q: value }));
  const customers = useCustomers({
    q: q || undefined,
    customer_type: type || undefined,
    risk_level: risk || undefined,
    offset: current * CUSTOMER_PAGE_SIZE,
    limit: CUSTOMER_PAGE_SIZE,
  });

  return (
    <div className="space-y-4">
      <Card className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
        <SearchBox id="customer-search" label={t('customers.searchPlaceholder')} value={search} onChange={setSearch} />
        <Field label={t('customers.type')}>
          <Select value={type} onChange={(e) => update({ type: e.target.value })}>
            <option value="">{t('customers.all')}</option>
            {CUSTOMER_TYPE_VALUES.map((value) => (
              <option key={value} value={value}>
                {t(`customerType.${value}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('customers.risk')}>
          <Select value={risk} onChange={(e) => update({ risk: e.target.value })}>
            <option value="">{t('customers.all')}</option>
            {RISK_LEVELS.map((value) => (
              <option key={value} value={value}>
                {t(`customerContext.riskLevels.${value}`)}
              </option>
            ))}
          </Select>
        </Field>
      </Card>

      {customers.isError ? (
        <ErrorState error={customers.error} onRetry={() => void customers.refetch()} />
      ) : !customers.data ? (
        <div className="h-48 animate-pulse rounded-md bg-neutral-soft" aria-hidden />
      ) : customers.data.items.length === 0 ? (
        <Card>
          <EmptyState icon={Users} title={t('customers.empty')} />
        </Card>
      ) : (
        <Card className={cn('overflow-hidden', customers.isPlaceholderData && 'opacity-70')}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-[13px]" aria-label={t('customers.tabCustomers')}>
              <thead>
                <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                  <th scope="col" className="px-5 py-2 font-medium">{t('customers.columns.customer')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('customers.type')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('customers.risk')}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{t('customers.columns.accounts')}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">{t('customers.columns.openAlerts')}</th>
                  <th scope="col" className="px-5 py-2 font-medium">{t('customers.columns.status')}</th>
                </tr>
              </thead>
              <tbody>
                {customers.data.items.map((item) => (
                  <tr key={item.customer_no} className="border-b border-border last:border-0">
                    <td className="px-5 py-2.5">
                      <Link to={`/customers/${encodeURIComponent(item.customer_no)}`} className="font-semibold text-info hover:underline">
                        {item.full_name}
                      </Link>
                      <span className="block font-mono text-xs text-muted">{item.customer_no}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      {item.customer_type ? t(`customerType.${item.customer_type as 'BIREYSEL'}`, { defaultValue: item.customer_type }) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      {item.risk_level ? t(`customerContext.riskLevels.${item.risk_level as 'low'}`, { defaultValue: item.risk_level }) : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(item.account_count, language)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {item.open_alert_count > 0 ? (
                        <Badge tone="danger">{formatNumber(item.open_alert_count, language)}</Badge>
                      ) : (
                        '0'
                      )}
                    </td>
                    <td className="px-5 py-2.5">
                      <Badge tone={item.is_active ? 'success' : 'neutral'}>{item.is_active ? t('customers.active') : t('customers.inactive')}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between px-5 pt-3 text-xs text-muted">
            <span>{t('customers.total', { count: customers.data.total })}</span>
          </div>
          <Pager current={current} total={customers.data.total} onPage={(next) => update({ page: next > 0 ? String(next + 1) : null })} />
        </Card>
      )}
    </div>
  );
}

function AccountList({ params, update }: { params: URLSearchParams; update: Update }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const q = params.get('q') ?? '';
  const currency = params.get('currency') ?? '';
  const current = page(params);
  const [search, setSearch] = useDebouncedSearch(q, (value) => update({ q: value }));
  const [currencyDraft, setCurrencyDraft] = useState(currency);
  const accounts = useAccounts({
    q: q || undefined,
    currency: currency || undefined,
    offset: current * CUSTOMER_PAGE_SIZE,
    limit: CUSTOMER_PAGE_SIZE,
  });
  const commitCurrency = () => {
    const value = currencyDraft.trim().toUpperCase();
    if (value === '' || /^[A-Z]{3}$/.test(value)) update({ currency: value });
  };

  return (
    <div className="space-y-4">
      <Card className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
        <SearchBox id="account-search" label={t('customers.accountSearchPlaceholder')} value={search} onChange={setSearch} />
        <Field label={t('customers.currency')} hint={t('customers.currencyHint')}>
          <Input
            value={currencyDraft}
            maxLength={3}
            className="font-mono uppercase"
            onChange={(e) => setCurrencyDraft(e.target.value)}
            onBlur={commitCurrency}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitCurrency();
            }}
          />
        </Field>
        <p className="self-end text-xs text-muted">{t('customers.accountsLogged')}</p>
      </Card>

      {accounts.isError ? (
        <ErrorState error={accounts.error} onRetry={() => void accounts.refetch()} />
      ) : !accounts.data ? (
        <div className="h-48 animate-pulse rounded-md bg-neutral-soft" aria-hidden />
      ) : accounts.data.items.length === 0 ? (
        <Card>
          <EmptyState icon={Users} title={t('customers.accountsEmpty')} />
        </Card>
      ) : (
        <Card className={cn('overflow-hidden', accounts.isPlaceholderData && 'opacity-70')}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-[13px]" aria-label={t('customers.tabAccounts')}>
              <thead>
                <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
                  <th scope="col" className="px-5 py-2 font-medium">{t('customers.columns.account')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.customer')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('customers.currency')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.accountType')}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t('customers.columns.opened')}</th>
                  <th scope="col" className="px-5 py-2 font-medium">{t('customers.columns.status')}</th>
                </tr>
              </thead>
              <tbody>
                {accounts.data.items.map((item) => (
                  <tr key={item.account_no} className="border-b border-border last:border-0">
                    <td className="px-5 py-2.5 font-mono text-xs">{item.account_no}</td>
                    <td className="px-3 py-2.5">
                      <Link to={`/customers/${encodeURIComponent(item.customer_no)}`} className="font-semibold text-info hover:underline">
                        {item.customer_name}
                      </Link>
                      <span className="block font-mono text-xs text-muted">{item.customer_no}</span>
                    </td>
                    <td className="px-3 py-2.5 font-mono">{item.currency}</td>
                    <td className="px-3 py-2.5">{item.account_type ?? '—'}</td>
                    <td className="px-3 py-2.5">{item.opened_at ? formatDate(item.opened_at, language) : '—'}</td>
                    <td className="px-5 py-2.5">
                      <Badge tone={item.is_active ? 'success' : 'neutral'}>{item.is_active ? t('customers.active') : t('customers.inactive')}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-5 pt-3 text-xs text-muted">{t('customers.accountTotal', { count: accounts.data.total })}</div>
          <Pager current={current} total={accounts.data.total} onPage={(next) => update({ page: next > 0 ? String(next + 1) : null })} />
        </Card>
      )}
    </div>
  );
}
