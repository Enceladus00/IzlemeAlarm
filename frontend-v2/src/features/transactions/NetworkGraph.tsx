import { useQueries } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiRequest, type QueryValue } from '@/api/client';
import { transactionSummarySchema, type TransactionSummary } from '@/api/schemas/transactions';
import { formatMoney } from '@/utils/format';
import { buildCounterpartyFlow, type CounterpartyRow } from './counterparties';
import { centsToDecimal } from './flow';
import { txKeys } from './api';

const WIDTH = 1000;
const HEIGHT = 720;
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 };
const RING = 230;
const HOP = 150;
const FIRST_HOP_LIMIT = 24;
const NEXT_HOP_LIMIT = 8;
const IN = 'var(--series-1)';
const OUT = 'var(--series-2)';
const ALERT = 'var(--status-critical)';
const FOCUS_ID = '__focus__';

interface Node {
  id: string;
  label: string;
  account: string;
  x: number;
  y: number;
  angle: number;
  depth: number;
  cents: bigint;
  rules: string[];
  flagged: boolean;
}

interface Edge {
  from: string;
  to: string;
  cents: bigint;
  count: number;
  flaggedShare: number;
  rules: string[];
}

const toNumber = (cents: bigint) => Number(cents / 100n);

/**
 * Node-link view of the focus's neighbourhood. The focus is in the centre,
 * its biggest counterparties on a ring; clicking a counterparty loads its own
 * counterparties (through the signed `account_ref`) and places them outward.
 * Edges point in the direction money moved; thickness is amount, red marks
 * alert-linked transfers. Accounts already on the graph are reused, so a
 * cycle or a shared middleman shows up as an edge closing back.
 */
export function NetworkGraph({
  summary,
  focusName,
  filters,
}: {
  summary: TransactionSummary;
  focusName: string;
  filters: Record<string, QueryValue>;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const base = useMemo(() => buildCounterpartyFlow(summary.routes), [summary.routes]);
  const [currency, setCurrency] = useState<string | null>(null);
  const active = currency && base.currencies.includes(currency) ? currency : (base.currencies[0] ?? '');
  const [expanded, setExpanded] = useState<string[]>([]);
  const [hover, setHover] = useState<string | null>(null);

  const expansions = useQueries({
    queries: expanded.map((ref) => {
      const query = { ...filters, account_ref: ref };
      return {
        queryKey: txKeys.summary(query),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          apiRequest('/transactions/summary', { query, schema: transactionSummarySchema, signal }),
      };
    }),
  });

  const graph = useMemo(() => {
    const nodes = new Map<string, Node>();
    const edges = new Map<string, Edge>();
    const focusRefs = new Set(base.focusRefs);
    const idOf = (ref: string) => (focusRefs.has(ref) ? FOCUS_ID : ref);
    nodes.set(FOCUS_ID, { id: FOCUS_ID, label: focusName, account: '', ...CENTER, angle: 0, depth: 0, cents: 0n, rules: [], flagged: false });

    const addEdges = (from: string, row: CounterpartyRow, otherId: string) => {
      const link = (a: string, b: string, cents: bigint, count: number) => {
        if (cents <= 0n) return;
        const key = `${a}>${b}`;
        const existing = edges.get(key);
        if (existing) return; // the same pair seen from both ends: keep the first
        edges.set(key, { from: a, to: b, cents, count, flaggedShare: row.flaggedShare, rules: row.rules });
      };
      link(otherId, from, row.inCents, row.inCount);
      link(from, otherId, row.outCents, row.outCount);
    };

    const first = base.rows.filter((row) => row.currency === active).slice(0, FIRST_HOP_LIMIT);
    first.forEach((row, index) => {
      const angle = (2 * Math.PI * index) / Math.max(first.length, 1) - Math.PI / 2;
      const id = row.ref || row.account;
      nodes.set(id, {
        id,
        label: row.label || row.account,
        account: row.account,
        x: CENTER.x + RING * Math.cos(angle),
        y: CENTER.y + RING * Math.sin(angle),
        angle,
        depth: 1,
        cents: row.inCents + row.outCents,
        rules: row.rules,
        flagged: row.flaggedShare > 0,
      });
      addEdges(FOCUS_ID, row, id);
    });

    expanded.forEach((ref, index) => {
      const data = expansions[index]?.data;
      const parent = nodes.get(ref);
      if (!data || !parent) return;
      const next = buildCounterpartyFlow(data.routes)
        .rows.filter((row) => row.currency === active)
        .slice(0, NEXT_HOP_LIMIT);
      const fresh = next.filter((row) => !nodes.has(idOf(row.ref || row.account)));
      fresh.forEach((row, position) => {
        const spread = Math.min(Math.PI / 2.2, 0.32 * fresh.length);
        const angle = parent.angle + (fresh.length > 1 ? -spread / 2 + (spread * position) / (fresh.length - 1) : 0);
        const id = row.ref || row.account;
        nodes.set(id, {
          id,
          label: row.label || row.account,
          account: row.account,
          x: parent.x + HOP * Math.cos(angle),
          y: parent.y + HOP * Math.sin(angle),
          angle,
          depth: parent.depth + 1,
          cents: row.inCents + row.outCents,
          rules: row.rules,
          flagged: row.flaggedShare > 0,
        });
      });
      for (const row of next) addEdges(ref, row, idOf(row.ref || row.account));
    });

    const list = [...nodes.values()];
    const edgeList = [...edges.values()].filter((edge) => nodes.has(edge.from) && nodes.has(edge.to));
    const maxEdge = edgeList.reduce((max, edge) => (edge.cents > max ? edge.cents : max), 1n);
    const maxNode = list.reduce((max, node) => (node.cents > max ? node.cents : max), 1n);
    // Fit everything into the viewBox (expanded hops can leave the ring).
    const xs = list.map((node) => node.x);
    const ys = list.map((node) => node.y);
    const pad = 70;
    const box = {
      x: Math.min(0, Math.min(...xs) - pad),
      y: Math.min(0, Math.min(...ys) - pad),
      w: Math.max(WIDTH, Math.max(...xs) + pad) - Math.min(0, Math.min(...xs) - pad),
      h: Math.max(HEIGHT, Math.max(...ys) + pad) - Math.min(0, Math.min(...ys) - pad),
    };
    return { nodes: list, edges: edgeList, maxEdge, maxNode, box };
  }, [base, active, expanded, expansions, focusName]);

  const money = (cents: bigint) => formatMoney(centsToDecimal(cents), active, language);
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const radius = (node: Node) =>
    node.id === FOCUS_ID ? 30 : 9 + 17 * Math.sqrt(toNumber(node.cents) / Math.max(1, toNumber(graph.maxNode)));
  const toggle = (id: string) =>
    setExpanded((current) => (current.includes(id) ? current.filter((ref) => ref !== id) : [...current, id]));
  const loading = expansions.some((query) => query.isFetching);
  const highlighted = (edge: Edge) => hover !== null && (edge.from === hover || edge.to === hover);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>{t('txAnalysis.netHint')}</span>
        <span className="flex items-center gap-2">
          {loading && <span role="status">{t('txAnalysis.netLoading')}</span>}
          {expanded.length > 0 && (
            <button type="button" className="font-medium text-accent hover:underline" onClick={() => setExpanded([])}>
              {t('txAnalysis.netCollapse')}
            </button>
          )}
          {base.currencies.length > 1 &&
            base.currencies.map((code) => (
              <button
                key={code}
                type="button"
                aria-pressed={code === active}
                onClick={() => {
                  setCurrency(code);
                  setExpanded([]);
                }}
                className={`rounded-full border px-2 py-0.5 ${code === active ? 'border-accent bg-accent/10 text-fg' : 'border-border'}`}
              >
                {code}
              </button>
            ))}
        </span>
      </div>
      <div className="overflow-hidden rounded-lg border border-border bg-surface-muted">
        <svg
          viewBox={`${graph.box.x} ${graph.box.y} ${graph.box.w} ${graph.box.h}`}
          className="block h-[560px] w-full"
          role="img"
          aria-label={t('txAnalysis.netAria', { name: focusName, count: graph.nodes.length - 1 })}
          fontFamily="IBM Plex Sans, system-ui, sans-serif"
        >
          <defs>
            {(['in', 'out', 'alert'] as const).map((kind) => (
              <marker key={kind} id={`net-arrow-${kind}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill={kind === 'alert' ? ALERT : kind === 'in' ? IN : OUT} />
              </marker>
            ))}
          </defs>
          {graph.edges.map((edge) => {
            const a = byId.get(edge.from)!;
            const b = byId.get(edge.to)!;
            const towardFocus = edge.to === FOCUS_ID;
            const kind = edge.flaggedShare > 0 ? 'alert' : towardFocus ? 'in' : 'out';
            const color = kind === 'alert' ? ALERT : kind === 'in' ? IN : OUT;
            // Curve both directions of a pair apart so they do not overlap.
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const length = Math.hypot(dx, dy) || 1;
            const bend = 0.12 * length;
            const mx = (a.x + b.x) / 2 - (dy / length) * bend;
            const my = (a.y + b.y) / 2 + (dx / length) * bend;
            const end = radius(b) + 3;
            const ex = b.x - ((b.x - mx) / Math.hypot(b.x - mx, b.y - my)) * end;
            const ey = b.y - ((b.y - my) / Math.hypot(b.x - mx, b.y - my)) * end;
            const width = 1.2 + 9 * Math.sqrt(toNumber(edge.cents) / Math.max(1, toNumber(graph.maxEdge)));
            const dim = hover !== null && !highlighted(edge);
            return (
              <path
                key={`${edge.from}>${edge.to}`}
                d={`M ${a.x} ${a.y} Q ${mx} ${my} ${ex} ${ey}`}
                fill="none"
                stroke={color}
                strokeWidth={width}
                strokeOpacity={dim ? 0.12 : 0.65}
                markerEnd={`url(#net-arrow-${kind})`}
              >
                <title>
                  {t('txAnalysis.netEdgeTooltip', {
                    from: a.label,
                    to: b.label,
                    amount: money(edge.cents),
                    count: edge.count,
                    share: Math.round(edge.flaggedShare * 100),
                    rules: edge.rules.join(', ') || '—',
                  })}
                </title>
              </path>
            );
          })}
          {graph.nodes.map((node) => {
            const r = radius(node);
            const isFocus = node.id === FOCUS_ID;
            const isExpanded = expanded.includes(node.id);
            const canExpand = !isFocus && node.id.includes('.');
            return (
              <g
                key={node.id}
                transform={`translate(${node.x} ${node.y})`}
                className={canExpand ? 'cursor-pointer' : undefined}
                onClick={canExpand ? () => toggle(node.id) : undefined}
                onMouseEnter={() => setHover(node.id)}
                onMouseLeave={() => setHover(null)}
                role={canExpand ? 'button' : undefined}
                tabIndex={canExpand ? 0 : undefined}
                aria-label={canExpand ? t('txAnalysis.netExpand', { name: node.label }) : undefined}
                onKeyDown={canExpand ? (event) => (event.key === 'Enter' || event.key === ' ') && toggle(node.id) : undefined}
              >
                <title>
                  {isFocus ? focusName : t('txAnalysis.netNodeTooltip', { name: node.label, account: node.account, amount: money(node.cents) })}
                </title>
                <circle
                  r={r}
                  fill={isFocus ? 'var(--accent)' : 'var(--surface)'}
                  stroke={node.flagged ? ALERT : isFocus ? 'var(--accent)' : 'var(--border-strong)'}
                  strokeWidth={node.flagged ? 3 : 1.5}
                  strokeDasharray={isExpanded ? '4 3' : undefined}
                />
                {canExpand && !isExpanded && (
                  <text textAnchor="middle" dy="0.35em" fontSize={r > 14 ? 14 : 11} fill="var(--text-muted)">
                    +
                  </text>
                )}
                <text y={r + 15} textAnchor="middle" fontSize={13} fontWeight={isFocus ? 700 : 500} fill="var(--text)">
                  {node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}
                </text>
                {!isFocus && node.rules.length > 0 && (
                  <text y={r + 30} textAnchor="middle" fontSize={11} fill={ALERT} fontFamily="IBM Plex Mono, monospace">
                    {node.rules.join(' ')}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <li className="flex items-center gap-2">
          <span className="h-1 w-5 rounded" style={{ background: IN }} aria-hidden />
          {t('txAnalysis.netLegendIn')}
        </li>
        <li className="flex items-center gap-2">
          <span className="h-1 w-5 rounded" style={{ background: OUT }} aria-hidden />
          {t('txAnalysis.netLegendOut')}
        </li>
        <li className="flex items-center gap-2">
          <span className="h-1 w-5 rounded" style={{ background: ALERT }} aria-hidden />
          {t('txAnalysis.netLegendAlert')}
        </li>
        <li>{t('txAnalysis.netLegendSize')}</li>
      </ul>
    </div>
  );
}
