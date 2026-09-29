import subprocess
from pathlib import Path


EXPECTED_BRANCH = "feature/better-entry-optimizer"
ENV_PATH = Path(".env")

TARGET_VALUES = {
    "RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE": "true",
    "RITHMIC_COMEX_MARKET_DATA_ENABLED": "true",
    "RITHMIC_COMEX_MARKET_DEPTH_ENABLED": "false",
}

REQUIRED_EXISTING_KEYS = (
    "RITHMIC_USERNAME",
    "RITHMIC_PASSWORD",
    "RITHMIC_SYSTEM_NAME",
    "RITHMIC_WS_URL",
    "RITHMIC_EXCHANGE",
    "RITHMIC_SYMBOL",
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


branch = git_output("branch", "--show-current")
if branch != EXPECTED_BRANCH:
    stop(
        f"Wrong branch. Expected={EXPECTED_BRANCH} actual={branch}"
    )

print(f"[OK] Branch={branch}")

if not ENV_PATH.exists():
    stop(".env does not exist")

ignore_result = subprocess.run(
    ["git", "check-ignore", "-q", str(ENV_PATH)],
    capture_output=True,
    text=True,
    check=False,
)

if ignore_result.returncode != 0:
    stop(".env is not ignored by Git")

print("[OK] .env is ignored by Git")

text = ENV_PATH.read_text(encoding="utf-8")

lines = text.splitlines()

for key in REQUIRED_EXISTING_KEYS:
    matches = [
        line
        for line in lines
        if line.strip()
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]

    if len(matches) != 1:
        stop(
            f"{key} expected exactly once in .env, found {len(matches)}"
        )

    value = matches[0].split("=", 1)[1].strip()

    if not value:
        stop(f"{key} exists but is empty")

print("[OK] Existing Rithmic connection keys are present")

for key in TARGET_VALUES:
    matches = [
        line
        for line in lines
        if line.strip()
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[0].strip() == key
    ]

    if len(matches) > 1:
        stop(
            f"{key} appears multiple times in .env; refusing automatic edit"
        )

    if len(matches) == 1:
        stop(
            f"{key} already exists in .env; refusing to overwrite it automatically"
        )

addition = [
    "",
    "# Rithmic production subscription status",
]

for key, value in TARGET_VALUES.items():
    addition.append(f"{key}={value}")

new_text = text.rstrip("\r\n") + "\n" + "\n".join(addition) + "\n"

ENV_PATH.write_text(new_text, encoding="utf-8")

print("[UPDATED] .env")
print(
    "[ADDED] RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE=true"
)
print(
    "[ADDED] RITHMIC_COMEX_MARKET_DATA_ENABLED=true"
)
print(
    "[ADDED] RITHMIC_COMEX_MARKET_DEPTH_ENABLED=false"
)
print("[INFO] No usernames, passwords, or other secret values were printed.")
print(
    "[INFO] Market depth remains disabled until live DOM/Level-2 entitlement is verified."
)
print("[DONE] Rithmic production flags added.")
print("[NO COMMIT] .env remains local and ignored.")
print("[NO RESTART] Validate the Rithmic connection first.")