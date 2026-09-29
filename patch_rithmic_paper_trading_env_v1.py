import getpass
import os
import subprocess
from pathlib import Path


EXPECTED_BRANCH = "feature/better-entry-optimizer"
ENV_PATH = Path(".env")
TEMP_PATH = Path(".env.rithmic_patch_tmp")

TARGET_VALUES = {
    "RITHMIC_WS_URL": "wss://rprotocol.rithmic.com:443",
    "RITHMIC_SYSTEM_NAME": "Rithmic Paper Trading",
    "RITHMIC_EXCHANGE": "COMEX",
    "RITHMIC_SYMBOL": "GCZ6",
    "RITHMIC_ENDPOINT_KEY": "CORE_CHICAGO",
    "RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE": "true",
    "RITHMIC_COMEX_MARKET_DATA_ENABLED": "true",
    "RITHMIC_COMEX_MARKET_DEPTH_ENABLED": "true",
}

REQUIRED_KEYS = (
    "RITHMIC_USERNAME",
    "RITHMIC_PASSWORD",
    "RITHMIC_SDK_PATH",
    "RITHMIC_APP_NAME",
)


def stop(message: str) -> None:
    raise SystemExit(f"[STOP] {message}")


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stop(result.stderr.strip() or f"git {' '.join(args)} failed")

    return result.stdout.strip()


def key_of(line: str):
    stripped = line.strip()

    if not stripped or stripped.startswith("#") or "=" not in line:
        return None

    return line.split("=", 1)[0].strip()


branch = git_output("branch", "--show-current")

if branch != EXPECTED_BRANCH:
    stop(
        f"Wrong branch. Expected={EXPECTED_BRANCH} actual={branch}"
    )

print(f"[OK] Branch={branch}")

if not ENV_PATH.exists():
    stop(".env does not exist")

ignored = subprocess.run(
    ["git", "check-ignore", "-q", str(ENV_PATH)],
    capture_output=True,
    text=True,
    check=False,
)

if ignored.returncode != 0:
    stop(".env is not ignored by Git")

print("[OK] .env is ignored by Git")

raw_bytes = ENV_PATH.read_bytes()
has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")

try:
    text = raw_bytes.decode("utf-8-sig")
except UnicodeDecodeError as exc:
    stop(f".env is not valid UTF-8: {exc}")

newline = "\r\n" if "\r\n" in text else "\n"
lines = text.splitlines()

counts = {}

for line in lines:
    key = key_of(line)
    if key:
        counts[key] = counts.get(key, 0) + 1

for key in REQUIRED_KEYS:
    count = counts.get(key, 0)

    if count != 1:
        stop(f"{key} expected exactly once, found {count}")

for key in TARGET_VALUES:
    count = counts.get(key, 0)

    if count > 1:
        stop(f"{key} appears multiple times in .env")

username_line = next(
    line for line in lines if key_of(line) == "RITHMIC_USERNAME"
)

username_value = username_line.split("=", 1)[1].strip()

if not username_value:
    stop("RITHMIC_USERNAME is empty")

print("[OK] Rithmic Paper Trading user ID is present")
print("[INFO] Enter your Rithmic Paper Trading password.")
print("[INFO] The password will not be displayed.")

paper_password = getpass.getpass(
    "Rithmic Paper Trading password: "
)

if not paper_password:
    stop("Paper Trading password cannot be empty")

new_lines = []
updated = set()

for line in lines:
    key = key_of(line)

    if key == "RITHMIC_PASSWORD":
        new_lines.append(f"RITHMIC_PASSWORD={paper_password}")
        updated.add(key)
        continue

    if key in TARGET_VALUES:
        new_lines.append(f"{key}={TARGET_VALUES[key]}")
        updated.add(key)
        continue

    new_lines.append(line)

for key, value in TARGET_VALUES.items():
    if key not in updated:
        new_lines.append(f"{key}={value}")

new_text = newline.join(new_lines).rstrip("\r\n") + newline

encoded = new_text.encode("utf-8")

if has_bom:
    encoded = b"\xef\xbb\xbf" + encoded

if TEMP_PATH.exists():
    stop(f"Temporary file already exists: {TEMP_PATH}")

try:
    TEMP_PATH.write_bytes(encoded)
    os.replace(TEMP_PATH, ENV_PATH)
finally:
    if TEMP_PATH.exists():
        TEMP_PATH.unlink()

print("[UPDATED] .env")
print("[SET] RITHMIC_SYSTEM_NAME=Rithmic Paper Trading")
print("[SET] RITHMIC_WS_URL=wss://rprotocol.rithmic.com:443")
print("[SET] RITHMIC_ENDPOINT_KEY=CORE_CHICAGO")
print("[SET] RITHMIC_EXCHANGE=COMEX")
print("[SET] RITHMIC_SYMBOL=GCZ6")
print("[SET] RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE=true")
print("[SET] RITHMIC_COMEX_MARKET_DATA_ENABLED=true")
print("[SET] RITHMIC_COMEX_MARKET_DEPTH_ENABLED=true")
print("[UPDATED] RITHMIC_PASSWORD=<hidden Paper Trading password>")
print("[INFO] No credential values were printed.")
print("[DONE] Rithmic Paper Trading environment configured.")
print("[NO COMMIT] .env remains ignored/local.")
print("[NO BOT RESTART] Validate the Rithmic API first.")