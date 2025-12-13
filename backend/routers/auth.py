from fastapi import APIRouter, Depends, HTTPException, status
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
    
    # 1. Bootstrap Admin (if no admins exist)
    # Check if any admin exists
    if not session.exec(select(Admin)).first():
         # Create bootstrap admin
         # Bug fix: Do not use SECRET_KEY as password.
         initial_password = settings.ADMIN_PASSWORD
         if not initial_password:
             import secrets
             initial_password = secrets.token_urlsafe(16)
             print(f"WARNING: ADMIN_PASSWORD not set. Generated bootstrap password: {initial_password}")
             
         hashed_pwd = get_password_hash(initial_password)
         admin = Admin(username="admin", role="superadmin", hashed_password=hashed_pwd)
         session.add(admin)
         session.commit()
    
    # 2. Try LDAP Auth
    # In a real scenario, we would verify against AD here.
    # if ldap_service.verify_user(form_data.username, form_data.password):
    #    ... sync user to DB ...
    
    # 3. DB Auth (Fallback/Cache)
    statement = select(Admin).where(Admin.username == form_data.username)
    user = session.exec(statement).first()
    
    # Mock Auth for Prototype if user exists (or if we just created 'admin')
    if not user:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(form_data.password, user.hashed_password):
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
