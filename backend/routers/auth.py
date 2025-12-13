from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from datetime import timedelta
from database import get_session
from models import Admin
from auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash, verify_password
from config import settings
from ldap_service import ldap_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    # 1. Try Local Admin (Bootstrap)
    # For the first run, if no admins exist, we might want a bootstrap admin.
    # But for now, let's assume we use LDAP or a pre-seeded admin.
    
    # 1. Bootstrap Admin: REMOVED.
    # Logic moved to main.py "on_startup" to avoid Race Conditions and Performance hit on every login.

    # 2. Try LDAP Auth
    # 2. Try LDAP Auth
    # Fix: Enable LDAP Authentication with status check
    ldap_status = ldap_service.verify_user(form_data.username, form_data.password)
    
    if ldap_status == "SUCCESS":
        # If LDAP auth succeeds, we ensure the user exists in our local admin table (cache)
        # so they can have a role, etc.
        statement = select(Admin).where(Admin.username == form_data.username)
        user = session.exec(statement).first()
        if not user:
            # Auto-provision LDAP user as admin
            user = Admin(
                username=form_data.username,
                hashed_password=get_password_hash(form_data.password), # Cache current password
                role="viewer" # Default role (Least Privilege)
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            # Update cached password just in case
            user.hashed_password = get_password_hash(form_data.password)
            session.add(user)
            session.commit()
            
        # Proceed to token generation
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    elif ldap_status == "INVALID_CREDENTIALS":
        # Security Fix: If LDAP denies explicit credentials, do NOT fall back to local DB.
        # This prevents using old cached passwords if the user is still in AD but password changed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password (LDAP)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # If "NOT_FOUND" or "ERROR", fall through to DB Check
    # This allows local-only admins (NOT_FOUND in AD) to login.
    # And allows cached login if AD is down (ERROR).
    
    # 3. DB Auth (Fallback/Cache)
    statement = select(Admin).where(Admin.username == form_data.username)
    user = session.exec(statement).first()
    
    # Mock Auth for Prototype if user exists (or if we just created 'admin')
    # Timing Attack Fix: Always run verify_password
    # Mock Auth for Prototype if user exists (or if we just created 'admin')
    # Timing Attack Fix: Always run verify_password
    if not user:
        # Dummy verification to consume same time
        # Use a consistent dummy hash to avoid recalculating it every time, but generated securely or standard
        # For simplicity and security, we can use a fixed valid hash derived from a constant if needed, 
        # but recalculating a hash on startup is better. 
        # Here we use a safe fallback.
        dummy_hash = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWrn96pzwLO3.wS5x0.k.F.eZ./W." # Keep structure but acknowledge it's dummy
        await run_in_threadpool(verify_password, form_data.password, dummy_hash)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Bug Fix: Run CPU-bound bcrypt in threadpool to prevent blocking async loop
    try:
        is_correct_password = await run_in_threadpool(verify_password, form_data.password, user.hashed_password)
    except ValueError:
        # malicious or corrupted hash in DB
        is_correct_password = False
    
    if not is_correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
