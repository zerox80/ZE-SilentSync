from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import asyncio
from sqlmodel import Session, select, SQLModel
from typing import List
from database import get_session
from auth import get_current_admin
from models import Software, Deployment, Machine, Admin, MachineSoftwareLink, SoftwareDependency
from datetime import datetime
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

@router.delete("/software/{software_id}")
def delete_software(software_id: int, session: Session = Depends(get_session)):
    software = session.get(Software, software_id)
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")
    
    # Optional: Check for existing deployments or links and decide whether to block or cascade.
    # For now, we'll just delete the software record. SQLModel/SQLAlchemy might error if foreign keys exist 
    # and cascade isn't set, but let's assume simple deletion for now or let the error bubble up.
    # Better to manually clean up if needed, but user just wants "delete".
    
    # Delete associated deployments?
    deployments = session.exec(select(Deployment).where(Deployment.software_id == software_id)).all()
    for dep in deployments:
        session.delete(dep)
        
    # Delete associated links?
    links = session.exec(select(MachineSoftwareLink).where(MachineSoftwareLink.software_id == software_id)).all()
    for link in links:
        session.delete(link)

    # Delete associated dependencies (both directions)
    dependencies = session.exec(select(SoftwareDependency).where(
        (SoftwareDependency.software_id == software_id) | 
        (SoftwareDependency.dependency_id == software_id)
    )).all()
    for dep in dependencies:
        session.delete(dep)

    session.delete(software)
    session.commit()
    return {"status": "deleted", "id": software_id}

@router.get("/ad/tree")
def get_ad_tree(session: Session = Depends(get_session)):
    return ldap_service.get_ou_tree(session)

@router.get("/machines", response_model=List[Machine])
def get_machines(session: Session = Depends(get_session)):
    return session.exec(select(Machine)).all()

@router.post("/deploy")
def create_deployment(software_id: int, target_dn: str, target_type: str, action: str = "install", session: Session = Depends(get_session)):
    # Logic to resolve target (OU or Machine) and create deployment records
    # For simplicity, we just create a Deployment record. 
    # In a real app, if target is OU, we might expand to all machines in that OU immediately or let a background task do it.
    
    deployment = Deployment(
        software_id=software_id,
        target_value=target_dn,
        target_type=target_type,
        action=action
    )
    session.add(deployment)
    session.commit()
    session.refresh(deployment)
    return {"status": "deployment scheduled"}

class BulkDeploymentRequest(SQLModel):
    software_ids: List[int]
    target_dns: List[str]
    action: str = "install"
    force_reinstall: bool = False

@router.post("/deploy/bulk")
def create_bulk_deployment(request: BulkDeploymentRequest, session: Session = Depends(get_session)):
    count = 0
    for software_id in request.software_ids:
        for target_dn in request.target_dns:
            # Simple heuristic for target type, similar to frontend
            # OUs start with OU= or DC=, Machines start with CN= (usually)
            # Improved heuristic: OUs explicitly start with OU= or DC=, but we must be careful.
            # Computers often start with CN=...OU=...
            # If it starts with OU= or DC=, it is likely an OU root.
            # If it starts with CN=, it is a machine.
            target_upper = target_dn.strip().upper()
            if target_upper.startswith("CN="):
                target_type = "machine"
            elif target_upper.startswith(("OU=", "DC=")):
                target_type = "ou"
            else:
                # Fallback to simple machine ID (integer) assumption if no DN structure
                 target_type = "machine"
            
            deployment = Deployment(
                software_id=software_id,
                target_value=target_dn,
                target_type=target_type,
                action=request.action
            )
            session.add(deployment)
            
            # FORCE RE-INSTALL LOGIC
            if request.force_reinstall and request.action == "install":
                # Efficiently reset links
                if target_type == "machine":
                     # For machine targets, target_dn is expected to be the machine ID or hostname. 
                     machines = []
                     try:
                        machine_id = int(target_dn)
                        found = session.get(Machine, machine_id)
                        if found:
                             machines = [found]
                     except ValueError:
                        # Maybe it is a DN or Hostname?
                        # Try to match hostname directly or extract from CN=...
                        hostname_candidate = target_dn
                        if target_dn.upper().strip().startswith("CN="):
                            # Extract CN value: CN=Hostname,OU=...
                            parts = target_dn.split(",")
                            if parts:
                                kv = parts[0].split("=")
                                if len(kv) == 2:
                                    hostname_candidate = kv[1]
                        
                        machines = session.exec(select(Machine).where(Machine.hostname == hostname_candidate)).all()
                        if not machines and hostname_candidate != target_dn:
                             # Try raw match
                             machines = session.exec(select(Machine).where(Machine.hostname == target_dn)).all()
                else: 
                     # OU Target matches if it ends with the DN, but we must ensure it's a component boundary.
                     # e.g. "OU=Sales" matches "...CN=PC1,OU=Sales" but NOT "...OU=PreSales"
                     # Simple check: Ends with ",target_dn" OR is exactly "target_dn"
                     machines = []
                     # We can't easily do this purely in SQL with 'endswith' correctly without regex support in DB.
                     # So we fetch potential matches and filter in python OR assume users provide valid DNs.
                     # Let's try a slightly safer SQL approach if possible, or just strict suffix check.
                     # Assuming basic structure:
                     
                     # Fetch all machines (or filter roughly)
                     candidates = session.exec(select(Machine).where(Machine.ou_path.endswith(target_dn))).all()
                     for m in candidates:
                         if m.ou_path == target_dn or m.ou_path.endswith("," + target_dn):
                             machines.append(m)

                for machine in machines:
                    if not machine: continue
                    
                    link = session.exec(select(MachineSoftwareLink).where(
                        (MachineSoftwareLink.machine_id == machine.id) &
                        (MachineSoftwareLink.software_id == software_id)
                    )).first()
                    
                    if link:
                        link.status = "pending"
                        link.last_updated = datetime.utcnow()
                        session.add(link)
                        
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

    # Security: Validate extension
    ALLOWED_EXTENSIONS = {'.msi', '.exe', '.zip', '.7z'}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension. Only .msi, .exe, .zip, .7z are allowed.")

    file_path = os.path.join(UPLOAD_DIR, filename)
    
    # Run blocking I/O in a worker thread and ensure the target file handle is closed.
    def _write_upload():
        with open(file_path, "wb") as out_file:
            shutil.copyfileobj(file.file, out_file)

    await asyncio.to_thread(_write_upload)
        
    # Return the URL where it can be accessed
    # In production, this should be a full URL or relative to a configured base
    return {"filename": filename, "url": f"/static/{filename}"}
