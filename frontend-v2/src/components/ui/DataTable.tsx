import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface Column<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  align?: 'left' | 'right';
  className?: string;
}

/** Plain, accessible table with a horizontal scroll container for narrow screens. */
export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  label,
  minWidth = 640,
  maxHeight,
}: {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row, index: number) => string;
  label: string;
  minWidth?: number;
  maxHeight?: number;
}) {
  return (
    <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full text-[13px]" style={{ minWidth }} aria-label={label}>
        <thead className={cn(maxHeight && 'sticky top-0 z-10 bg-surface')}>
          <tr className="border-b border-border text-[11px] tracking-wide text-muted uppercase">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn('px-3 py-2 font-medium whitespace-nowrap', column.align === 'right' ? 'text-right' : 'text-left')}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)} className="border-b border-border align-top last:border-0">
              {columns.map((column) => (
                <td key={column.key} className={cn('px-3 py-2', column.align === 'right' && 'text-right tabular-nums', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
