import argparse
import json
from datetime import datetime

from ai_export_common import (
    add_account_argument,
    get_ai_account_file,
    load_json_file,
    logger,
)

def _load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[AI SHADOW REPORT] Failed to load {path}: {e}")
        return default


def _pct(value):
    if value is None:
        return "N/A"

    try:
        return f"{round(float(value) * 100, 1)}%"
    except Exception:
        return "N/A"


def _get_nested(data, *keys, default=None):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

    return current if current is not None else default


def _top_items(mapping, limit=10):
    if not isinstance(mapping, dict):
        return []

    items = list(mapping.items())
    items.sort(
        key=lambda item: item[1].get("total", 0)
        if isinstance(item[1], dict)
        else 0,
        reverse=True,
    )

    return items[:limit]


def build_ai_shadow_advisor_report(account=None):
    dataset_path = get_ai_account_file("ai_memory_dataset.json", account)
    evaluation_path = get_ai_account_file("ai_shadow_advisor_evaluation.json", account)

    dataset = _load_json(dataset_path, [])
    evaluation = _load_json(evaluation_path, {})

    by_recommendation = evaluation.get("by_ai_recommendation", {})
    by_strategy = evaluation.get("by_strategy", {})
    by_match_type = evaluation.get("by_ai_match_type", {})
    by_session = evaluation.get("by_session", {})
    by_market_condition = evaluation.get("by_market_condition", {})

    allow = by_recommendation.get("ALLOW", {})
    block = by_recommendation.get("BLOCK", {})
    warn = by_recommendation.get("WARN", {})

    records = evaluation.get("records", [])

    bad_allows = [
        item for item in records
        if item.get("evaluation_result") == "BAD_ALLOW"
    ]

    bad_blocks = [
        item for item in records
        if item.get("evaluation_result") == "BAD_BLOCK_BLOCKED_WINNER"
    ]

    good_blocks = [
        item for item in records
        if item.get("evaluation_result") == "GOOD_BLOCK_PROTECTED_FROM_SL"
    ]

    warn_worked = [
        item for item in records
        if item.get("evaluation_result") == "WARN_BUT_SETUP_WORKED"
    ]

    report = {
        "generated_at": datetime.now().isoformat(),
        "dataset_records": len(dataset),
        "evaluated_records": evaluation.get("total_ai_evaluated_records", 0),

        "summary": {
            "allow_total": allow.get("total", 0),
            "allow_precision": allow.get("allow_precision"),
            "block_total": block.get("total", 0),
            "block_precision": block.get("block_precision"),
            "warn_total": warn.get("total", 0),
            "warn_favorable_rate": warn.get("favorable_rate"),
            "warn_sl_rate": warn.get("sl_rate"),
        },

        "risk_findings": {
            "bad_allows": bad_allows,
            "bad_blocks": bad_blocks,
            "good_blocks": good_blocks,
            "warn_worked": warn_worked,
        },

        "top_strategy_breakdown": dict(_top_items(by_strategy)),
        "top_match_type_breakdown": dict(_top_items(by_match_type)),
        "session_breakdown": by_session,
        "market_condition_breakdown": by_market_condition,
        "recommendation_breakdown": by_recommendation,
    }

    return report


def export_markdown_report(report):
    lines = []

    summary = report.get("summary", {})
    risk = report.get("risk_findings", {})

    lines.append("# AI Shadow Advisor Report")
    lines.append("")
    lines.append(f"Generated at: `{report.get('generated_at')}`")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- Dataset records: **{report.get('dataset_records')}**")
    lines.append(f"- AI evaluated records: **{report.get('evaluated_records')}**")
    lines.append("")
    lines.append("## Recommendation Quality")
    lines.append("")
    lines.append(f"- ALLOW total: **{summary.get('allow_total')}**")
    lines.append(f"- ALLOW precision: **{_pct(summary.get('allow_precision'))}**")
    lines.append(f"- BLOCK total: **{summary.get('block_total')}**")
    lines.append(f"- BLOCK precision: **{_pct(summary.get('block_precision'))}**")
    lines.append(f"- WARN total: **{summary.get('warn_total')}**")
    lines.append(f"- WARN favorable rate: **{_pct(summary.get('warn_favorable_rate'))}**")
    lines.append(f"- WARN SL rate: **{_pct(summary.get('warn_sl_rate'))}**")
    lines.append("")
    lines.append("## Risk Findings")
    lines.append("")
    lines.append(f"- Bad ALLOW decisions: **{len(risk.get('bad_allows', []))}**")
    lines.append(f"- Bad BLOCK decisions: **{len(risk.get('bad_blocks', []))}**")
    lines.append(f"- Good BLOCK protections: **{len(risk.get('good_blocks', []))}**")
    lines.append(f"- WARN setups that worked: **{len(risk.get('warn_worked', []))}**")
    lines.append("")

    lines.append("## Top Strategy Breakdown")
    lines.append("")

    top_strategy = report.get("top_strategy_breakdown", {})

    if not top_strategy:
        lines.append("No strategy breakdown available.")
    else:
        lines.append("| Strategy | Total | Favorable Rate | SL Rate | ALLOW Precision | BLOCK Precision |")
        lines.append("|---|---:|---:|---:|---:|---:|")

        for strategy, stats in top_strategy.items():
            lines.append(
                f"| {strategy} "
                f"| {stats.get('total', 0)} "
                f"| {_pct(stats.get('favorable_rate'))} "
                f"| {_pct(stats.get('sl_rate'))} "
                f"| {_pct(stats.get('allow_precision'))} "
                f"| {_pct(stats.get('block_precision'))} |"
            )

    lines.append("")
    lines.append("## Top Match-Type Breakdown")
    lines.append("")

    top_match = report.get("top_match_type_breakdown", {})

    if not top_match:
        lines.append("No match-type breakdown available.")
    else:
        lines.append("| Match Type | Total | Favorable Rate | SL Rate |")
        lines.append("|---|---:|---:|---:|")

        for match_type, stats in top_match.items():
            lines.append(
                f"| {match_type} "
                f"| {stats.get('total', 0)} "
                f"| {_pct(stats.get('favorable_rate'))} "
                f"| {_pct(stats.get('sl_rate'))} |"
            )

    lines.append("")
    lines.append("## Industrial Conclusion")
    lines.append("")
    lines.append(
        "AI execution control should remain disabled until the evaluated sample size is large enough "
        "and ALLOW / BLOCK precision is stable across strategy, session, and market-condition groups."
    )

    return "\n".join(lines)


def export_ai_shadow_advisor_report(account=None):
    report = build_ai_shadow_advisor_report(account)

    output_json = get_ai_account_file("ai_shadow_advisor_report.json", account)
    output_md = get_ai_account_file("ai_shadow_advisor_report.md", account)

    output_json.parent.mkdir(parents=True, exist_ok=True)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    markdown = export_markdown_report(report)

    with open(output_md, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"Dataset records: {report.get('dataset_records')}")
    print(f"AI evaluated records: {report.get('evaluated_records')}")
    print(f"JSON report: {output_json}")
    print(f"Markdown report: {output_md}")

    logger.info(
        f"[AI SHADOW REPORT] Exported | "
        f"json={output_json} md={output_md}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_account_argument(parser)
    args = parser.parse_args()

    export_ai_shadow_advisor_report(account=args.account)