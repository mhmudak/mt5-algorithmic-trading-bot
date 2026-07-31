from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    live_bot = ROOT / "src" / "live_bot.py"
    settings = ROOT / "config" / "settings.py"
    strategy = ROOT / "src" / "strategies" / "strategy_volatility_compression_breakout.py"

    live_text = live_bot.read_text(encoding="utf-8")
    settings_text = settings.read_text(encoding="utf-8")
    strategy_text = strategy.read_text(encoding="utf-8")

    assert "ENABLE_VOLATILITY_COMPRESSION_BREAKOUT" in settings_text
    assert "VOLATILITY_COMPRESSION_BREAKOUT_DEMO_ONLY" in settings_text
    assert "def generate_signal(df):" in strategy_text
    assert "sl_reference" in strategy_text
    assert "tp_reference" in strategy_text
    assert "setup_source_bucket" in strategy_text
    assert "volatility_compression_breakout_signal" in live_text
    assert '"VOLATILITY_COMPRESSION_BREAKOUT"' in live_text
    assert "if not ENABLE_VOLATILITY_COMPRESSION_BREAKOUT" in live_text

    print("[PASS] Phase 6B VCB is wired into settings, strategy generate_signal, and live_bot strategy_map.")


if __name__ == "__main__":
    main()
