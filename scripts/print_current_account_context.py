from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5

from src.account_context import (
    get_account_key,
    get_account_data_dir,
    get_account_intelligence_dir,
)


def main():
    initialized = mt5.initialize()
    print("mt5 initialized:", initialized)
    print("last_error:", mt5.last_error())

    account = mt5.account_info()
    if account is None:
        print("[WARN] No MT5 account_info available.")
        print("account_key:", get_account_key())
        print("data_dir:", get_account_data_dir())
        print("intelligence_dir:", get_account_intelligence_dir())
        return

    print("login:", getattr(account, "login", None))
    print("server:", getattr(account, "server", None))
    print("account_key:", get_account_key())
    print("data_dir:", get_account_data_dir())
    print("intelligence_dir:", get_account_intelligence_dir())


if __name__ == "__main__":
    main()
