from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from src.order_flow_providers.rithmic_protocol import RithmicConfig, RithmicMarketDataClient


PHASE = "PHASE_5AG_RITHMIC_CONFORMANCE_ORDER_PLANT_LOGIN"

ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

OUT_JSON = ORDER_FLOW_DIR / "phase5ag_rithmic_conformance_order_plant_login.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5ag_rithmic_conformance_order_plant_login_summary.txt"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_rithmic_config(*, symbol: str, exchange: str) -> RithmicConfig:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    env_values = {
        "ws_url": os.getenv("RITHMIC_WS_URL"),
        "url": os.getenv("RITHMIC_WS_URL"),
        "websocket_url": os.getenv("RITHMIC_WS_URL"),
        "system_name": os.getenv("RITHMIC_SYSTEM_NAME"),
        "system": os.getenv("RITHMIC_SYSTEM_NAME"),
        "username": os.getenv("RITHMIC_USERNAME"),
        "user": os.getenv("RITHMIC_USERNAME"),
        "password": os.getenv("RITHMIC_PASSWORD"),
        "exchange": exchange,
        "symbol": symbol,
        "sdk_path": os.getenv("RITHMIC_SDK_PATH"),
        "rithmic_sdk_path": os.getenv("RITHMIC_SDK_PATH"),
    }

    signature = inspect.signature(RithmicConfig)
    kwargs = {}

    for name in signature.parameters:
        if name == "self":
            continue
        if name in env_values and env_values[name] is not None:
            kwargs[name] = env_values[name]

    return RithmicConfig(**kwargs)


def resolve_rithmic_symbol(
    cli_symbol: str | None,
    configured_symbol: str | None,
) -> str:
    """
    Resolve an explicit/current contract only.

    The ORDER_PLANT conformance login does not subscribe to
    market data, but RithmicMarketDataClient still requires
    explicit contract identity and must never silently choose
    an old dated contract.
    """

    cli = str(
        cli_symbol or ""
    ).strip()

    if cli:
        return cli.upper()

    configured = str(
        configured_symbol or ""
    ).strip()

    if configured:
        return configured.upper()

    raise ValueError(
        "No Rithmic contract configured. "
        "Pass --symbol explicitly or set "
        "RITHMIC_SYMBOL to the active contract."
    )


async def close_transport_quietly(
    client: Any,
) -> None:
    """
    Close only the websocket transport.

    Phase 5AG performs a custom ORDER_PLANT login. Do not send
    the generic provider logout request without explicit
    protocol evidence that the same logout flow is required.
    """

    ws = getattr(
        client,
        "ws",
        None,
    )

    client.ws = None

    if ws is None:
        return

    try:
        await ws.close(
            1000,
            "phase5ag conformance done",
        )
    except Exception:
        pass


def get_order_plant_enum(pb: dict[str, Any]) -> int:
    enum_obj = pb["request_login_pb2"].RequestLogin.SysInfraType

    candidates = [
        "ORDER_PLANT",
        "ORDERS",
        "ORDER_PLANT_SYS",
    ]

    for name in candidates:
        if hasattr(enum_obj, name):
            return getattr(enum_obj, name)

    if hasattr(enum_obj, "Value"):
        for name in candidates:
            try:
                return enum_obj.Value(name)
            except Exception:
                pass

    available = [x for x in dir(enum_obj) if x.isupper()]
    raise RuntimeError(f"ORDER_PLANT enum not found. Available enum names: {available}")


async def main_async() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--symbol",
        default=None,
    )

    parser.add_argument(
        "--exchange",
        default="COMEX",
    )

    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=3600,
    )

    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=30,
    )

    args = parser.parse_args()

    if load_dotenv is not None:
        load_dotenv(
            ROOT / ".env"
        )

    try:
        symbol = (
            resolve_rithmic_symbol(
                args.symbol,
                os.getenv(
                    "RITHMIC_SYMBOL"
                ),
            )
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    app_name = os.getenv(
        "RITHMIC_APP_NAME",
        "elme:MT5_XAUUSD_RITHMIC_OBSERVE_ONLY",
    )

    config = build_rithmic_config(
        symbol=symbol,
        exchange=args.exchange,
    )

    client = RithmicMarketDataClient(
        config
    )

    print(
        "[PHASE 5AG RITHMIC "
        "CONFORMANCE ORDER PLANT LOGIN]"
    )

    print(
        f"system_name = "
        f"{config.system_name}"
    )

    print(
        f"symbol = {symbol}"
    )

    print(
        f"exchange = "
        f"{args.exchange}"
    )

    print(
        f"app_name = {app_name}"
    )

    print(
        "infra_type = ORDER_PLANT"
    )

    print(
        "mode = CONFORMANCE_LOGIN_ONLY"
    )

    print(
        "decision_impact = NONE"
    )

    print(
        "can_influence_decision = False"
    )

    print(
        "trade_action = NO_AUTO_TRADE"
    )

    print(
        "orders_sent = 0"
    )

    print("")

    started_at = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    login_ok = False

    login_response: dict[
        str,
        Any,
    ] = {}

    error: str | None = None

    try:
        await client.connect()

        rq = (
            client.pb[
                "request_login_pb2"
            ].RequestLogin()
        )

        rq.template_id = 10
        rq.template_version = "3.9"

        rq.user_msg.append(
            "phase5ag_conformance_"
            "order_plant_login"
        )

        rq.user = config.username
        rq.password = config.password
        rq.app_name = app_name
        rq.app_version = "0.1.0"
        rq.system_name = (
            config.system_name
        )

        rq.infra_type = (
            get_order_plant_enum(
                client.pb
            )
        )

        await client.ws.send(
            rq.SerializeToString()
        )

        raw = await client.ws.recv()

        rp = (
            client.pb[
                "response_login_pb2"
            ].ResponseLogin()
        )

        rp.ParseFromString(
            raw
        )

        rp_code = list(
            rp.rp_code
        )

        login_ok = (
            rp_code == ["0"]
            or rp_code == [0]
        )

        login_response = {
            "rp_code": rp_code,
            "ok": login_ok,
            "fcm_id": getattr(
                rp,
                "fcm_id",
                None,
            ),
            "ib_id": getattr(
                rp,
                "ib_id",
                None,
            ),
            "heartbeat_interval": getattr(
                rp,
                "heartbeat_interval",
                None,
            ),
            "unique_user_id": getattr(
                rp,
                "unique_user_id",
                None,
            ),
        }

        print(
            "[LOGIN ORDER PLANT] "
            f"ok={login_ok} "
            f"rp_code={rp_code}"
        )

        print(
            "Leave this window running. "
            "Now email Rithmic that the "
            "app is logged in."
        )

        print(
            "Press Ctrl+C only after Rithmic "
            "says they are done or after "
            "duration ends."
        )

        print("")

        end_time = (
            time.time()
            + args.duration_seconds
        )

        heartbeat_count = 0

        while (
            time.time()
            < end_time
        ):
            await asyncio.sleep(
                args.heartbeat_seconds
            )

            heartbeat_count += 1

            try:
                await client.send_heartbeat()

                print(
                    "[HEARTBEAT] "
                    f"{heartbeat_count} ok at "
                    f"{datetime.now().isoformat(timespec='seconds')}"
                )

            except Exception as exc:
                print(
                    "[HEARTBEAT WARNING] "
                    f"{repr(exc)}"
                )

    except KeyboardInterrupt:
        print(
            "[STOPPED] Ctrl+C received."
        )

    except Exception as exc:
        error = repr(exc)

        print(
            f"[ERROR] {error}"
        )

    finally:
        await close_transport_quietly(
            client
        )

    report = {
        "phase": PHASE,
        "started_at": started_at,
        "updated_at": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),
        "system_name": getattr(
            config,
            "system_name",
            None,
        ),
        "symbol": symbol,
        "exchange": args.exchange,
        "app_name": app_name,
        "infra_type": "ORDER_PLANT",
        "mode": (
            "CONFORMANCE_LOGIN_ONLY"
        ),
        "login_ok": login_ok,
        "login_response": (
            login_response
        ),
        "error": error,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "orders_sent": 0,
        "recommendation": (
            "If login_ok is True, notify "
            "Rithmic that app_name is logged "
            "into the order plant of "
            "Rithmic Test."
        ),
    }

    write_json(
        OUT_JSON,
        report,
    )

    lines = [
        "[PHASE 5AG RITHMIC "
        "CONFORMANCE ORDER PLANT LOGIN]",
        f"updated_at = "
        f"{report['updated_at']}",
        f"system_name = "
        f"{report['system_name']}",
        f"symbol = "
        f"{report['symbol']}",
        f"app_name = "
        f"{report['app_name']}",
        f"infra_type = "
        f"{report['infra_type']}",
        f"login_ok = "
        f"{report['login_ok']}",
        f"rp_code = "
        f"{login_response.get('rp_code')}",
        f"orders_sent = "
        f"{report['orders_sent']}",
        f"decision_impact = "
        f"{report['decision_impact']}",
        f"can_influence_decision = "
        f"{report['can_influence_decision']}",
        f"trade_action = "
        f"{report['trade_action']}",
        f"error = "
        f"{report['error']}",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()