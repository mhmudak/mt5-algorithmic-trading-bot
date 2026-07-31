
from pathlib import Path

live_bot = Path("src/live_bot.py").read_text(encoding="utf-8")
settings = Path("config/settings.py").read_text(encoding="utf-8")

required_imports = [
    "from src.strategies.strategy_flag import generate_signal as flag_signal",
    "from src.strategies.strategy_flag_refined import generate_signal as flag_refined_signal",
    "from src.strategies.strategy_head_shoulders import generate_signal as head_shoulders_signal",
    "from src.strategies.strategy_triangle_pennant import generate_signal as triangle_pennant_signal",
]

for item in required_imports:
    assert item in live_bot, f"Missing live_bot import: {item}"

required_strategy_tuples = [
    '("TRIANGLE_PENNANT", triangle_pennant_signal)',
    '("FLAG_REFINED", flag_refined_signal)',
    '("FLAG", flag_signal)',
    '("HEAD_SHOULDERS", head_shoulders_signal)',
]

for item in required_strategy_tuples:
    assert item in live_bot, f"Missing live_bot strategy tuple: {item}"

required_confirmed_names = [
    '"HEAD_SHOULDERS"',
    '"TRIANGLE_PENNANT"',
    '"FLAG"',
    '"FLAG_REFINED"',
]

for item in required_confirmed_names:
    assert item in live_bot, f"Missing confirmed/runtime strategy name in live_bot: {item}"

required_ladder_names = [
    '"HEAD_SHOULDERS"',
    '"TRIANGLE_PENNANT"',
    '"FLAG"',
    '"FLAG_REFINED"',
]

for item in required_ladder_names:
    assert item in settings, f"Missing TP ladder eligibility in settings: {item}"

required_base_scores = [
    "FLAG_BASE_MIN_SCORE",
    "FLAG_REFINED_BASE_MIN_SCORE",
    "TRIANGLE_PENNANT_BASE_MIN_SCORE",
    "HEAD_SHOULDERS_BASE_MIN_SCORE",
]

for item in required_base_scores:
    assert item in settings, f"Missing base score setting: {item}"

print("[PASS] Phase 6O4 existing chart-pattern live_bot integration audit passed.")
