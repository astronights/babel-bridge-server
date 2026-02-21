from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import create_indexes
from routers import auth, rooms, conversations


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure MongoDB indexes exist
    await create_indexes()
    yield
    # Shutdown: nothing to clean up (Motor closes connections automatically)


app = FastAPI(
    title="BabelBridge API",
    description="AI-powered multiplayer language learning backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — update origins for your frontend domain in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(conversations.router)


@app.get("/", tags=["Health"])
async def health():
    return {"status": "ok", "service": "Babel Bridge API"}
