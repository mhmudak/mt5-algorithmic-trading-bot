from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _load_project_env(
    root: str | Path | None,
) -> None:
    if root is None:
        return

    try:
        from dotenv import load_dotenv
    except Exception:
        return

    try:
        load_dotenv(
            Path(root) / ".env",
            override=False,
        )
    except Exception:
        # Contract resolution itself remains deterministic.
        # Failure to read dotenv simply means process
        # environment / CLI must provide the symbol.
        pass


def normalize_rithmic_symbol(
    value: object,
) -> str | None:
    text = str(
        value or ""
    ).strip()

    if not text:
        return None

    return text.upper()


def safe_symbol_for_file(
    value: object,
) -> str:
    symbol = normalize_rithmic_symbol(
        value
    )

    if not symbol:
        return ""

    for old, new in (
        ("/", "_"),
        ("\\", "_"),
        (".", "_"),
        (" ", "_"),
        (":", "_"),
    ):
        symbol = symbol.replace(
            old,
            new,
        )

    return symbol


def resolve_rithmic_symbol(
    cli_symbol: object = None,
    *,
    root: str | Path | None = None,
) -> str | None:
    """
    Resolve current contract identity.

    Explicit CLI always wins. Otherwise load the project .env
    if available and use RITHMIC_SYMBOL. No dated futures
    fallback is ever invented here.
    """

    explicit = normalize_rithmic_symbol(
        cli_symbol
    )

    if explicit:
        return explicit

    _load_project_env(
        root
    )

    return normalize_rithmic_symbol(
        os.getenv(
            "RITHMIC_SYMBOL"
        )
    )


def require_rithmic_symbol(
    cli_symbol: object = None,
    *,
    root: str | Path | None = None,
) -> str:
    symbol = resolve_rithmic_symbol(
        cli_symbol,
        root=root,
    )

    if symbol:
        return symbol

    raise ValueError(
        "No Rithmic contract configured. "
        "Pass the symbol explicitly or set "
        "RITHMIC_SYMBOL to the active contract."
    )


def parse_rithmic_symbols(
    value: object,
) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    for part in (
        str(value or "")
        .replace(";", ",")
        .split(",")
    ):
        symbol = (
            normalize_rithmic_symbol(
                part
            )
        )

        if (
            not symbol
            or symbol in seen
        ):
            continue

        seen.add(
            symbol
        )

        symbols.append(
            symbol
        )

    return symbols


def resolve_rithmic_symbols(
    cli_symbols: object = None,
    *,
    root: str | Path | None = None,
) -> list[str]:
    """
    Multi-symbol tools may receive an explicit list.

    Without one, they use exactly the single configured active
    RITHMIC_SYMBOL. They never fabricate an historical pair.
    """

    explicit = parse_rithmic_symbols(
        cli_symbols
    )

    if explicit:
        return explicit

    configured = resolve_rithmic_symbol(
        None,
        root=root,
    )

    return (
        [configured]
        if configured
        else []
    )


def require_rithmic_symbols(
    cli_symbols: object = None,
    *,
    root: str | Path | None = None,
) -> list[str]:
    symbols = resolve_rithmic_symbols(
        cli_symbols,
        root=root,
    )

    if symbols:
        return symbols

    raise ValueError(
        "No Rithmic contract configured. "
        "Pass --symbols explicitly or set "
        "RITHMIC_SYMBOL to the active contract."
    )
