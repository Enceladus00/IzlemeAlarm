import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { formatMoney, formatNumber } from '@/utils/format';
import {
  CANVAS_WIDTH,
  CARD_HEIGHT,
  CARD_WIDTH,
  RECIPIENT_X,
  ROUTE_X,
  SOURCE_X,
  centsToDecimal,
  type FlowCard,
  type FlowLayout,
} from './flow';

const ROUTINE = 'var(--series-1)';
const ALERT = 'var(--status-critical)';
const FOCUS = 'var(--accent)';
const NEUTRAL = 'var(--status-neutral)';

function Card({
  x,
  centerY,
  title,
  detail,
  accent,
  tooltip,
}: {
  x: number;
  centerY: number;
  title: string;
  detail: string;
  accent: string;
  tooltip: string;
}) {
  const y = centerY - CARD_HEIGHT / 2;
  return (
    <g>
      <title>{tooltip}</title>
      <rect x={x} y={y} width={CARD_WIDTH} height={CARD_HEIGHT} rx={9} fill="var(--surface)" stroke="var(--border-strong)" strokeWidth={1.2} />
      <rect x={x} y={y} width={4} height={CARD_HEIGHT} rx={2} fill={accent} />
      <text
        x={x + 18}
        y={centerY - 4}
        fill="var(--text)"
        fontSize={16}
        fontWeight={600}
        {...(title.length > 21 ? { textLength: 164, lengthAdjust: 'spacingAndGlyphs' } : {})}
      >
        {title}
      </text>
      <text x={x + 18} y={centerY + 19} fill="var(--text-muted)" fontSize={13}>
        {detail}
      </text>
    </g>
  );
}

/** Renders a FlowLayout (see flow.ts) with theme tokens; text is escaped by React. */
export function FlowDiagram({ layout, focusLabel }: { layout: FlowLayout; focusLabel: string }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const titleId = useId();
  const descId = useId();
  const money = (cents: bigint, currency: string) => formatMoney(centsToDecimal(cents), currency, language);

  const accountCard = (card: FlowCard, x: number, kind: 'source' | 'recipient') => (
    <Card
      key={`${kind}-${card.account.accountNo}`}
      x={x}
      centerY={card.centerY}
      title={card.account.customerName}
      detail={t(kind === 'source' ? 'txAnalysis.flowOutgoing' : 'txAnalysis.flowIncoming', {
        account: card.account.accountNo,
        count: card.count,
      })}
      accent={card.focused ? FOCUS : NEUTRAL}
      tooltip={`${card.account.customerName} · ${card.account.accountNo}`}
    />
  );

  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface-muted">
        <svg
          viewBox={`0 0 ${CANVAS_WIDTH} ${layout.canvasHeight}`}
          className="block w-full min-w-[720px]"
          role="img"
          aria-labelledby={`${titleId} ${descId}`}
          fontFamily="IBM Plex Sans, system-ui, sans-serif"
        >
          <title id={titleId}>{t('txAnalysis.flowSvgTitle', { id: focusLabel })}</title>
          <desc id={descId}>{t('txAnalysis.flowSvgDesc')}</desc>
          {(
            [
              [SOURCE_X, 'sources'],
              [ROUTE_X, 'routes'],
              [RECIPIENT_X, 'recipients'],
            ] as const
          ).map(([x, key]) => (
            <text key={key} x={x} y={42} fill="var(--text-muted)" fontSize={14} letterSpacing={1}>
              {t(`txAnalysis.flowColumns.${key}`)}
            </text>
          ))}
          {layout.routes.map((route) => {
            const flagged = route.flagged > 0;
            const tooltip = t('txAnalysis.flowTooltip', {
              from: route.sender,
              to: route.receiver,
              count: route.count,
              amount: money(route.amountCents, route.currency),
              flagged: route.flagged,
            });
            return route.bands.map((band, index) => (
              <path
                key={`${route.sender}-${route.receiver}-${route.currency}-${index}`}
                className="flow-band"
                d={band}
                fill={flagged ? ALERT : ROUTINE}
                fillOpacity={flagged ? 0.7 : 0.35}
              >
                <title>{tooltip}</title>
              </path>
            ));
          })}
          {layout.sources.map((card) => accountCard(card, SOURCE_X, 'source'))}
          {layout.routes.map((route) => (
            <Card
              key={`route-${route.sender}-${route.receiver}-${route.currency}`}
              x={ROUTE_X}
              centerY={route.centerY}
              title={`${route.sender} → ${route.receiver} · ${route.currency}`}
              detail={t('txAnalysis.flowRouteDetail', {
                count: route.count,
                amount: formatNumber(centsToDecimal(route.amountCents), language, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
              })}
              accent={route.flagged > 0 ? ALERT : ROUTINE}
              tooltip={t('txAnalysis.flowTooltip', {
                from: route.sender,
                to: route.receiver,
                count: route.count,
                amount: money(route.amountCents, route.currency),
                flagged: route.flagged,
              })}
            />
          ))}
          {layout.recipients.map((card) => accountCard(card, RECIPIENT_X, 'recipient'))}
        </svg>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <li className="flex items-center gap-2">
          <span className="h-2 w-4 rounded-sm opacity-60" style={{ background: ROUTINE }} aria-hidden />
          {t('txAnalysis.legendRoutine')}
        </li>
        <li className="flex items-center gap-2">
          <span className="h-2 w-4 rounded-sm" style={{ background: ALERT }} aria-hidden />
          {t('txAnalysis.legendAlert')}
        </li>
        <li className="flex items-center gap-2">
          <span className="h-3 w-1 rounded-sm" style={{ background: FOCUS }} aria-hidden />
          {t('txAnalysis.legendFocus')}
        </li>
      </ul>
    </div>
  );
}

/** Table alternative to the diagram (exact values, screen readers). */
export function FlowRouteTable({ layout }: { layout: FlowLayout }) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-[13px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
            <th scope="col" className="px-3 py-2 font-medium">{t('txAnalysis.routeTable.route')}</th>
            <th scope="col" className="px-3 py-2 font-medium">{t('txAnalysis.routeTable.currency')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('txAnalysis.routeTable.count')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('txAnalysis.routeTable.amount')}</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">{t('txAnalysis.routeTable.flagged')}</th>
          </tr>
        </thead>
        <tbody>
          {layout.routes.map((route) => (
            <tr key={`${route.sender}-${route.receiver}-${route.currency}`} className="border-b border-border last:border-0">
              <td className="px-3 py-2 font-mono text-xs">
                {route.sender} → {route.receiver}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{route.currency}</td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(route.count, language)}</td>
              <td className="px-3 py-2 text-right font-mono tabular-nums">
                {formatMoney(centsToDecimal(route.amountCents), route.currency, language)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{formatNumber(route.flagged, language)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
