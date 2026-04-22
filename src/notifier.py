def build_trade_message(data):
    signal = data.get("signal")
    strategy = data.get("strategy")
    entry_model = data.get("entry_model", "N/A")

    entry = data.get("entry")
    sl = data.get("sl")
    tp = data.get("tp")

    score = data.get("score", 0)
    session = data.get("session", "N/A")

    pivot_support = data.get("pivot_support_level")
    pivot_resistance = data.get("pivot_resistance_level")
    pivot_target = data.get("pivot_target_level")

    reason = data.get("reason", "")

    # RR calculation
    rr = "N/A"
    try:
        if signal == "BUY":
            rr_val = (tp - entry) / (entry - sl)
        else:
            rr_val = (entry - tp) / (sl - entry)
        rr = round(rr_val, 2)
    except:
        pass

    message = f"""
📡 SIGNAL DETECTED

🔹 Strategy: {strategy}
🔹 Type: {entry_model}
🔹 Signal: {signal}
🔹 Score: {score}
🔹 Session: {session}

📍 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
📊 RR: {rr}

"""

    if pivot_support:
        message += f"🟢 Support: {round(pivot_support,2)}\n"
    if pivot_resistance:
        message += f"🔴 Resistance: {round(pivot_resistance,2)}\n"
    if pivot_target:
        message += f"🎯 Target Level: {round(pivot_target,2)}\n"

    message += f"\n🧠 Reason:\n{reason}"

    return message