from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import asyncio
import re
from sqlmodel import Session, select, SQLModel
from typing import List
from database import get_session
from auth import get_current_admin
from models import Software, Deployment, Machine, Admin, MachineSoftwareLink, SoftwareDependency, AuditLog
from datetime import datetime
from ldap_service import ldap_service

router = APIRouter(prefix="/api/v1/management", tags=["management"], dependencies=[Depends(get_current_admin)])

@router.get("/software", response_model=List[Software])
def get_software(session: Session = Depends(get_session)):
    return session.exec(select(Software)).all()

@router.post("/software", response_model=Software)
def create_software(software: Software, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    session.add(software)
    session.commit()
    session.refresh(software)
    
    # Audit Log
    session.add(AuditLog(
        admin_id=admin.id, 
        action="create_software", 
        target=software.name, 
        details=f"Version: {software.version}",
        level="INFO"
    ))
    session.commit()
    
    return software

@router.delete("/software/{software_id}")
def delete_software(software_id: int, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    software = session.get(Software, software_id)
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")
    
    # Audit Log Entry
    log = AuditLog(admin_id=admin.id, action="delete_software", target=software.name, level="INFO")
    session.add(log) # Add early, commit later

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

    # Delete the actual file from disk
    import os
    files_to_delete = []
    
    # Bug 2 Fix: Check for file usage AFTER the commit to ensure we see the updated state
    # We must delete the software record and commit to update the state for the check below.
    session.delete(software)
    session.commit()
    
    # Ideally, we would rely on a garbage collector process, but for this scope:
    if software.download_url and software.download_url.startswith("/static/"):
        filename = os.path.basename(software.download_url)
        safe_filename = os.path.basename(filename)
        file_path = os.path.join("uploads", safe_filename)
        
        # Check if ANY software still uses this URL (since we just deleted ours, count should be 0 if unique)
        usage_count = session.exec(select(Software).where(Software.download_url == software.download_url)).all()
        
        if len(usage_count) == 0:
             files_to_delete.append(file_path)
        else:
             print(f"Skipping file deletion for {file_path} (Still used by {len(usage_count)} others)")

    if software.icon_url and software.icon_url.startswith("/static/"):
        icon_filename = os.path.basename(software.icon_url)
        safe_icon_filename = os.path.basename(icon_filename)
        icon_path = os.path.join("uploads", safe_icon_filename)
        
        usage_count = session.exec(select(Software).where(Software.icon_url == software.icon_url)).all()
        
        if len(usage_count) == 0:
            files_to_delete.append(icon_path)
        else:
             print(f"Skipping icon deletion for {icon_path} (Still used by {len(usage_count)} others)")

    # Execute deletion
    for fpath in files_to_delete:
        if os.path.exists(fpath) and os.path.isfile(fpath):
            try:
                os.remove(fpath)
                print(f"Deleted file: {fpath}")
            except Exception as e:
                print(f"Error deleting file {fpath}: {e}")

    return {"status": "deleted", "id": software_id}

@router.get("/ad/tree")
def get_ad_tree(session: Session = Depends(get_session)):
    return ldap_service.get_ou_tree(session)

@router.get("/machines", response_model=List[Machine])
def get_machines(session: Session = Depends(get_session)):
    return session.exec(select(Machine)).all()

@router.post("/deploy")
def create_deployment(software_id: int, target_dn: str, target_type: str, action: str = "install", session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    if not target_dn or not target_dn.strip():
        raise HTTPException(status_code=400, detail="Target DN cannot be empty")
        
    # Fix: Validate software existence
    software = session.get(Software, software_id)
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")

    # Logic to resolve target (OU or Machine) and create deployment records
    # For simplicity, we just create a Deployment record. 
    # In a real app, if target is OU, we might expand to all machines in that OU immediately or let a background task do it.
    
    deployment = Deployment(
        software_id=software_id,
        target_value=target_dn,
        target_type=target_type,
        action=action,
        created_by=admin.id
    )
    session.add(deployment)
    
    # Audit Log
    session.add(AuditLog(
        admin_id=admin.id,
        action="create_deployment",
        target=target_dn,
        details=f"Software: {software.name}, Action: {action}",
        level="INFO"
    ))
    
    session.commit()
    session.refresh(deployment)
    return {"status": "deployment scheduled"}

class BulkDeploymentRequest(SQLModel):
    software_ids: List[int]
    target_dns: List[str]
    action: str = "install"
    force_reinstall: bool = False

@router.post("/deploy/bulk")
def create_bulk_deployment(request: BulkDeploymentRequest, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    # Fix: Validate all software IDs first
    # Fix: Validate all software IDs first (Batch check)
    softwares = session.exec(select(Software).where(Software.id.in_(request.software_ids))).all()
    found_ids = {s.id for s in softwares}
    
    for sid in request.software_ids:
        if sid not in found_ids:
             raise HTTPException(status_code=400, detail=f"Software ID {sid} not found")

    # 1. Resolve all target machines once
    machines_dict = {} # Use dict for uniqueness by ID: {id: Machine}

    for target_dn in request.target_dns:
        if not target_dn or not target_dn.strip():
            continue

        # Heuristic for target type
        target_upper = target_dn.strip().upper()
        target_type = "machine" # default fallback
        
        if target_dn.strip().isdigit():
             target_type = "machine"
        elif target_upper.startswith("CN="):
            # Check if machine exists with this DN or Hostname
            machine_chk = session.exec(select(Machine).where(Machine.ou_path.endswith(target_dn) | (Machine.hostname == target_dn))).first()
            if machine_chk:
                 target_type = "machine"
            else:
                target_type = "ou"
        elif target_upper.startswith(("OU=", "DC=")):
            target_type = "ou"

        # Create Deployment Records (one per Soft x Target combo)
        for software_id in request.software_ids:
            deployment = Deployment(
                software_id=software_id,
                target_value=target_dn,
                target_type=target_type,
                action=request.action,
                created_by=admin.id
            )
            session.add(deployment)
        
        # Resolve Machines for Link Updates
        found_machines = []
        if target_type == "machine":
             try:
                machine_id = int(target_dn)
                found = session.get(Machine, machine_id)
                if found: found_machines.append(found)
             except ValueError:
                # Try Hostname match (CN=...)
                hostname_candidate = target_dn
                if target_upper.startswith("CN="):
                    parts = re.split(r'(?<!\\),', target_dn)
                    if parts:
                        kv = parts[0].split("=", 1)
                        if len(kv) == 2:
                            hostname_candidate = kv[1].replace(r'\,', ',')
                
                ms = session.exec(select(Machine).where(Machine.hostname == hostname_candidate)).all()
                if not ms and hostname_candidate != target_dn:
                     ms = session.exec(select(Machine).where(Machine.hostname == target_dn)).all()
                found_machines.extend(ms)

        else: # target_type == "ou"
             # Fetch all machines in this OU (recursive suffix check)
             candidates = session.exec(select(Machine).where(Machine.ou_path.endswith(target_dn))).all()
             for m in candidates:
                 if m.ou_path == target_dn or m.ou_path.endswith("," + target_dn):
                     found_machines.append(m)

        for m in found_machines:
            machines_dict[m.id] = m

    # 2. Bulk Update/Create Links (Fix N+1)
    if not machines_dict:
        session.commit()
        return {"status": "bulk deployment scheduled", "count": 0}

    all_machine_ids = list(machines_dict.keys())
    
    # Fetch existing links for (Any Machine in List) AND (Any Software in Request)
    existing_links = session.exec(select(MachineSoftwareLink).where(
        (MachineSoftwareLink.machine_id.in_(all_machine_ids)) & 
        (MachineSoftwareLink.software_id.in_(request.software_ids))
    )).all()
    
    link_map = {(l.machine_id, l.software_id): l for l in existing_links}
    
    count = 0
    for m_id, machine in machines_dict.items():
        for sid in request.software_ids:
            link = link_map.get((m_id, sid))
            
            if link:
                if request.action == "install":
                    link.status = "pending"
                elif request.action == "uninstall":
                    link.status = "installed" 
                
                link.last_updated = datetime.utcnow()
                session.add(link)
                # If existing, we updated it.
                count += 1
            else:
                # Link does not exist. Create it!
                new_link = MachineSoftwareLink(
                     machine_id=m_id,
                     software_id=sid,
                     status="pending" if request.action == "install" else "unknown",
                     last_updated=datetime.utcnow()
                 )
                session.add(new_link)
                count += 1

    # Audit Log
    session.add(AuditLog(
        admin_id=admin.id,
        action="create_bulk_deployment",
        target=f"{len(request.target_dns)} targets",
        details=f"Software IDs: {request.software_ids}, Machines Affected: {len(machines_dict)} ({count} links)",
        level="INFO"
    ))
            
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
    # Fix: Agent only supports .msi and .exe directly. Archives (.zip, .7z) cause crashes.
    ALLOWED_EXTENSIONS = {'.msi', '.exe'}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension. Only .msi, .exe are allowed.")

    file_path = os.path.join(UPLOAD_DIR, filename)
    
    # Fix: Prevent overwrites by auto-renaming
    MAX_FILE_SIZE = 500 * 1024 * 1024
    
    # Bug 4 Fix: TOCTOU - Use Exclusive Creation (mode='xb') inside a loop to prevent overwrites
    # This guarantees that WE created the file and no one else exists with that name.
    
    final_file_path = None
    file_handle = None
    
    try:
        # Retry loop for name generation
        for _ in range(5):
             # Try unsafe name first if not exists, then timestamped
             # Logic refactored: Always try to get a handle.
             try:
                 # Check if we need a timestamp
                 # We try 'file_path' (original name) first? 
                 # Or just generated logic?
                 # Let's try the constructed 'file_path' first.
                 
                 # But we need atomic open.
                 # Removed os.path.exists check to prevent TOCTOU. "xb" is atomic.
                 file_handle = open(file_path, "xb")
                 final_file_path = file_path
                 break
             except FileExistsError:
                 # Generate new name
                 from datetime import datetime
                 import secrets
                 timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                 # random suffix to be sure
                 suffix = secrets.token_hex(4)
                 name, extension = os.path.splitext(filename)
                 # Reconstruct filename and path for next calc
                 filename = f"{name}_{timestamp}_{suffix}{extension}"
                 file_path = os.path.join(UPLOAD_DIR, filename)
                 continue
                 
        if not file_handle:
             raise HTTPException(status_code=500, detail="Could not generate unique filename.")
             
        # Write to the exclusive handle
        try:
            size = 0
            while True:
                chunk = await file.read(1024 * 1024) # 1MB chunks
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                     file_handle.close()
                     os.remove(final_file_path)
                     raise HTTPException(status_code=413, detail="File too large (Max 500MB)")
                file_handle.write(chunk)
        finally:
            file_handle.close()

    except HTTPException:
        raise
    except Exception as e:
        if final_file_path and os.path.exists(final_file_path):
            os.remove(final_file_path)
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
        
    # Return the URL where it can be accessed
    # In production, this should be a full URL or relative to a configured base
    return {"filename": filename, "url": f"/static/{filename}"}
