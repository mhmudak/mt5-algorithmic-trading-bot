
from pathlib import Path
import ast

TARGETS = [
    ("src/strategies/strategy_balanced_auction_range.py", "BALANCED_AUCTION_RANGE", "BAR"),
    ("src/strategies/strategy_fcr_m1_fvg.py", "FCR_M1_FVG", "FCR"),
    ("src/strategies/strategy_ifvg_retest_confluence.py", "IFVG_RETEST_CONFLUENCE", "IFVG"),
    ("src/strategies/strategy_liquidity_pool_ob.py", "LIQUIDITY_POOL_OB", "LPOB"),
    ("src/strategies/strategy_mtf_order_block_entry.py", "MTF_OB_ENTRY", "MTOB"),
    ("src/strategies/strategy_pro_trader_replication.py", "PRO_TRADER_REPLICATION", "PTR"),
    ("src/strategies/strategy_smt_pro.py", "SMT_PRO", "SMTP"),
    ("src/strategies/strategy_wavetrend_momentum.py", "WAVETREND_MOMENTUM", "WTM"),
    ("src/strategies/strategy_wavetrend_pivot.py", "WAVETREND_PIVOT", "WTP"),
]

for file_path, strategy, prefix in TARGETS:
    source = Path(file_path).read_text(encoding="utf-8")
    ast.parse(source)

    for text in [
        "import hashlib",
        "PHASE6P2_RR_STRATEGY_STANDARDIZATION = True",
        "def _phase6p2_generate_signal_raw(df):",
        "def _phase6p2_standardize_signal",
        "def generate_signal(df):",
        "setup_id",
        "entry_reference",
        "risk_reward",
        "auto_trade_allowed",
        "decision_impact",
        "duplicate_policy",
    ]:
        assert text in source, f"{strategy} missing source text: {text}"

    assert source.count("def generate_signal(df):") == 1, f"{strategy} must expose one generate_signal wrapper"

print("[PASS] Phase 6P2 RR strategy source standardization passed.")
