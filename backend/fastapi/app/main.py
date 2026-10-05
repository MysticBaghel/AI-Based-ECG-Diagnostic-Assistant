from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title="Major Project API",
    version="0.1.0",
    description=f"Running in '{settings.fastapi_env}' mode.",
)

# The Vite dev server runs on a different port, which makes it a separate
# origin, so the browser needs these headers to read responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness probe used by the frontend to check the backend is up."""
    return {"status": "ok", "service": "fastapi"}
