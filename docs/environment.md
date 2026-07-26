# Environment Variables

This file defines the Phase 0 environment plan. Concrete values must stay in local `.env` files and deployment secrets.

## Backend

See `backend/.env.example`.

Required groups:

- application settings
- CORS settings
- MongoDB settings
- JWT settings
- password hashing settings
- ChromaDB settings
- OpenAI settings
- Groq settings
- storage settings
- upload settings
- notification integration placeholders

## Frontend

See `frontend/.env.example`.

Required groups:

- API base URL
- public app name
- feature flags for incomplete integrations

## Secret Handling Rules

- Do not commit real `.env` files.
- Do not commit API keys.
- Use deployment provider secret managers for production.
- Use `.env.example` only for variable names and safe defaults.

## Confirmed Deployment Targets

- Backend: Railway
- Frontend: Vercel
- Development database: local MongoDB
- Production database: MongoDB Atlas
- Primary image storage: ImageKit

## Secret Notes

OpenAI, Groq, and ImageKit credentials must be placed in local `.env` files during development and in Railway/Vercel secrets during deployment. They must not be copied into source files, docs, screenshots, or committed configuration.
