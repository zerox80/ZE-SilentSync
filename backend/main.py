from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from routers import management, agent, auth

from config import settings

app = FastAPI(title="ZE-SilentSync Manager", version="0.1.0")

# CORS Configuration
origins = settings.ALLOWED_ORIGINS

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
    seed_data()

def seed_data():
    from sqlmodel import Session, select
    from database import engine
    from models import Software, Machine
    
    with Session(engine) as session:
        if not session.exec(select(Software)).first():
            print("Seeding Mock Software...")
            softwares = [
                Software(name="Google Chrome", version="120.0", download_url="https://dl.google.com/chrome/install/chrome_installer.exe", silent_args="/silent /install", is_msi=False),
                Software(name="Mozilla Firefox", version="121.0", download_url="https://download.mozilla.org/?product=firefox-msi-latest", silent_args="/qn", is_msi=True),
                Software(name="7-Zip", version="23.01", download_url="https://www.7-zip.org/a/7z2301-x64.msi", silent_args="/qn", is_msi=True),
                Software(name="VLC Media Player", version="3.0.20", download_url="https://get.videolan.org/vlc/3.0.20/win64/vlc-3.0.20-win64.exe", silent_args="/S", is_msi=False),
            ]
            for s in softwares:
                session.add(s)
            
            # Seed a Mock Machine for testing
            # Security Fix: Do NOT seed a default machine with known details in production.
            # if not session.exec(select(Machine)).first():
            #      session.add(Machine(hostname="TEST-PC-01", mac_address="00:11:22:33:44:55", os_info="Windows 11 Pro", ou_path="OU=Sales,DC=example,DC=com"))
            
            session.commit()

    # Seed Default Admin
    from models import Admin
    from auth import get_password_hash
    from config import settings
    
    with Session(engine) as session:
        if not session.exec(select(Admin)).first():
            # Fix: Do NOT fallback to SECRET_KEY. Generate a random password if not set.
            password = settings.ADMIN_PASSWORD
            
            if not password:
                import secrets
                password = secrets.token_urlsafe(12)
                print(f"WARNING: ADMIN_PASSWORD not set. Generated temporary password: {password}")
            
            print("Seeding Default Admin...")
                
            admin = Admin(
                username="admin", 
                hashed_password=get_password_hash(password),
                role="superadmin"
            )
            session.add(admin)
            session.commit()
            print("Default admin created.")

from fastapi.staticfiles import StaticFiles
import os

app.include_router(auth.router)
app.include_router(management.router)
app.include_router(agent.router)

os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploads"), name="static")

@app.get("/")
def read_root():
    return {"message": "ZLDAP Install Manager API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
