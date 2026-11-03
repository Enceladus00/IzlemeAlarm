import { Table2, TrendingUp } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';

/**
 * Lets any chart be read as a plain table (accessibility and exact values).
 * `chart` receives the toggle button so it can place it in its own toolbar.
 */
export function ChartTableToggle({
  chart,
  table,
}: {
  chart: (toggle: ReactNode) => ReactNode;
  table: ReactNode;
}) {
  const { t } = useTranslation();
  const [showTable, setShowTable] = useState(false);
  const toggle = (
    <Button size="sm" variant="ghost" aria-pressed={showTable} onClick={() => setShowTable((value) => !value)}>
      {showTable ? <TrendingUp className="size-3.5" aria-hidden /> : <Table2 className="size-3.5" aria-hidden />}
      {showTable ? t('charts.showChart') : t('charts.showTable')}
    </Button>
  );
  if (!showTable) return <>{chart(toggle)}</>;
  return (
    <div>
      <div className="mb-3 flex justify-end">{toggle}</div>
      {table}
    </div>
  );
}
