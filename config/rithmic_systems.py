from __future__ import annotations

from dataclasses import dataclass


PHASE = "PHASE_5AN_RITHMIC_PRODUCTION_ENDPOINT_CHECKPOINT"

CONFORMANCE_STATUS = "PASSED"
REQUIRED_APP_PREFIX = "elme:"
DEFAULT_PRODUCTION_ENDPOINT_KEY = "CORE_CHICAGO"


@dataclass(frozen=True)
class RithmicEndpoint:
    key: str
    label: str
    region: str
    host: str
    port: int = 443

    @property
    def websocket_url(self) -> str:
        return f"wss://{self.host}:{self.port}"


RITHMIC_R_PROTOCOL_ENDPOINTS: dict[str, RithmicEndpoint] = {
    "CORE_CHICAGO": RithmicEndpoint(
        key="CORE_CHICAGO",
        label="Core / Chicago",
        region="USA",
        host="rprotocol.rithmic.com",
    ),
    "NEW_YORK": RithmicEndpoint(
        key="NEW_YORK",
        label="New York",
        region="USA",
        host="rprotocol-nyc.rithmic.com",
    ),
    "SYDNEY": RithmicEndpoint(
        key="SYDNEY",
        label="Sydney",
        region="Australia",
        host="rprotocol-au.rithmic.com",
    ),
    "SAO_PAULO": RithmicEndpoint(
        key="SAO_PAULO",
        label="Sao Paolo",
        region="Brazil",
        host="rprotocol-br.rithmic.com",
    ),
    "COLO75": RithmicEndpoint(
        key="COLO75",
        label="Colo75",
        region="USA",
        host="rprotocol-colo75.rithmic.com",
    ),
    "FRANKFURT": RithmicEndpoint(
        key="FRANKFURT",
        label="Frankfurt",
        region="Germany",
        host="rprotocol-de.rithmic.com",
    ),
    "HONG_KONG": RithmicEndpoint(
        key="HONG_KONG",
        label="Hong Kong",
        region="Hong Kong",
        host="rprotocol-hk.rithmic.com",
    ),
    "IRELAND": RithmicEndpoint(
        key="IRELAND",
        label="Ireland",
        region="Ireland",
        host="rprotocol-ie.rithmic.com",
    ),
    "MUMBAI": RithmicEndpoint(
        key="MUMBAI",
        label="Mumbai",
        region="India",
        host="rprotocol-in.rithmic.com",
    ),
    "SEOUL": RithmicEndpoint(
        key="SEOUL",
        label="Seoul",
        region="Korea",
        host="rprotocol-kr.rithmic.com",
    ),
    "CAPE_TOWN": RithmicEndpoint(
        key="CAPE_TOWN",
        label="Cape Town",
        region="South Africa",
        host="rprotocol-za.rithmic.com",
    ),
    "TOKYO": RithmicEndpoint(
        key="TOKYO",
        label="Tokyo",
        region="Japan",
        host="rprotocol-jp.rithmic.com",
    ),
    "SINGAPORE": RithmicEndpoint(
        key="SINGAPORE",
        label="Singapore",
        region="Singapore",
        host="rprotocol-sg.rithmic.com",
    ),
}


PRODUCTION_SWITCH_POLICY = {
    "conformance_required": True,
    "app_prefix_required": REQUIRED_APP_PREFIX,
    "credentials_required": True,
    "market_data_subscription_required": True,
    "comex_market_data_required": True,
    "market_depth_required": True,
    "manual_env_change_required": True,
    "observe_only_first": True,
    "auto_trade_from_rithmic_allowed": False,
    "decision_impact": "NONE",
}


def get_rithmic_endpoint(key: str = DEFAULT_PRODUCTION_ENDPOINT_KEY) -> RithmicEndpoint:
    normalized = (key or DEFAULT_PRODUCTION_ENDPOINT_KEY).strip().upper()

    if normalized not in RITHMIC_R_PROTOCOL_ENDPOINTS:
        raise KeyError(f"Unknown Rithmic endpoint key: {key}")

    return RITHMIC_R_PROTOCOL_ENDPOINTS[normalized]


def list_rithmic_endpoints() -> list[dict[str, str]]:
    return [
        {
            "key": endpoint.key,
            "label": endpoint.label,
            "region": endpoint.region,
            "host": endpoint.host,
            "websocket_url": endpoint.websocket_url,
        }
        for endpoint in RITHMIC_R_PROTOCOL_ENDPOINTS.values()
    ]
