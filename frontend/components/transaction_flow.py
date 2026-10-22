from decimal import Decimal
from html import escape
from typing import Any, Literal


CANVAS_WIDTH = 900
CARD_WIDTH = 200
CARD_HEIGHT = 72
SOURCE_X = 18
ROUTE_X = 350
RECIPIENT_X = 682


def build_account_flow_svg(
    transactions: list[dict[str, Any]],
    focus_type: Literal["customer", "account"],
    focus_id: str,
) -> tuple[str | None, int, int]:
    if focus_type not in {"customer", "account"}:
        raise ValueError(f"Unsupported account-flow focus type: {focus_type}")

    def is_focused(transaction: dict[str, Any]) -> bool:
        if focus_type == "account":
            return (
                transaction["sender_account_no"] == focus_id
                or transaction["receiver_account_no"] == focus_id
            )
        return (
            transaction["sender_customer_no"] == focus_id
            or transaction["receiver_customer_no"] == focus_id
        )

    focused_transactions = [
        transaction for transaction in transactions if is_focused(transaction)
    ]
    accounts: dict[str, dict[str, Any]] = {}
    flows: dict[tuple[str, str, str], dict[str, Any]] = {}

    for transaction in focused_transactions:
        sender = transaction["sender_account_no"]
        receiver = transaction["receiver_account_no"]
        currency = transaction["currency"]
        amount = Decimal(str(transaction["amount"]))
        flagged = bool(transaction["alert_linked"])

        for account_no, customer_no, customer_name, direction in (
            (
                sender,
                transaction["sender_customer_no"],
                transaction["sender_customer_name"],
                "outgoing",
            ),
            (
                receiver,
                transaction["receiver_customer_no"],
                transaction["receiver_customer_name"],
                "incoming",
            ),
        ):
            account = accounts.setdefault(
                account_no,
                {
                    "account_no": account_no,
                    "customer_no": customer_no,
                    "customer_name": customer_name,
                    "incoming": 0,
                    "outgoing": 0,
                },
            )
            account[direction] += 1

        flow = flows.setdefault(
            (sender, receiver, currency),
            {"count": 0, "amount": Decimal(0), "flagged": 0},
        )
        flow["count"] += 1
        flow["amount"] += amount
        flow["flagged"] += int(flagged)

    if not accounts:
        return None, 0, 0

    involved_accounts = sorted(
        accounts.values(),
        key=lambda account: (
            -(account["incoming"] + account["outgoing"]),
            account["account_no"],
        ),
    )
    visible_flows = list(flows.items())
    visible_flows.sort(
        key=lambda item: (
            -item[1]["count"],
            item[0][0],
            item[0][1],
            item[0][2],
        )
    )
    if not visible_flows:
        return None, len(involved_accounts), 0

    account_by_no = {account["account_no"]: account for account in involved_accounts}
    focused_accounts = {
        account["account_no"]
        for account in involved_accounts
        if (
            account["account_no"] == focus_id
            if focus_type == "account"
            else account["customer_no"] == focus_id
        )
    }
    source_counts: dict[str, int] = {}
    recipient_counts: dict[str, int] = {}
    for (sender, receiver, _currency), flow in visible_flows:
        source_counts[sender] = source_counts.get(sender, 0) + flow["count"]
        recipient_counts[receiver] = recipient_counts.get(receiver, 0) + flow["count"]

    route_count = len(visible_flows)
    canvas_height = max(
        500,
        220 + max(route_count, len(source_counts), len(recipient_counts)) * 72,
    )

    def row_centers(count: int) -> list[float]:
        if count == 1:
            return [canvas_height / 2]
        top = 100
        step = (canvas_height - 200) / (count - 1)
        return [top + index * step for index in range(count)]

    def card(
        x: int,
        center_y: float,
        title: str,
        detail: str,
        accent: str,
        tooltip: str,
    ) -> str:
        y = center_y - CARD_HEIGHT / 2
        title_layout = (
            ' textLength="164" lengthAdjust="spacingAndGlyphs"'
            if len(title) > 21
            else ""
        )
        return (
            f'<g><title>{escape(tooltip)}</title>'
            f'<rect x="{x}" y="{y:.1f}" width="{CARD_WIDTH}" '
            f'height="{CARD_HEIGHT}" rx="9" fill="#1B2431" '
            f'stroke="#394355" stroke-width="1.2"/>'
            f'<rect x="{x}" y="{y:.1f}" width="4" height="{CARD_HEIGHT}" '
            f'rx="2" fill="{accent}"/>'
            f'<text x="{x + 18}" y="{center_y - 4:.1f}" fill="#F2F4F8" '
            f'font-size="16" font-weight="600" font-family="sans-serif"'
            f'{title_layout}>'
            f'{escape(title)}</text>'
            f'<text x="{x + 18}" y="{center_y + 19:.1f}" fill="#AAB4C3" '
            f'font-size="13" font-family="sans-serif">{escape(detail)}</text>'
            "</g>"
        )

    source_accounts = [
        account_by_no[account_no]
        for account_no in sorted(
            source_counts,
            key=lambda account_no: (-source_counts[account_no], account_no),
        )
    ]
    recipient_accounts = [
        account_by_no[account_no]
        for account_no in sorted(
            recipient_counts,
            key=lambda account_no: (-recipient_counts[account_no], account_no),
        )
    ]
    source_y = dict(zip(source_counts, row_centers(len(source_accounts))))
    recipient_y = dict(zip(recipient_counts, row_centers(len(recipient_accounts))))
    route_y = row_centers(route_count)
    maximum_count = max(flow["count"] for _, flow in visible_flows)

    ribbons: list[str] = []
    route_cards: list[str] = []
    for index, ((sender, receiver, currency), flow) in enumerate(visible_flows):
        route_center = route_y[index]
        ribbon_width = 5 + 15 * flow["count"] / maximum_count
        color = "#F16C7A" if flow["flagged"] else "#F4A62A"
        opacity = 0.72 if flow["flagged"] else 0.45
        for start_x, start_y, end_x, end_y in (
            (SOURCE_X + CARD_WIDTH, source_y[sender], ROUTE_X, route_center),
            (ROUTE_X + CARD_WIDTH, route_center, RECIPIENT_X, recipient_y[receiver]),
        ):
            half_width = ribbon_width / 2
            curve = (end_x - start_x) * 0.46
            path = (
                f"M {start_x} {start_y - half_width:.1f} "
                f"C {start_x + curve:.1f} {start_y - half_width:.1f}, "
                f"{end_x - curve:.1f} {end_y - half_width:.1f}, "
                f"{end_x} {end_y - half_width:.1f} "
                f"L {end_x} {end_y + half_width:.1f} "
                f"C {end_x - curve:.1f} {end_y + half_width:.1f}, "
                f"{start_x + curve:.1f} {start_y + half_width:.1f}, "
                f"{start_x} {start_y + half_width:.1f} Z"
            )
            tooltip = (
                f"{sender} to {receiver}: {flow['count']} transfers, "
                f"{flow['amount']:,.2f} {currency}; "
                f"{flow['flagged']} alert-linked"
            )
            ribbons.append(
                f'<path class="flow-band" d="{path}" fill="{color}" '
                f'fill-opacity="{opacity}"><title>{escape(tooltip)}</title></path>'
            )
        route_cards.append(
            card(
                ROUTE_X,
                route_center,
                f"{sender} → {receiver} · {currency}",
                f"{flow['count']} transfers · {flow['amount']:,.2f}",
                color,
                (
                    f"{sender} to {receiver}, {flow['count']} transfers, "
                    f"{flow['amount']:,.2f} {currency}, "
                    f"{flow['flagged']} alert-linked"
                ),
            )
        )

    source_cards = [
        card(
            SOURCE_X,
            source_y[account["account_no"]],
            account["customer_name"],
            f"{account['account_no']} · {source_counts[account['account_no']]} outgoing",
            "#F4A62A" if account["account_no"] in focused_accounts else "#8B7CFF",
            f"{account['customer_name']}, account {account['account_no']}, "
            f"{source_counts[account['account_no']]} outgoing transfers",
        )
        for account in source_accounts
    ]
    recipient_cards = [
        card(
            RECIPIENT_X,
            recipient_y[account["account_no"]],
            account["customer_name"],
            (
                f"{account['account_no']} · "
                f"{recipient_counts[account['account_no']]} incoming"
            ),
            "#F4A62A" if account["account_no"] in focused_accounts else "#29C7B8",
            f"{account['customer_name']}, account {account['account_no']}, "
            f"{recipient_counts[account['account_no']]} incoming transfers",
        )
        for account in recipient_accounts
    ]

    legend_y = canvas_height - 34
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="flow-title flow-description" '
        f'viewBox="0 0 {CANVAS_WIDTH} {canvas_height}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet">'
        f'<title id="flow-title">Transfer flow for {escape(focus_type)} '
        f'{escape(focus_id)}</title>'
        f'<desc id="flow-description">Curved bands show transfers connected '
        f'to the selected {escape(focus_type)} {escape(focus_id)}. Band '
        'thickness indicates transfer count; red indicates an alert-linked '
        "transfer.</desc>"
        f'<rect width="{CANVAS_WIDTH}" height="{canvas_height}" rx="12" '
        'fill="#151A23"/>'
        f'<text x="{SOURCE_X}" y="42" fill="#AAB4C3" font-size="14" '
        'font-family="sans-serif" letter-spacing="1">'
        "ORIGINATING ACCOUNTS</text>"
        f'<text x="{ROUTE_X}" y="42" fill="#AAB4C3" font-size="14" '
        'font-family="sans-serif" letter-spacing="1">TRANSFER ROUTES</text>'
        f'<text x="{RECIPIENT_X}" y="42" fill="#AAB4C3" font-size="14" '
        'font-family="sans-serif" letter-spacing="1">RECEIVING ACCOUNTS</text>'
        + "".join(ribbons)
        + "".join(source_cards)
        + "".join(route_cards)
        + "".join(recipient_cards)
        + f'<rect x="{SOURCE_X}" y="{legend_y}" width="9" height="9" '
        'rx="4" fill="#F4A62A"/>'
        f'<text x="{SOURCE_X + 16}" y="{legend_y + 9}" fill="#AAB4C3" '
        'font-size="12" font-family="sans-serif">Routine transfer flow</text>'
        f'<rect x="{SOURCE_X + 176}" y="{legend_y}" width="9" height="9" '
        'rx="4" fill="#F16C7A"/>'
        f'<text x="{SOURCE_X + 192}" y="{legend_y + 9}" fill="#AAB4C3" '
        'font-size="12" font-family="sans-serif">Alert-linked route</text>'
        f'<rect x="{SOURCE_X + 354}" y="{legend_y}" width="9" height="9" '
        'rx="4" fill="#F4A62A"/>'
        f'<text x="{SOURCE_X + 370}" y="{legend_y + 9}" fill="#AAB4C3" '
        'font-size="12" font-family="sans-serif">Selected entity</text>'
        "</svg>"
    )
    return svg, len(involved_accounts), route_count
