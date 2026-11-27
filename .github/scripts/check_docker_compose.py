#!/usr/bin/env python3
"""Validate the Compose settings shared by the API and bot services."""

from pathlib import Path

import yaml


def service_environment(service: dict, service_name: str) -> dict[str, str]:
    entries = service.get("environment", [])
    if not isinstance(entries, list):
        raise SystemExit(f"{service_name}.environment must be a list.")
    return {
        entry.split("=", 1)[0]: entry.split("=", 1)[1]
        for entry in entries
        if isinstance(entry, str) and "=" in entry
    }


def main() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    api = services["api"]
    bot = services["bot"]
    api_environment = service_environment(api, "api")
    bot_environment = service_environment(bot, "bot")

    if any(key.startswith("TELEGRAM_") for key in api_environment):
        raise SystemExit("The API service must not require Telegram credentials.")
    if api_environment.get("DATABASE_PATH") != bot_environment.get("DATABASE_PATH"):
        raise SystemExit("API and bot must use the same DATABASE_PATH.")
    if api_environment.get("DATABASE_PATH") != "/app/rvx_bot.db":
        raise SystemExit("Compose DATABASE_PATH must match the shared application DB.")
    if api["networks"] != bot["networks"]:
        raise SystemExit("API and bot must share a Compose network.")
    if "./:/app" not in api.get("volumes", []) or "./:/app" not in bot.get(
        "volumes", []
    ):
        raise SystemExit("API and bot must share the application directory.")

    healthcheck = bot.get("healthcheck", {})
    test = healthcheck.get("test", [])
    if "http://api:8000/health" not in test:
        raise SystemExit(
            "The bot healthcheck must probe the API over the Compose network."
        )

    print("Docker Compose API, database, network, and bot healthcheck settings passed.")


if __name__ == "__main__":
    main()
