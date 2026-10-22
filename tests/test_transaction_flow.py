import unittest
import xml.etree.ElementTree as ET

from frontend.components.transaction_flow import build_account_flow_svg


def transaction(
    sender: str,
    sender_customer: str,
    receiver: str,
    receiver_customer: str,
    amount: str,
    *,
    currency: str = "TRY",
    alert_linked: bool = False,
) -> dict[str, str | bool]:
    return {
        "sender_account_no": sender,
        "sender_customer_no": f"C-{sender_customer}",
        "sender_customer_name": sender_customer,
        "receiver_account_no": receiver,
        "receiver_customer_no": f"C-{receiver_customer}",
        "receiver_customer_name": receiver_customer,
        "currency": currency,
        "amount": amount,
        "alert_linked": alert_linked,
    }


class TransactionFlowTests(unittest.TestCase):
    def test_shows_only_focused_customer_routes_and_highlights_alerts(self) -> None:
        transactions = [
            transaction("ACC-1", "Origin", "ACC-2", "Destination", "9500.00", alert_linked=True),
            transaction("ACC-1", "Origin", "ACC-2", "Destination", "9800.00"),
            transaction(
                "ACC-1",
                "Origin",
                "ACC-2",
                "Destination",
                "125.00",
                currency="USD",
            ),
            transaction("ACC-3", "Other", "ACC-4", "Unrelated", "300.00"),
        ]

        svg, account_count, route_count = build_account_flow_svg(
            transactions, "customer", "C-Origin"
        )

        self.assertEqual((account_count, route_count), (2, 2))
        self.assertIsNotNone(svg)
        assert svg is not None
        root = ET.fromstring(svg)
        namespace = "{http://www.w3.org/2000/svg}"
        bands = root.findall(f".//{namespace}path[@class='flow-band']")
        self.assertEqual(len(bands), 4)
        self.assertEqual(svg.count("125.00 USD"), 3)
        self.assertEqual(svg.count("19,300.00 TRY"), 3)
        self.assertIn("#F16C7A", svg)
        self.assertIn("Alert-linked route", svg)
        self.assertIn("Selected entity", svg)
        self.assertIn("Transfer flow for customer C-Origin", svg)
        self.assertNotIn("Unrelated", svg)

    def test_account_focus_keeps_all_links_in_a_cycle(self) -> None:
        transactions = [
            transaction("ACC-1", "One", "ACC-2", "Two", "100.00"),
            transaction("ACC-2", "Two", "ACC-3", "Three", "200.00"),
            transaction("ACC-3", "Three", "ACC-1", "One", "300.00", alert_linked=True),
        ]

        svg, account_count, route_count = build_account_flow_svg(
            transactions, "account", "ACC-1"
        )

        self.assertEqual((account_count, route_count), (3, 2))
        assert svg is not None
        root = ET.fromstring(svg)
        namespace = "{http://www.w3.org/2000/svg}"
        self.assertEqual(
            len(root.findall(f".//{namespace}path[@class='flow-band']")),
            4,
        )

    def test_does_not_truncate_focused_routes(self) -> None:
        transactions = [
            transaction(
                "ACC-FOCUS",
                "Focus",
                f"ACC-{index}",
                f"Counterparty {index}",
                f"{index * 100}.00",
            )
            for index in range(1, 13)
        ]

        svg, account_count, route_count = build_account_flow_svg(
            transactions, "customer", "C-Focus"
        )

        self.assertEqual((account_count, route_count), (13, 12))
        assert svg is not None
        root = ET.fromstring(svg)
        namespace = "{http://www.w3.org/2000/svg}"
        self.assertEqual(
            len(root.findall(f".//{namespace}path[@class='flow-band']")),
            24,
        )

    def test_empty_transaction_set_has_no_graph(self) -> None:
        self.assertEqual(
            build_account_flow_svg([], "customer", "C-Missing"),
            (None, 0, 0),
        )

    def test_data_derived_labels_are_escaped_in_svg(self) -> None:
        focused = {
            **transaction(
                "ACC-<1>",
                "<script>alert(1)</script>",
                "ACC-2",
                "Destination & Co",
                "100.00",
            ),
            "sender_customer_no": "C-<1>",
        }

        svg, _, _ = build_account_flow_svg([focused], "account", "ACC-<1>")

        assert svg is not None
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertIn("Destination &amp; Co", svg)
        ET.fromstring(svg)


if __name__ == "__main__":
    unittest.main()
