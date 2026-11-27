# RVX — AI-Powered Crypto News & Learning Assistant

RVX is a Telegram-first project designed to make cryptocurrency and Web3 information easier to understand.

It combines AI-assisted news explanations with learning features, helping users move from unfamiliar crypto terminology to clearer, more structured understanding.

> **Project status:** Active development. The repository contains application code, tests, and deployment configurations. Public service availability and production usage are not guaranteed by this README.

## Why RVX exists

Crypto news is often full of jargon, context gaps, and claims that are difficult for newcomers to evaluate.

RVX aims to make that information more accessible by helping users:
- understand what a crypto-related event means;
- identify why a news item may matter to the market;
- learn Web3 and trading concepts step by step;
- interact with the project through Telegram.

RVX is an educational and information tool, not a source of guaranteed trading signals or financial advice.

## What the project includes

- **AI-assisted news analysis** — turns crypto-related text into a structured, more accessible explanation.
- **Market context** — highlights possible implications, risks, and areas worth paying attention to.
- **Learning features** — includes interactive educational flows and progress-related functionality.
- **Russian and Ukrainian localization** — the bot includes language support for both languages.
- **Multiple AI integrations** — the codebase includes integrations and fallback logic for several model providers. Available providers depend on environment configuration.
- **Backend services** — a Telegram bot and a FastAPI-based API are provided as separate application components.
- **Operational safeguards** — the backend includes API-key authentication, request limiting, audit logging, input validation, and security-related middleware.

## How the project is structured

| Component | Responsibility |
| --- | --- |
| Telegram bot | User interaction, commands, and learning flows |
| AI analysis modules | Processing and explaining crypto-related content |
| FastAPI backend | API endpoints and backend services |
| Data and utility modules | Configuration, persistence, caching, localization, and supporting features |
| Tests and CI configuration | Automated checks and regression protection |

The repository also includes Docker-based deployment configurations. The Railway-specific Docker configuration starts the bot as a separate service; the API is expected to run separately.

## Technology

- Python
- Telegram Bot API (python-telegram-bot)
- FastAPI
- Pydantic
- SQLite
- Docker and Docker Compose
- AI provider integrations, including Groq, Mistral, Google Gemini, DeepSeek, and Ollama-related components

The exact provider setup depends on environment variables and deployment configuration.

## Run locally with Docker Compose

### 1. Requirements

- Git
- Docker
- Docker Compose
- A Telegram bot token
- API credentials for the AI provider(s) you intend to use

### 2. Get the project

    git clone https://github.com/SGGuard/RVX_AIBot.git
    cd RVX_AIBot

### 3. Configure environment variables

Create your local environment file from the example:

    cp .env.example .env

Edit .env before starting the services. At minimum, configure:

- `TELEGRAM_BOT_TOKEN` — your Telegram bot token.
- At least one AI provider key: `GEMINI_API_KEY`, `GROQ_API_KEY`, or `MISTRAL_API_KEY`.
- `BOT_API_KEY` — a strong random secret shared by the bot and API.
- `ADMIN_TOKEN` — replace the example placeholder with a strong random secret. The default placeholder is rejected outside development.
- `USER_ID_SIGNING_SECRET` — use a random value of at least 32 characters; keep the same value for the bot and API. This enables signed user ID attribution.

You can generate separate random values with:

    openssl rand -hex 32

Run the command once for each secret and paste the results into the corresponding entries in .env. Do not reuse a public example value.

The Compose file supplies the database path and internal API URL for its services. Do not commit your real .env file or expose API keys and tokens.

### 4. Start the services

    docker compose up --build

The Compose configuration defines separate services for the API and Telegram bot. Check the container logs if either service does not start.

## Run tests

The repository includes automated tests. Install the project dependencies and run:

    pip install -r requirements.txt
    pytest

Test results can depend on the local environment and required configuration. A test suite being present does not, by itself, mean every test has passed in every deployment environment.

## Security notes

- Keep credentials in environment variables or a local .env file.
- Never commit real API keys, bot tokens, or production secrets.
- Use unique, strong values for administrative and API authentication tokens.
- Use HTTPS for remote API connections.
- Review deployment settings before exposing services publicly.

## Development approach

RVX is developed through an AI-assisted workflow. AI coding tools are used to support implementation, refactoring, and troubleshooting. The project is iterated through code changes, repository reviews, and automated tests.

AI assistance is part of the development process; it should not be confused with a claim that every line of code was manually written by the project owner.

## Repository

- GitHub: [SGGuard/RVX_AIBot](https://github.com/SGGuard/RVX_AIBot)

## Disclaimer

RVX provides educational explanations and informational context. It does not provide personalized financial advice, guarantee the accuracy of third-party information, or guarantee market outcomes.
