from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select, SQLModel
from typing import List
from database import get_session
from auth import get_current_admin
from models import Software, Deployment, Machine, Admin
from ldap_service import ldap_service

router = APIRouter(prefix="/api/v1/management", tags=["management"], dependencies=[Depends(get_current_admin)])

@router.get("/software", response_model=List[Software])
def get_software(session: Session = Depends(get_session)):
    return session.exec(select(Software)).all()

@router.post("/software", response_model=Software)
def create_software(software: Software, session: Session = Depends(get_session)):
    session.add(software)
    session.commit()
    session.refresh(software)
    return software

@router.get("/ad/tree")
def get_ad_tree(session: Session = Depends(get_session)):
    return ldap_service.get_ou_tree(session)

@router.get("/machines", response_model=List[Machine])
def get_machines(session: Session = Depends(get_session)):
    return session.exec(select(Machine)).all()

@router.post("/deploy")
def create_deployment(software_id: int, target_dn: str, target_type: str, session: Session = Depends(get_session)):
    # Logic to resolve target (OU or Machine) and create deployment records
    # For simplicity, we just create a Deployment record. 
    # In a real app, if target is OU, we might expand to all machines in that OU immediately or let a background task do it.
    
    deployment = Deployment(
        software_id=software_id,
        target_value=target_dn,
        target_type=target_type
    )
    session.add(deployment)
    session.commit()
    session.add(deployment)
    session.commit()
    return {"status": "deployment scheduled"}

class BulkDeploymentRequest(SQLModel):
    software_ids: List[int]
    target_dns: List[str]

@router.post("/deploy/bulk")
def create_bulk_deployment(request: BulkDeploymentRequest, session: Session = Depends(get_session)):
    count = 0
    for software_id in request.software_ids:
        for target_dn in request.target_dns:
            # Simple heuristic for target type, similar to frontend
            target_type = "ou" if "OU=" in target_dn else "machine"
            
            deployment = Deployment(
                software_id=software_id,
                target_value=target_dn,
                target_type=target_type
            )
            session.add(deployment)
            count += 1
            
    session.commit()
    return {"status": "bulk deployment scheduled", "count": count}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), session: Session = Depends(get_session)):
    import shutil
    import os
    import re
    
    UPLOAD_DIR = "uploads"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Sanitize filename
    # 1. Use basename to strip any directory components
    filename = os.path.basename(file.filename)
    # 2. Remove any non-alphanumeric characters except . _ - to be extra safe
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Return the URL where it can be accessed
    # In production, this should be a full URL or relative to a configured base
    return {"filename": filename, "url": f"/static/{filename}"}
