import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

READINESS_PATH = INTEL_DIR / "phase4_orderflow_provider_readiness_report.json"
REPORT_PATH = INTEL_DIR / "phase4_orderflow_provider_selection_matrix.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_provider_selection_matrix_summary.txt"


REQUIRED_BOT_NEEDS = [
    "real COMEX / CME futures data",
    "GC or MGC futures mapping for XAUUSD context",
    "real volume-at-price POC",
    "value area high / low",
    "bid volume",
    "ask volume",
    "delta",
    "cumulative delta",
    "footprint / cluster data",
    "DOM / market depth",
    "timestamped snapshots",
    "stable observe-only ingestion path",
]


PROVIDERS = [
    {
        "provider_id": "RITHMIC_API",
        "provider_name": "Rithmic API / R Protocol API",
        "role": "PRIMARY_CANDIDATE_FOR_DIRECT_BOT_INGESTION",
        "fit_score": 92,
        "strengths": [
            "Designed for futures infrastructure and API use.",
            "Potentially suitable for direct market-data ingestion.",
            "More appropriate for bot integration than visual-only platforms.",
            "Can become long-term architecture if API access is approved.",
        ],
        "risks_or_questions": [
            "Need to confirm API access for your account/broker/FCM.",
            "Need to confirm CME/COMEX market-depth entitlement.",
            "Need to confirm whether historical depth/tick data is available.",
            "Need developer kit/access approval before coding final connector.",
            "May require paid professional/non-professional data permissions.",
        ],
        "required_confirmations_before_subscribe": [
            "Can I access live COMEX GC or MGC futures market data by API?",
            "Can I get bid volume, ask volume, trades, quotes, and market depth?",
            "Can I get enough data to compute footprint, delta, cumulative delta, POC, and value area?",
            "Can I use the API from Python, or do I need a bridge/wrapper?",
            "What is the exact monthly cost including exchange fees?",
            "Is paper/sim access available before live use?",
        ],
        "decision": "CONTACT_FIRST_DO_NOT_SUBSCRIBE_YET",
    },
    {
        "provider_id": "SIERRA_CHART_DENALI_DTC",
        "provider_name": "Sierra Chart Denali + DTC Bridge",
        "role": "STRONG_VALIDATION_AND_BRIDGE_CANDIDATE",
        "fit_score": 88,
        "strengths": [
            "Very strong futures data and volume-profile ecosystem.",
            "Good candidate for validating footprint/POC/market-depth behavior visually.",
            "DTC bridge can be useful if direct API provider path is blocked.",
            "Good research/validation layer before letting bot consume real order-flow.",
        ],
        "risks_or_questions": [
            "May require Sierra Chart running as part of the data bridge.",
            "Not as clean as a direct Python API.",
            "Need to confirm DTC access and export path for required fields.",
            "Need to confirm subscription package and exchange entitlements.",
        ],
        "required_confirmations_before_subscribe": [
            "Can DTC expose live market depth and time-and-sales needed by the bot?",
            "Can we access GC/MGC futures with Denali in real time?",
            "Can we compute or retrieve volume-at-price POC/value area?",
            "Can Python connect reliably to the DTC server locally?",
            "What package and exchange fees are required?",
        ],
        "decision": "CONTACT_SECOND_OR_USE_AS_VALIDATION_BRIDGE",
    },
    {
        "provider_id": "DXFEED_API",
        "provider_name": "dxFeed CME/COMEX data",
        "role": "DATA_FEED_CANDIDATE_NEEDS_API_CONFIRMATION",
        "fit_score": 82,
        "strengths": [
            "CME/CBOT/NYMEX/COMEX data coverage appears relevant.",
            "Market-depth packages may fit order-flow research.",
            "Could be a clean data-provider path if API access is available.",
        ],
        "risks_or_questions": [
            "Need to confirm API availability for your use case.",
            "Need to confirm exact fields for bid/ask volume, depth, trades, and history.",
            "Need to confirm integration complexity and cost.",
            "Retail platform packages may not equal direct API availability.",
        ],
        "required_confirmations_before_subscribe": [
            "Do I get an API, or only platform access?",
            "Does the API include COMEX market depth?",
            "Can I access GC/MGC time-and-sales and order book snapshots?",
            "Can I store data for research/backtesting?",
            "What is the total monthly cost?",
        ],
        "decision": "EVALUATE_AFTER_RITHMIC_AND_SIERRA",
    },
    {
        "provider_id": "QUANTOWER_VISUAL_VALIDATION",
        "provider_name": "Quantower",
        "role": "VISUAL_ORDERFLOW_VALIDATION_TOOL",
        "fit_score": 68,
        "strengths": [
            "Useful visual order-flow platform.",
            "Good for manually validating volume profile, delta, footprint concepts.",
            "Can help compare bot conclusions with professional visual tools.",
        ],
        "risks_or_questions": [
            "Not first choice for direct Python ingestion.",
            "API path may be less suitable for this MT5 Python bot.",
            "May be better as a visual validation tool than the main data source.",
        ],
        "required_confirmations_before_subscribe": [
            "Can its API expose the needed data externally?",
            "Is Python integration practical?",
            "Can it export real-time footprint/delta/POC data?",
            "What data-feed subscription is needed?",
        ],
        "decision": "USE_FOR_VISUAL_VALIDATION_NOT_FIRST_CONNECTOR",
    },
]


def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    readiness = load_json(READINESS_PATH)
    readiness_status = readiness.get("readiness_status", "UNKNOWN")

    sorted_providers = sorted(PROVIDERS, key=lambda item: item["fit_score"], reverse=True)

    top_provider = sorted_providers[0]

    report = {
        "phase": "PHASE_4T_ORDERFLOW_PROVIDER_SELECTION_MATRIX",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "readiness_status": readiness_status,
        "required_bot_needs": REQUIRED_BOT_NEEDS,
        "providers": sorted_providers,
        "top_candidate": top_provider,
        "recommended_sequence": [
            "Contact Rithmic/API access path first.",
            "Contact Sierra Chart/Denali only if Rithmic API path is blocked or for validation bridge.",
            "Check dxFeed API only after confirming direct API access and market-depth entitlement.",
            "Use Quantower mainly for visual validation unless API export is confirmed.",
        ],
        "subscription_decision": "DO_NOT_SUBSCRIBE_YET",
        "next_step": "Collect provider answers and pricing before paying.",
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "warning": "Provider selection is preparation only. No order-flow data may influence live trading until observe-only validation passes.",
        "recommendation": "CONTACT_PROVIDERS_AND_CONFIRM_API_DATA_ENTITLEMENTS",
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4T ORDER-FLOW PROVIDER SELECTION MATRIX]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"readiness_status = {readiness_status}",
        f"subscription_decision = {report['subscription_decision']}",
        "",
        "[TOP CANDIDATE]",
        f"provider_id = {top_provider['provider_id']}",
        f"provider_name = {top_provider['provider_name']}",
        f"fit_score = {top_provider['fit_score']}",
        f"role = {top_provider['role']}",
        f"decision = {top_provider['decision']}",
        "",
        "[PROVIDER RANKING]",
    ]

    for provider in sorted_providers:
        lines.append(
            f"{provider['fit_score']} | {provider['provider_id']} | "
            f"{provider['role']} | {provider['decision']}"
        )

    lines += [
        "",
        "[REQUIRED BOT NEEDS]",
    ]

    for need in REQUIRED_BOT_NEEDS:
        lines.append(f"- {need}")

    lines += [
        "",
        "[CONTACT QUESTIONS FOR TOP CANDIDATE]",
    ]

    for question in top_provider["required_confirmations_before_subscribe"]:
        lines.append(f"- {question}")

    lines += [
        "",
        "[RECOMMENDED SEQUENCE]",
    ]

    for step in report["recommended_sequence"]:
        lines.append(f"- {step}")

    lines += [
        "",
        "[NEXT STEP]",
        report["next_step"],
        "",
        "[WARNING]",
        report["warning"],
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()