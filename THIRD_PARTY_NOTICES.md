# Third-party notices

Warden uses the following third-party material. Each item is used under the license shown, and copyright stays with its authors. The full license texts ship with each package. The web app shows the same list at `/licenses`.

## Fonts (bundled and served by the web app via `next/font`)

| Font | Author | License |
|---|---|---|
| Space Grotesk | Florian Karsten | SIL Open Font License 1.1 |
| Outfit | The Outfit Project Authors | SIL Open Font License 1.1 |

## Artwork and icons

- The character mascots (`apps/web/components/Toy.tsx`) are original artwork made for Warden (from the Milo prototype).
- Interface icons (`apps/web/components/icons.tsx`) are simple line drawings; some follow the shapes of Feather Icons (MIT License, © Cole Bemis).
- No stock photography or third-party images are used.

## Web app dependencies (`apps/web/package.json`)

| Package | License |
|---|---|
| next | MIT |
| react, react-dom | MIT |
| zustand | MIT |

## API dependencies (`apps/api/requirements.txt`)

| Package | License |
|---|---|
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| pydantic, pydantic-settings | MIT |
| sqlalchemy, alembic | MIT |
| asyncpg | Apache-2.0 |
| httpx | BSD-3-Clause |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| anthropic | MIT |
| plaid-python | MIT |
| stripe | MIT |
| litellm | MIT |
| pgvector | MIT |
| celery | BSD-3-Clause |
| redis | MIT |
| email-validator | Unlicense |
| python-dotenv | BSD-3-Clause |
| tavily-python | MIT |
| e2b-code-interpreter | MIT |

## Development tooling (not shipped)

- `.claude/skills/apple-design`: design guidance by Emil Kowalski, MIT License (see its LICENSE file).
