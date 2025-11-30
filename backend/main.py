from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import create_db_and_tables
from .routers import management, agent

app = FastAPI(title="ZE-SilentSync Manager", version="0.1.0")

# CORS Configuration
origins = [
    "http://localhost:5173",  # Vite default
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

app.include_router(management.router)
app.include_router(agent.router)

@app.get("/")
def read_root():
    return {"message": "ZLDAP Install Manager API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
