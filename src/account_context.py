from pathlib import Path
import MetaTrader5 as mt5


def _safe(value):
    return str(value).replace(" ", "_").replace("/", "_").replace("\\", "_").replace(":", "_")


def get_account_key():
    account = mt5.account_info()

    if account is None:
        return "unknown_account"

    login = getattr(account, "login", "unknown_login")
    server = getattr(account, "server", "unknown_server")

    return f"{_safe(server)}_{_safe(login)}"


def get_account_data_dir():
    path = Path("data") / "accounts" / get_account_key()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_account_file(filename):
    return get_account_data_dir() / filename