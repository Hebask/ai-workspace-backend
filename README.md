# AI Workspace Backend (WebSocket + MongoDB Atlas + RAG + Images + MCP)

A production-oriented FastAPI backend for a multi-user AI “workspace”:
- JWT auth (register/login)
- WebSocket chat (streaming deltas)
- Per-user conversations stored in MongoDB (Atlas supported)
- PDF upload + chunking + retrieval (RAG)
- Image generation + secure public share links
- MCP integration (tool server) for extending capabilities
- Redis-based usage quotas (per plan)

## Features
- **Auth**: `/auth/register`, `/auth/login`, `/auth/me`
- **WebSocket**: `/ws` (auth + assistant + chat + list conversations/messages)
- **Conversations API**: `GET /conversations`, `GET /conversations/{id}/messages`
- **Files**: `POST /files/upload` (multipart)
- **Images**: generate + serve, optional public links
- **Atlas-first** deployment supported

## Quickstart

1) Create `.env` from example:
```bash
cp .env.example .env
```

2) Set in .env:

MONGO_URI (Atlas)

OPENAI_API_KEY

JWT_SECRET

3) Run:
```bash
docker compose up -d --build
```
3) Open:

http://localhost:8000/health

http://localhost:8000/docs

# WebSocket

Connect: ws://localhost:8000/ws

### Send:
```json
{"action":"auth","token":"<ACCESS_TOKEN>"}
{"action":"assistant","job_id":"a1","message":"Hello"}
{"action":"list_conversations","limit":20}
```
