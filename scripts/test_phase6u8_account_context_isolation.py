from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import account_context


def test_account_key_is_dynamic_and_safe():
    original_account_info = account_context.mt5.account_info

    try:
        account_context.mt5.account_info = lambda: SimpleNamespace(
            server="Other Broker/Demo:Server",
            login=98765432,
        )

        key = account_context.get_account_key()

        assert key == "Other_Broker_Demo_Server_98765432"
        assert "Tickmill-Demo_25323531" not in key

        data_dir = account_context.get_account_data_dir()
        intel_dir = account_context.get_account_intelligence_dir()

        assert str(data_dir).replace("\\", "/").endswith("data/accounts/Other_Broker_Demo_Server_98765432")
        assert str(intel_dir).replace("\\", "/").endswith("data/strategy_intelligence/Other_Broker_Demo_Server_98765432")

    finally:
        account_context.mt5.account_info = original_account_info


if __name__ == "__main__":
    test_account_key_is_dynamic_and_safe()
    print("[PASS] Phase 6U8 account context isolation passed.")
