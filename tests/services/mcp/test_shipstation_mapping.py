import json

from sophia.services.mcp.models import MCPToolResult
from sophia.services.mcp.shipstation_mapping import (
    _parse_shipstation_carrier_services,
    _parse_shipstation_return_label,
    _parse_shipstation_tracking,
)


def _wrap(data: dict) -> MCPToolResult:
    return MCPToolResult(content=[{"type": "text", "text": json.dumps(data)}])


class TestParseShipstationTracking:
    def test_full_shipment(self):
        data = {
            "shipment_id": "se-1234567",
            "order_id": "se-order-001",
            "tracking_number": "9400111899223397846123",
            "carrier_code": "usps",
            "service_code": "usps_priority_mail",
            "ship_date": "2025-01-15T00:00:00Z",
            "status": "delivered",
            "ship_to": {"name": "Alice Smith", "address_line1": "123 Main St"},
        }
        tracking = _parse_shipstation_tracking(_wrap(data))

        assert tracking.order_id == "se-order-001"
        assert tracking.carrier == "usps"
        assert tracking.tracking_number == "9400111899223397846123"
        assert tracking.status == "delivered"
        assert tracking.estimated_delivery is not None

    def test_minimal_shipment(self):
        data = {"order_id": "se-order-002", "status": "pending"}
        tracking = _parse_shipstation_tracking(_wrap(data))

        assert tracking.order_id == "se-order-002"
        assert tracking.status == "pending"
        assert tracking.tracking_number == ""
        assert tracking.carrier == ""
        assert tracking.estimated_delivery is None


class TestParseShipstationCarrierServices:
    def test_multiple_services(self):
        data = {
            "services": [
                {
                    "carrier_code": "usps",
                    "service_code": "usps_priority_mail",
                    "name": "USPS Priority Mail",
                    "domestic": True,
                    "international": False,
                },
                {
                    "carrier_code": "fedex",
                    "service_code": "fedex_ground",
                    "name": "FedEx Ground",
                    "domestic": True,
                    "international": False,
                },
            ]
        }
        options = _parse_shipstation_carrier_services(_wrap(data))

        assert len(options) == 2
        assert options[0].carrier == "usps"
        assert options[0].service == "USPS Priority Mail"
        assert options[0].cost == 0.0
        assert options[0].estimated_days == 0
        assert options[1].carrier == "fedex"

    def test_empty_services(self):
        data = {"services": []}
        options = _parse_shipstation_carrier_services(_wrap(data))
        assert options == []


class TestParseShipstationReturnLabel:
    def test_return_label(self):
        data = {
            "label_id": "se-label-123",
            "tracking_number": "9400111899223397846123",
            "label_download": {"pdf": "https://api.shipstation.com/v2/downloads/10/label.pdf"},
            "shipment_id": "se-ship-456",
            "carrier_code": "usps",
        }
        label = _parse_shipstation_return_label(_wrap(data))

        assert label.label_url == "https://api.shipstation.com/v2/downloads/10/label.pdf"
        assert label.tracking_number == "9400111899223397846123"
        assert label.carrier == "usps"
        assert label.expiry is not None
