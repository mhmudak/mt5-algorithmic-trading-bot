import MetaTrader5 as mt5


def main() -> None:
    print("Starting MT5 connection test...")

    if not mt5.initialize():
        print("initialize() failed")
        print("Error:", mt5.last_error())
        return

    print("MT5 initialized successfully")

    version = mt5.version()
    print("Terminal version:", version)

    account_info = mt5.account_info()
    if account_info is None:
        print("Could not read account info")
        print("Error:", mt5.last_error())
        mt5.shutdown()
        return

    print("Connected account login:", account_info.login)
    print("Server:", account_info.server)
    print("Balance:", account_info.balance)

    mt5.shutdown()
    print("MT5 connection closed cleanly")


if __name__ == "__main__":
    main()