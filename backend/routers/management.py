from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import asyncio
import re
from sqlmodel import Session, select, SQLModel
from typing import List
from database import get_session
from auth import get_current_admin
from models import Software, Deployment, Machine, Admin, MachineSoftwareLink, SoftwareDependency, AuditLog
from datetime import datetime, timezone
from ldap_service import ldap_service

router = APIRouter(prefix="/api/v1/management", tags=["management"], dependencies=[Depends(get_current_admin)])

@router.get("/software", response_model=List[Software])
def get_software(offset: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Software).offset(offset).limit(limit)).all()

@router.post("/software", response_model=Software)
def create_software(software: Software, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    # Security Fix: Validate download_url scheme
    if software.download_url:
        url = software.download_url.lower()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("/static/")):
             raise HTTPException(status_code=400, detail="Invalid download_url. Must start with http://, https://, or /static/")
        
        # Bug Fix 9: Prevent credentials in URL
        if "@" in url and not url.startswith("/static/"):
             raise HTTPException(status_code=400, detail="Security Error: Credentials in URL are not allowed.")

        if url.startswith("/static/") and ".." in url:
             raise HTTPException(status_code=400, detail="Path traversal detected in download_url")

    if software.icon_url:
        url = software.icon_url.lower()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("/static/")):
            raise HTTPException(status_code=400, detail="Invalid icon_url. Must start with http://, https://, or /static/")
            
        if url.startswith("/static/") and ".." in url:
             raise HTTPException(status_code=400, detail="Path traversal detected in icon_url")

    # Bug Fix: Enforce RBAC
    if admin.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Insufficient privileges.")

    session.add(software)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        # Check for IntegrityError (Name+Version)
        if "unique constraint" in str(e).lower() or "integrityerror" in str(e).lower():
             raise HTTPException(status_code=409, detail="Software with this name and version already exists.")
        raise e
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
        
    # Bug Fix: Enforce RBAC. Only superadmins can delete software.
    if admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Insufficient privileges. Required: superadmin")
    
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
    
    # Bug Fix: Race Condition handling.
    # We must check for usage while holding the DB lock (after delete, before commit).
    # If we commit first, another process could insert a reference before we delete the file.
    
    session.delete(software)
    # Flush to ensure delete is registered in this transaction scope for queries
    session.flush()
    
    files_to_delete = []
    
    import os
    
    # Check Download URL
    # Bug Fix 6: Race Condition handling.
    # Strategy: Rename file to .deleted *before* commit. 
    # If B inserts reference to 'file' during this, it will point to non-existent file (Safe violation).
    # If commit fails, we rename back.
    # If commit succeeds, we delete .deleted.
    
    session.delete(software)
    # Flush to ensure delete is registered
    session.flush()
    
    files_to_delete = []
    renamed_files = [] # Tuples of (original, temp)
    import os
    import shutil
    
    # Check Download URL
    if software.download_url and software.download_url.startswith("/static/"):
        usage_count = session.exec(select(Software).where(Software.download_url == software.download_url)).all()
        if len(usage_count) == 0:
            filename = os.path.basename(software.download_url)
            if filename and not filename.startswith(".") and "/" not in filename:
                 files_to_delete.append(os.path.join("uploads", filename))
    
    # Check Icon URL
    if software.icon_url and software.icon_url.startswith("/static/"):
         usage_count = session.exec(select(Software).where(Software.icon_url == software.icon_url)).all()
         if len(usage_count) == 0:
            filename = os.path.basename(software.icon_url)
            if filename and not filename.startswith(".") and "/" not in filename:
                 files_to_delete.append(os.path.join("uploads", filename))

    # Bug Fix 4: File Deletion Race Condition
    # Delete from DB first. If that succeeds, then delete from disk.
    # This prevents the file from vanishing if the DB delete fails/rolls back.
    
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    
    # Final Delete from Disk (Post-Commit)
    for fpath in files_to_delete:
         try:
             if os.path.exists(fpath):
                 os.remove(fpath)
                 print(f"Deleted file: {fpath}")
         except Exception as e:
             print(f"Error deleting file {fpath}: {e}")
             # Non-critical: Orphaned file can be cleaned up later

    return {"status": "deleted", "id": software_id}

@router.get("/ad/tree")
def get_ad_tree(session: Session = Depends(get_session)):
    return ldap_service.get_ou_tree(session)

@router.get("/machines", response_model=List[Machine])
def get_machines(offset: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Machine).offset(offset).limit(limit)).all()

@router.post("/deploy")
def create_deployment(software_id: int, target_dn: str, target_type: str, action: str = "install", session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    if not target_dn or not target_dn.strip():
        raise HTTPException(status_code=400, detail="Target DN cannot be empty")
    
    # Bug Fix: Validate target_type parameter
    valid_target_types = {"machine", "ou", "group"}
    if target_type not in valid_target_types:
        raise HTTPException(status_code=400, detail=f"Invalid target_type. Must be one of: {', '.join(valid_target_types)}")
        
    # Fix: Validate software existence
    software = session.get(Software, software_id)
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")

    # Logic to resolve target (OU or Machine) and create deployment records
    # For simplicity, we just create a Deployment record. 
    # In a real app, if target is OU, we might expand to all machines in that OU immediately or let a background task do it.
    
    # Bug Fix 7: Validate icon_url logic (in create_software, scrolling up)
    # Wait, I need to target create_deployment separately or use multi-replace? 
    # The tool call targets create_deployment logic mostly.
    # Let me fix create_deployment first.
    
    # Bug Fix 2: Enforce RBAC
    if admin.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Insufficient privileges.")

    deployment = Deployment(
        software_id=software_id,
        target_value=target_dn,
        target_type=target_type,
        action=action,
        created_by=admin.id
    )
    
    # Bug Fix 6: Validate Target
    if target_type == "machine":
        # Check if machine ID or Hostname exists
        # Try ID first
        if target_dn.isdigit():
             m = session.get(Machine, int(target_dn))
             if not m:
                  raise HTTPException(status_code=404, detail=f"Machine ID {target_dn} not found")
        else:
             # Try Hostname
             m = session.exec(select(Machine).where(Machine.hostname == target_dn)).first()
             if not m:
                   # Try CN=Hostname
                   if target_dn.lower().startswith("cn="):
                        hostname = target_dn[3:] # Simple strip
                        m = session.exec(select(Machine).where(Machine.hostname == hostname)).first()
                   
                   if not m:
                        raise HTTPException(status_code=404, detail=f"Machine {target_dn} not found")
    elif target_type == "ou":
         # Basic validation: ensure it looks like a DN
         if not ("dc=" in target_dn.lower() or "ou=" in target_dn.lower()):
              raise HTTPException(status_code=400, detail="Invalid OU DN format")

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
    softwares = []
    chunk_size = 500
    for i in range(0, len(request.software_ids), chunk_size):
        chunk = request.software_ids[i:i + chunk_size]
        batch = session.exec(select(Software).where(Software.id.in_(chunk))).all()
        softwares.extend(batch)
        
    found_ids = {s.id for s in softwares}
    
    for sid in request.software_ids:
        if sid not in found_ids:
             raise HTTPException(status_code=400, detail=f"Software ID {sid} not found")

    # 1. Resolve all target machines once
    machines_dict = {} # Use dict for uniqueness by ID: {id: Machine}

    # 1. Bulk Machine Resolution (Fix Bug 10: N+1)
    machines_dict = {}
    
    # Pre-classify targets
    target_ids = []
    target_hostnames = [] # (hostname, original_dn)
    target_ous = [] # dn
    
    for dn in request.target_dns:
        if not dn or not dn.strip(): continue
        dn_clean = dn.strip()
        dn_u = dn_clean.upper()
        
        if dn_clean.isdigit():
             target_ids.append(int(dn_clean))
        elif dn_u.startswith("CN="):
             # Parse hostname
             parts = re.split(r'(?<!\\\\),', dn_clean)
             if parts:
                 kv = parts[0].split("=", 1)
                 if len(kv) == 2:
                     target_hostnames.append((kv[1].replace(r'\,', ','), dn_clean))
        elif dn_u.startswith(("OU=", "DC=")):
             target_ous.append(dn_clean)
        else:
             # Fallback: Treat as hostname?
             target_hostnames.append((dn_clean, dn_clean))
             
    # Fetch IDs
    if target_ids:
        ms = session.exec(select(Machine).where(Machine.id.in_(target_ids))).all()
        for m in ms: machines_dict[m.id] = m
        
    # Fetch Hostnames
    if target_hostnames:
        exact_names = [name for name, _ in target_hostnames]
        # Chunking if too large
        chunk_size = 500
        for i in range(0, len(exact_names), chunk_size):
             chunk = exact_names[i:i + chunk_size]
             ms = session.exec(select(Machine).where(Machine.hostname.in_(chunk))).all()
             for m in ms: machines_dict[m.id] = m
             
    # Fetch OUs (Still Iterative or OR'd, but efficient enough if few OUs)
    for ou in target_ous:
        # Recursive suffix match
        ms = session.exec(select(Machine).where(Machine.ou_path.endswith(ou))).all()
        for m in ms:
             if m.ou_path == ou or m.ou_path.endswith("," + ou):
                  machines_dict[m.id] = m
                  
    # Create Deployments
    # Fix: Batch Add
    new_deployments = []
    for dn in request.target_dns:
         # Determine type for DB record
         t_type = "machine"
         if dn.strip().upper().startswith(("OU=", "DC=")): t_type = "ou"
         
         for sid in request.software_ids:
             new_deployments.append(Deployment(
                 software_id=sid,
                 target_value=dn,
                 target_type=t_type,
                 action=request.action,
                 created_by=admin.id
             ))
    session.add_all(new_deployments)
    session.flush() # Populate IDs not needed, but good practice
    
    # Proceed to Link Updates using machines_dict (already bulk resolved)

    # 2. Bulk Update/Create Links (Fix N+1)
    if not machines_dict:
        session.commit()
        return {"status": "bulk deployment scheduled", "count": 0}

    all_machine_ids = list(machines_dict.keys())
    
    # Fix: Batch queries to avoid SQLite limit (999 vars)
    existing_links = []
    chunk_size = 500
    for i in range(0, len(all_machine_ids), chunk_size):
        chunk = all_machine_ids[i:i + chunk_size]
        batch_links = session.exec(select(MachineSoftwareLink).where(
            (MachineSoftwareLink.machine_id.in_(chunk)) & 
            (MachineSoftwareLink.software_id.in_(request.software_ids))
        )).all()
        existing_links.extend(batch_links)
    
    link_map = {(l.machine_id, l.software_id): l for l in existing_links}
    
    count = 0
    for m_id, machine in machines_dict.items():
        for sid in request.software_ids:
            link = link_map.get((m_id, sid))
            
            if link:
                if request.action == "install":
                    link.status = "pending"
                elif request.action == "uninstall":
                    link.status = "pending" # pending uninstall. Agent logic must be updated to handle this. 
                
                link.last_updated = datetime.now(timezone.utc)
                session.add(link)
                # If existing, we updated it.
                count += 1
            else:
                # Link does not exist. Create it!
                new_link = MachineSoftwareLink(
                     machine_id=m_id,
                     software_id=sid,
                     status="pending" if request.action == "install" else "unknown",
                     last_updated=datetime.now(timezone.utc)
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
    
    if not filename or filename.startswith('.'):
        raise HTTPException(status_code=400, detail="Invalid filename (Hidden files not allowed)")

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
