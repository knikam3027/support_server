from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.mongodb import connect_db, close_db, get_db
from app.routes import incidents, analysis, chat
from app.services.vector_search import rebuild_index


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    db = get_db()
    await rebuild_index(db)
    yield
    await close_db()


app = FastAPI(
    title="AI Incident Resolution Copilot",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents.router, prefix="/api", tags=["Incidents"])
app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])


@app.get("/")
async def root():
    return {"message": "AI Incident Resolution Copilot API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
