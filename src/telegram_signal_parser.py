import re


BUY_WORDS = [
    "buy",
    "buy gold",
    "شراء",
    "شرا",
]

SELL_WORDS = [
    "sell",
    "sell gold",
    "بيع",
]

GOLD_WORDS = [
    "gold",
    "xau",
    "xauusd",
    "ذهب",
]

STOP_WORDS = [
    "sl",
    "st",
    "stop",
    "stoploss",
    "ستوب",
]

TP_WORDS = [
    "tp",
    "tp1",
    "tp2",
    "tp3",
    "tp4",
    "هدف",
]

LOW_RISK_WORDS = [
    "low lot",
    "low risk",
    "لوت خفيف",
    "خطره",
    "خطرة",
]

PARTIAL_PROFIT_WORDS = [
    "حجزو ربح",
    "حجزوا ربح",
    "partial",
    "book profit",
]

CLOSE_FIRST_ENTRY_WORDS = [
    "سكرو اول دخول",
    "سكروا اول دخول",
    "close first",
    "close first entry",
]

RUNNING_WORDS = [
    "running",
    "pips running",
    "pipsdone",
    "pips done",
]

PARTIAL_PROFIT_WORDS += [
    "احجز ربحك",
    "احجزو ربحك",
    "احجز ربح",
    "نزيف احجز ربحك",
]

CLOSE_FIRST_ENTRY_WORDS += [
    "اغلق عقد",
    "اغلق اول دخول",
    "سكرو اول دخول",
]

MOVE_BE_WORDS = [
    "امن دخولك",
    "أمن دخولك",
    "امن دخول عقد",
    "زيرو انعكاس",
]

def normalize_text(text):
    if not text:
        return ""

    replacements = {
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "،": ",",
        "||": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.strip()


def contains_any(text, words):
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def extract_numbers(text):
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]


def detect_direction(text):
    lowered = text.lower()

    if any(word in lowered for word in SELL_WORDS):
        return "SELL"

    if any(word in lowered for word in BUY_WORDS):
        return "BUY"

    return None


def extract_stop_loss(lines):
    for line in lines:
        lower = line.lower()

        if any(word in lower for word in STOP_WORDS):
            numbers = extract_numbers(line)

            if numbers:
                return numbers[0]

    return None


def extract_tps(lines):
    tps = []

    for line in lines:
        lower = line.lower()

        if any(word in lower for word in TP_WORDS):
            numbers = extract_numbers(line)
            tps.extend(numbers)

    return tps


def extract_entry_zone(text, direction):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    signal_line = None

    for line in lines:
        lower = line.lower()

        if (
            ("gold" in lower or "xau" in lower or "ذهب" in lower)
            and direction
            and direction.lower() in lower
        ):
            signal_line = line
            break

        if direction == "BUY" and ("buy" in lower or "شراء" in lower or "شرا" in lower):
            signal_line = line
            break

        if direction == "SELL" and ("sell" in lower or "بيع" in lower):
            signal_line = line
            break

    if not signal_line:
        return None, None

    numbers = extract_numbers(signal_line)

    if not numbers:
        return None, None

    # Remove obvious non-entry numbers if present by taking first two prices on the signal line.
    if len(numbers) == 1:
        return numbers[0], numbers[0]

    entry_low = min(numbers[0], numbers[1])
    entry_high = max(numbers[0], numbers[1])

    return entry_low, entry_high


def parse_management_message(text):
    if contains_any(text, PARTIAL_PROFIT_WORDS):
        return {
            "type": "MANAGEMENT",
            "action": "PARTIAL_PROFIT",
            "raw_text": text,
        }

    if contains_any(text, CLOSE_FIRST_ENTRY_WORDS):
        return {
            "type": "MANAGEMENT",
            "action": "CLOSE_FIRST_ENTRY_KEEP_BEST",
            "raw_text": text,
        }

    if "ستوب" in text or "sl" in text.lower():
        numbers = extract_numbers(text)

        if numbers:
            return {
                "type": "MANAGEMENT",
                "action": "MOVE_STOP",
                "new_sl": numbers[0],
                "raw_text": text,
            }

    if contains_any(text, RUNNING_WORDS):
        numbers = extract_numbers(text)

        return {
            "type": "UPDATE",
            "action": "RUNNING_PROFIT",
            "pips": numbers[0] if numbers else None,
            "raw_text": text,
        }
        
    if contains_any(text, MOVE_BE_WORDS):
        numbers = extract_numbers(text)
    
        return {
            "type": "MANAGEMENT",
            "action": "MOVE_TO_BREAKEVEN",
            "entry_hint": numbers[0] if numbers else None,
            "raw_text": text,
        }

    return None


def parse_telegram_signal(text):
    text = normalize_text(text)

    if not text:
        return {
            "type": "IGNORE",
            "reason": "empty_message",
        }

    management = parse_management_message(text)

    if management:
        return management

    direction = detect_direction(text)

    if not direction:
        return {
            "type": "IGNORE",
            "reason": "no_direction",
            "raw_text": text,
        }

    if not contains_any(text, GOLD_WORDS):
        return {
            "type": "IGNORE",
            "reason": "not_gold_signal",
            "raw_text": text,
        }

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    entry_low, entry_high = extract_entry_zone(text, direction)
    sl = extract_stop_loss(lines)
    tps = extract_tps(lines)

    risk_note = None

    if contains_any(text, LOW_RISK_WORDS):
        risk_note = "LOW_RISK"

    # Pre-signal like: "Buy now" / "Sell now"
    if entry_low is None and sl is None and not tps:
        return {
            "type": "PRE_SIGNAL",
            "direction": direction,
            "symbol": "XAUUSD",
            "risk_note": risk_note,
            "raw_text": text,
        }

    missing = []

    if entry_low is None:
        missing.append("entry")

    if sl is None:
        missing.append("sl")

    if not tps:
        missing.append("tp")

    if missing:
        return {
            "type": "INCOMPLETE_SIGNAL",
            "direction": direction,
            "symbol": "XAUUSD",
            "entry_low": entry_low,
            "entry_high": entry_high,
            "sl": sl,
            "tps": tps,
            "missing": missing,
            "risk_note": risk_note,
            "raw_text": text,
        }

    return {
        "type": "SIGNAL",
        "direction": direction,
        "symbol": "XAUUSD",
        "entry_low": entry_low,
        "entry_high": entry_high,
        "sl": sl,
        "tps": tps,
        "tp1": tps[0] if len(tps) >= 1 else None,
        "tp2": tps[1] if len(tps) >= 2 else None,
        "tp3": tps[2] if len(tps) >= 3 else None,
        "tp4": tps[3] if len(tps) >= 4 else None,
        "risk_note": risk_note,
        "raw_text": text,
    }