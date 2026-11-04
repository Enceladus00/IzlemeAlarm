/**
 * Port of frontend/components/transaction_flow.py::build_account_flow_svg.
 * This module computes the layout only (pure, testable); FlowDiagram renders it.
 */
export const CANVAS_WIDTH = 900;
export const CARD_WIDTH = 200;
export const CARD_HEIGHT = 72;
export const SOURCE_X = 18;
export const ROUTE_X = 350;
export const RECIPIENT_X = 682;

export type FocusType = 'customer' | 'account';

export interface FlowTransaction {
  sender_account_no: string;
  sender_customer_no: string;
  sender_customer_name: string;
  receiver_account_no: string;
  receiver_customer_no: string;
  receiver_customer_name: string;
  currency: string;
  amount: string;
  alert_linked?: boolean;
}

export interface FlowAccount {
  accountNo: string;
  customerNo: string;
  customerName: string;
  incoming: number;
  outgoing: number;
}

export interface FlowRoute {
  sender: string;
  receiver: string;
  currency: string;
  count: number;
  /** Exact total in minor units (cents). */
  amountCents: bigint;
  flagged: number;
  centerY: number;
  ribbonWidth: number;
  /** Two band paths: source card → route card, route card → recipient card. */
  bands: [string, string];
}

export interface FlowCard {
  account: FlowAccount;
  centerY: number;
  count: number;
  focused: boolean;
}

export interface FlowLayout {
  canvasHeight: number;
  involvedAccounts: number;
  routes: FlowRoute[];
  sources: FlowCard[];
  recipients: FlowCard[];
}

/** Parses a decimal string ("9500.00", "125.5", "-3") into integer cents. */
export function toCents(amount: string | number): bigint {
  const text = String(amount).trim();
  const match = /^(-?)(\d+)(?:\.(\d{1,}))?$/.exec(text);
  if (!match) return BigInt(Math.round(Number(text) * 100));
  const [, sign, whole, fraction = ''] = match;
  const cents = BigInt(whole!) * 100n + BigInt((fraction + '00').slice(0, 2));
  return sign ? -cents : cents;
}

/** Cents back to a plain decimal string with two places ("19300.00"). */
export function centsToDecimal(cents: bigint): string {
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const whole = absolute / 100n;
  const fraction = String(absolute % 100n).padStart(2, '0');
  return `${negative ? '-' : ''}${whole}.${fraction}`;
}

function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function bandPath(startX: number, startY: number, endX: number, endY: number, width: number): string {
  const half = width / 2;
  const curve = (endX - startX) * 0.46;
  const f = (value: number) => value.toFixed(1);
  return (
    `M ${startX} ${f(startY - half)} ` +
    `C ${f(startX + curve)} ${f(startY - half)}, ${f(endX - curve)} ${f(endY - half)}, ${endX} ${f(endY - half)} ` +
    `L ${endX} ${f(endY + half)} ` +
    `C ${f(endX - curve)} ${f(endY + half)}, ${f(startX + curve)} ${f(startY + half)}, ${startX} ${f(startY + half)} Z`
  );
}

export function buildFlowLayout(
  transactions: FlowTransaction[],
  focusType: FocusType,
  focusId: string,
): FlowLayout | null {
  const isFocused = (tx: FlowTransaction) =>
    focusType === 'account'
      ? tx.sender_account_no === focusId || tx.receiver_account_no === focusId
      : tx.sender_customer_no === focusId || tx.receiver_customer_no === focusId;

  const accounts = new Map<string, FlowAccount>();
  const flows = new Map<string, { sender: string; receiver: string; currency: string; count: number; amountCents: bigint; flagged: number }>();

  for (const tx of transactions.filter(isFocused)) {
    const sides: Array<[string, string, string, 'outgoing' | 'incoming']> = [
      [tx.sender_account_no, tx.sender_customer_no, tx.sender_customer_name, 'outgoing'],
      [tx.receiver_account_no, tx.receiver_customer_no, tx.receiver_customer_name, 'incoming'],
    ];
    for (const [accountNo, customerNo, customerName, direction] of sides) {
      let account = accounts.get(accountNo);
      if (!account) {
        account = { accountNo, customerNo, customerName, incoming: 0, outgoing: 0 };
        accounts.set(accountNo, account);
      }
      account[direction] += 1;
    }
    const key = JSON.stringify([tx.sender_account_no, tx.receiver_account_no, tx.currency]);
    let flow = flows.get(key);
    if (!flow) {
      flow = { sender: tx.sender_account_no, receiver: tx.receiver_account_no, currency: tx.currency, count: 0, amountCents: 0n, flagged: 0 };
      flows.set(key, flow);
    }
    flow.count += 1;
    flow.amountCents += toCents(tx.amount);
    flow.flagged += tx.alert_linked ? 1 : 0;
  }

  if (accounts.size === 0) return null;

  const focusedAccounts = new Set(
    [...accounts.values()]
      .filter((account) => (focusType === 'account' ? account.accountNo === focusId : account.customerNo === focusId))
      .map((account) => account.accountNo),
  );
  return layoutFlows(accounts, [...flows.values()], focusedAccounts);
}

/** Server routes (K12) for one focus: accounts are masked labels, names are not sent. */
export interface SummaryRoute {
  sender_account: string;
  receiver_account: string;
  sender_is_focus: boolean;
  receiver_is_focus: boolean;
  currency: string;
  count: number;
  amount: string;
  alert_linked: number;
}

export function buildFlowLayoutFromRoutes(
  routes: SummaryRoute[],
  names: { focus: string; counterparty: string },
): FlowLayout | null {
  if (routes.length === 0) return null;
  const accounts = new Map<string, FlowAccount>();
  const focusedAccounts = new Set<string>();
  const touch = (accountNo: string, isFocus: boolean, direction: 'incoming' | 'outgoing', count: number) => {
    let account = accounts.get(accountNo);
    if (!account) {
      account = { accountNo, customerNo: '', customerName: isFocus ? names.focus : names.counterparty, incoming: 0, outgoing: 0 };
      accounts.set(accountNo, account);
    }
    account[direction] += count;
    if (isFocus) focusedAccounts.add(accountNo);
  };
  const flows = routes.map((route) => {
    touch(route.sender_account, route.sender_is_focus, 'outgoing', route.count);
    touch(route.receiver_account, route.receiver_is_focus, 'incoming', route.count);
    return {
      sender: route.sender_account,
      receiver: route.receiver_account,
      currency: route.currency,
      count: route.count,
      amountCents: toCents(route.amount),
      flagged: route.alert_linked,
    };
  });
  return layoutFlows(accounts, flows, focusedAccounts);
}

function layoutFlows(
  accounts: Map<string, FlowAccount>,
  flows: Array<{ sender: string; receiver: string; currency: string; count: number; amountCents: bigint; flagged: number }>,
  focusedAccounts: Set<string>,
): FlowLayout {
  const visible = [...flows].sort(
    (a, b) =>
      b.count - a.count ||
      compareText(a.sender, b.sender) ||
      compareText(a.receiver, b.receiver) ||
      compareText(a.currency, b.currency),
  );

  // Insertion order matters: Python zips dict keys (first-seen order) with row centers.
  const sourceCounts = new Map<string, number>();
  const recipientCounts = new Map<string, number>();
  for (const flow of visible) {
    sourceCounts.set(flow.sender, (sourceCounts.get(flow.sender) ?? 0) + flow.count);
    recipientCounts.set(flow.receiver, (recipientCounts.get(flow.receiver) ?? 0) + flow.count);
  }

  const routeCount = visible.length;
  const canvasHeight = Math.max(500, 220 + Math.max(routeCount, sourceCounts.size, recipientCounts.size) * 72);
  const rowCenters = (count: number): number[] =>
    count === 1
      ? [canvasHeight / 2]
      : Array.from({ length: count }, (_, index) => 100 + index * ((canvasHeight - 200) / (count - 1)));

  const zipCenters = (counts: Map<string, number>) => {
    const centers = rowCenters(counts.size);
    return new Map([...counts.keys()].map((accountNo, index) => [accountNo, centers[index]!]));
  };
  const sourceY = zipCenters(sourceCounts);
  const recipientY = zipCenters(recipientCounts);
  const routeY = rowCenters(routeCount);
  const maximumCount = Math.max(...visible.map((flow) => flow.count));

  const routes: FlowRoute[] = visible.map((flow, index) => {
    const centerY = routeY[index]!;
    const ribbonWidth = 5 + (15 * flow.count) / maximumCount;
    return {
      ...flow,
      centerY,
      ribbonWidth,
      bands: [
        bandPath(SOURCE_X + CARD_WIDTH, sourceY.get(flow.sender)!, ROUTE_X, centerY, ribbonWidth),
        bandPath(ROUTE_X + CARD_WIDTH, centerY, RECIPIENT_X, recipientY.get(flow.receiver)!, ribbonWidth),
      ],
    };
  });

  const orderByCount = (counts: Map<string, number>) =>
    [...counts.keys()].sort((a, b) => counts.get(b)! - counts.get(a)! || compareText(a, b));
  const toCards = (counts: Map<string, number>, centers: Map<string, number>): FlowCard[] =>
    orderByCount(counts).map((accountNo) => ({
      account: accounts.get(accountNo)!,
      centerY: centers.get(accountNo)!,
      count: counts.get(accountNo)!,
      focused: focusedAccounts.has(accountNo),
    }));

  return {
    canvasHeight,
    involvedAccounts: accounts.size,
    routes,
    sources: toCards(sourceCounts, sourceY),
    recipients: toCards(recipientCounts, recipientY),
  };
}
