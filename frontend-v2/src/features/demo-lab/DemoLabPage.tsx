import { FlaskConical } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { DemoRun, DemoScenario, DemoStatus } from '@/api/schemas/demo';
import { useAuth } from '@/auth/auth-context';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { DataTable } from '@/components/ui/DataTable';
import { ErrorState } from '@/components/ui/ErrorState';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageSpinner } from '@/components/ui/Spinner';
import { StatCard } from '@/components/ui/StatCard';
import { Tabs } from '@/components/ui/Tabs';
import { formatDate, formatDateTime, formatMoney, formatNumber } from '@/utils/format';
import { useDemoStatus, useLastDemoRun, useSeedDemo } from './api';

type TabValue = 'coverage' | 'customers' | 'accounts' | 'transactions';

export default function DemoLabPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { can } = useAuth();
  const status = useDemoStatus();
  const lastRun = useLastDemoRun().data ?? null;
  const seed = useSeedDemo();
  const [useSaved, setUseSaved] = useState(false);
  const [tab, setTab] = useState<TabValue>('coverage');

  if (status.isPending) return <PageSpinner label={t('common.loading')} />;
  if (status.isError) {
    return (
      <>
        <PageHeader breadcrumb={t('demo.breadcrumb')} title={t('nav.demoLab')} description={t('demo.description')} />
        <ErrorState error={status.error} onRetry={() => void status.refetch()} />
      </>
    );
  }

  const inventory: DemoStatus = status.data;
  const scenarios = lastRun?.scenarios ?? inventory.scenarios;

  return (
    <>
      <PageHeader breadcrumb={t('demo.breadcrumb')} title={t('nav.demoLab')} description={t('demo.description')} />

      <div className="space-y-4">
        {!inventory.seed_enabled ? (
          <InlineAlert tone="warning" title={t('demo.disabledTitle')}>
            {t('demo.disabledBody')}
          </InlineAlert>
        ) : !can('upload:create') ? (
          <InlineAlert tone="info">{t('demo.cannotSeed')}</InlineAlert>
        ) : (
          <Card>
            <CardHeader title={t('demo.seedTitle')} description={t('demo.seedBody')} />
            <form
              className="space-y-4 p-5"
              onSubmit={(event) => {
                event.preventDefault();
                seed.mutate(useSaved);
              }}
            >
              <label className="flex max-w-2xl items-start gap-3 text-[13px]">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--accent)]"
                  checked={useSaved}
                  onChange={(event) => setUseSaved(event.target.checked)}
                  aria-describedby="demo-use-saved-hint"
                />
                <span>
                  <span className="font-medium">{t('demo.useSaved')}</span>
                  <span id="demo-use-saved-hint" className="mt-0.5 block text-xs text-muted">
                    {t('demo.useSavedHint')}
                  </span>
                </span>
              </label>
              <Button type="submit" variant="primary" loading={seed.isPending}>
                {!seed.isPending && <FlaskConical className="size-4" aria-hidden />}
                {seed.isPending ? t('demo.seeding') : t('demo.seed')}
              </Button>
              {seed.isError && <ErrorState error={seed.error} />}
              {seed.isSuccess && (
                <InlineAlert tone="success" live>
                  {t('demo.seedDone', {
                    customers: seed.data.customers,
                    accounts: seed.data.accounts,
                    transactions: seed.data.transactions,
                  })}
                </InlineAlert>
              )}
            </form>
          </Card>
        )}

        {!inventory.seeded ? (
          <InlineAlert tone="info">{t('demo.notSeeded')}</InlineAlert>
        ) : (
          <>
            {!inventory.fixture_ready && <InlineAlert tone="warning">{t('demo.partialFixture')}</InlineAlert>}
            <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
              <StatCard label={t('demo.metricCustomers')} value={formatNumber(inventory.customers, language)} />
              <StatCard label={t('demo.metricAccounts')} value={formatNumber(inventory.accounts, language)} />
              <StatCard label={t('demo.metricTransactions')} value={formatNumber(inventory.transactions, language)} />
              <StatCard label={t('demo.metricRules')} value={formatNumber(inventory.scenarios.length, language)} />
            </div>
            <p className="text-xs text-muted">
              {lastRun
                ? t('demo.lastRun', {
                    id: lastRun.run_id,
                    mode: lastRun.parameter_mode in { demo_provisional: 1, saved_active_rules: 1 }
                      ? t(`demo.modes.${lastRun.parameter_mode as 'demo_provisional'}`)
                      : lastRun.parameter_mode,
                    alerts: lastRun.created_alerts,
                  })
                : t('demo.notRunYet')}
            </p>

            <Card className="p-5">
              <Tabs<TabValue>
                label={t('nav.demoLab')}
                value={tab}
                onChange={setTab}
                items={[
                  { value: 'coverage', label: t('demo.tabs.coverage'), content: <Coverage scenarios={scenarios} run={lastRun} /> },
                  { value: 'customers', label: t('demo.tabs.customers'), content: <CustomersTable inventory={inventory} /> },
                  { value: 'accounts', label: t('demo.tabs.accounts'), content: <AccountsTable inventory={inventory} /> },
                  { value: 'transactions', label: t('demo.tabs.transactions'), content: <TransactionsTable inventory={inventory} /> },
                ]}
              />
            </Card>
          </>
        )}
      </div>
    </>
  );
}

function YesNo({ value }: { value: boolean | null | undefined }) {
  const { t } = useTranslation();
  if (value === null || value === undefined) return <span className="text-muted">—</span>;
  return <Badge tone={value ? 'success' : 'danger'}>{value ? t('demo.coverage.yes') : t('demo.coverage.no')}</Badge>;
}

function Coverage({ scenarios, run }: { scenarios: DemoScenario[]; run: DemoRun | null }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const summary = run ? Object.entries(run.rule_summary) : [];
  return (
    <div className="space-y-6">
      <DataTable
        label={t('demo.tabs.coverage')}
        rows={scenarios}
        rowKey={(row) => `${row.rule_code}-${row.customer_no}`}
        minWidth={1100}
        columns={[
          { key: 'rule', header: t('demo.coverage.rule'), render: (row) => <span className="font-mono font-semibold">{row.rule_code}</span> },
          { key: 'customer', header: t('demo.coverage.customer'), render: (row) => <span className="font-mono text-xs whitespace-nowrap">{row.customer_no}</span> },
          { key: 'account', header: t('demo.coverage.account'), render: (row) => <span className="font-mono text-xs whitespace-nowrap">{row.account_no}</span> },
          { key: 'scenario', header: t('demo.coverage.scenario'), className: 'min-w-64', render: (row) => row.intent },
          { key: 'expected', header: t('demo.coverage.expected'), render: (row) => <span className="font-mono text-xs">{row.expected_signal}</span> },
          { key: 'result', header: t('demo.coverage.result'), render: (row) => <span className="font-mono text-xs">{row.result_status ?? t('demo.coverage.notRun')}</span> },
          {
            key: 'score',
            header: t('demo.coverage.score'),
            align: 'right',
            render: (row) => (row.score ? formatNumber(row.score, language, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '—'),
          },
          { key: 'evidence', header: t('demo.coverage.evidence'), align: 'right', render: (row) => formatNumber(row.evidence_transactions ?? 0, language) },
          {
            key: 'evidenceIds',
            header: t('demo.coverage.evidenceIds'),
            render: (row) => <span className="font-mono text-xs break-all">{(row.evidence_transaction_numbers ?? []).join(', ') || '—'}</span>,
          },
          { key: 'observed', header: t('demo.coverage.observed'), render: (row) => <YesNo value={row.observed_signal} /> },
          { key: 'passed', header: t('demo.coverage.passed'), render: (row) => <YesNo value={row.passed} /> },
        ]}
      />
      {summary.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">{t('demo.executionTitle')}</h3>
          <DataTable
            label={t('demo.executionTitle')}
            rows={summary}
            rowKey={([code]) => code}
            minWidth={560}
            columns={[
              { key: 'rule', header: t('demo.execution.rule'), render: ([code]) => <span className="font-mono font-semibold">{code}</span> },
              { key: 'evaluated', header: t('demo.execution.evaluated'), align: 'right', render: ([, s]) => formatNumber(s.evaluated, language) },
              { key: 'signals', header: t('demo.execution.signals'), align: 'right', render: ([, s]) => formatNumber(s.alerts, language) },
              {
                key: 'skipped',
                header: t('demo.execution.skipped'),
                align: 'right',
                render: ([, s]) => formatNumber(Object.values(s.skipped_unset).reduce((sum, n) => sum + n, 0), language),
              },
              {
                key: 'runtime',
                header: t('demo.execution.runtime'),
                align: 'right',
                render: ([, s]) => (s.elapsed_ms === undefined ? '—' : formatNumber(s.elapsed_ms, language, { maximumFractionDigits: 1 })),
              },
            ]}
          />
        </div>
      )}
      <p className="text-xs text-muted">{t('demo.signalNote')}</p>
    </div>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  const { t } = useTranslation();
  return <Badge tone={active ? 'success' : 'neutral'}>{active ? t('demo.coverage.yes') : t('demo.coverage.no')}</Badge>;
}

function CustomersTable({ inventory }: { inventory: DemoStatus }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  return (
    <DataTable
      label={t('demo.tabs.customers')}
      rows={inventory.customer_rows}
      rowKey={(row) => row.customer_no}
      maxHeight={520}
      columns={[
        { key: 'no', header: t('demo.columns.customerNo'), render: (row) => <span className="font-mono text-xs whitespace-nowrap">{row.customer_no}</span> },
        { key: 'name', header: t('demo.columns.name'), render: (row) => row.full_name },
        { key: 'type', header: t('demo.columns.type'), render: (row) => row.customer_type ?? '—' },
        {
          key: 'income',
          header: t('demo.columns.income'),
          align: 'right',
          render: (row) => (row.monthly_income ? formatNumber(row.monthly_income, language, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'),
        },
        { key: 'accounts', header: t('demo.columns.accountCount'), align: 'right', render: (row) => formatNumber(row.account_count, language) },
        { key: 'active', header: t('demo.columns.active'), render: (row) => <ActiveBadge active={row.is_active} /> },
      ]}
    />
  );
}

function AccountsTable({ inventory }: { inventory: DemoStatus }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  return (
    <DataTable
      label={t('demo.tabs.accounts')}
      rows={inventory.account_rows}
      rowKey={(row) => row.account_no}
      maxHeight={520}
      columns={[
        { key: 'no', header: t('demo.columns.accountNo'), render: (row) => <span className="font-mono text-xs whitespace-nowrap">{row.account_no}</span> },
        { key: 'customer', header: t('demo.columns.customerNo'), render: (row) => <span className="font-mono text-xs whitespace-nowrap">{row.customer_no}</span> },
        { key: 'currency', header: t('demo.columns.currency'), render: (row) => row.currency },
        { key: 'type', header: t('demo.columns.accountType'), render: (row) => row.account_type ?? '—' },
        { key: 'opened', header: t('demo.columns.openedAt'), render: (row) => formatDate(row.opened_at, language) },
        { key: 'active', header: t('demo.columns.active'), render: (row) => <ActiveBadge active={row.is_active} /> },
      ]}
    />
  );
}

function TransactionsTable({ inventory }: { inventory: DemoStatus }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  return (
    <DataTable
      label={t('demo.tabs.transactions')}
      rows={inventory.transaction_rows}
      rowKey={(row) => row.transaction_no}
      maxHeight={520}
      minWidth={900}
      columns={[
        { key: 'no', header: t('demo.columns.transactionNo'), render: (row) => <span className="font-mono text-xs whitespace-nowrap">{row.transaction_no}</span> },
        {
          key: 'sender',
          header: t('demo.columns.sender'),
          render: (row) => (
            <span className="font-mono text-xs">
              {row.sender_customer_no} · {row.sender_account_no}
            </span>
          ),
        },
        {
          key: 'receiver',
          header: t('demo.columns.receiver'),
          render: (row) => (
            <span className="font-mono text-xs">
              {row.receiver_customer_no} · {row.receiver_account_no}
            </span>
          ),
        },
        { key: 'amount', header: t('demo.columns.amount'), align: 'right', render: (row) => <span className="font-mono">{formatMoney(row.amount, row.currency, language)}</span> },
        { key: 'time', header: t('demo.columns.time'), render: (row) => formatDateTime(row.tx_time, language) },
        { key: 'channel', header: t('demo.columns.channel'), render: (row) => row.channel },
        { key: 'active', header: t('demo.columns.active'), render: (row) => <ActiveBadge active={row.is_active} /> },
      ]}
    />
  );
}
