# API documentation

The web UI exposes a FastAPI backend. Once running, interactive API docs are at:

- Swagger UI: http://127.0.0.1:5000/docs
- ReDoc: http://127.0.0.1:5000/redoc
- OpenAPI schema: http://127.0.0.1:5000/openapi.json

The OpenAPI schema is the source of truth for the React frontend's TypeScript types — generate client types from `/openapi.json` rather than hand-rolling them.
