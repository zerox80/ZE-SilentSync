from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import asyncio
import re
from sqlmodel import Session, select, SQLModel
from typing import List
from database import get_session
from auth import get_current_admin
from models import Software, Deployment, Machine, Admin, MachineSoftwareLink, SoftwareDependency, AuditLog, MachineRead
from datetime import datetime, timezone
from ldap_service import ldap_service

router = APIRouter(prefix="/api/v1/management", tags=["management"], dependencies=[Depends(get_current_admin)])

@router.get("/software", response_model=List[Software])
def get_software(offset: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Software).offset(offset).limit(limit)).all()

@router.post("/software", response_model=Software)
def create_software(software: Software, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):

    if software.download_url:
        url = software.download_url.lower()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("/static/")):
             raise HTTPException(status_code=400, detail="Invalid download_url. Must start with http://, https://, or /static/")
        

        from urllib.parse import urlparse
        try:
             parsed_url = urlparse(url)
             if parsed_url.username or parsed_url.password:
                  raise HTTPException(status_code=400, detail="Security Error: Credentials in URL are not allowed.")
        except Exception:
             # Fallback or pass if parsing failed (unlikely for valid http/https)
             pass

        if url.startswith("/static/") and ".." in url:
             raise HTTPException(status_code=400, detail="Path traversal detected in download_url")

    if software.icon_url:
        url = software.icon_url.lower()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("/static/")):
            raise HTTPException(status_code=400, detail="Invalid icon_url. Must start with http://, https://, or /static/")
            
        if url.startswith("/static/") and ".." in url:
             raise HTTPException(status_code=400, detail="Path traversal detected in icon_url")


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
    
    # Check Download URL
    if software.download_url and software.download_url.startswith("/static/"):
        usage_count = session.exec(select(Software).where(Software.download_url == software.download_url)).all()
        # If this is the only one (or creates a condition where count is 1 inclusive strictly before, but here we haven't deleted yet)
        # Actually session.delete is pending. 
        # Safer: Check if count <= 1 (this one).
        if len(usage_count) <= 1: 
            filename = os.path.basename(software.download_url)
            if filename and not filename.startswith(".") and "/" not in filename:
                 files_to_delete.append(os.path.join("uploads", filename))
    
    # Check Icon URL
    if software.icon_url and software.icon_url.startswith("/static/"):
         usage_count = session.exec(select(Software).where(Software.icon_url == software.icon_url)).all()
         if len(usage_count) <= 1:
            filename = os.path.basename(software.icon_url)
            if filename and not filename.startswith(".") and "/" not in filename:
                 files_to_delete.append(os.path.join("uploads", filename))

    # Perform DB Delete
    session.delete(software)
    session.flush()


    # Commit first. If that succeeds, then delete from disk.
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

@router.get("/machines", response_model=List[MachineRead])
def get_machines(offset: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    return session.exec(select(Machine).offset(offset).limit(limit)).all()

@router.post("/deploy")
def create_deployment(software_id: int, target_dn: str, target_type: str, action: str = "install", session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    if not target_dn or not target_dn.strip():
        raise HTTPException(status_code=400, detail="Target DN cannot be empty")
    

    valid_target_types = {"machine", "ou"}
    if target_type not in valid_target_types:
        raise HTTPException(status_code=400, detail=f"Invalid target_type. Must be one of: {', '.join(valid_target_types)}")
        

    software = session.get(Software, software_id)
    if not software:
        raise HTTPException(status_code=404, detail="Software not found")

    # Logic to resolve target (OU or Machine) and create deployment records
    # For simplicity, we just create a Deployment record. 
    # In a real app, if target is OU, we might expand to all machines in that OU immediately or let a background task do it.
    

    # Wait, I need to target create_deployment separately or use multi-replace? 
    # The tool call targets create_deployment logic mostly.
    # Let me fix create_deployment first.
    

    if admin.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Insufficient privileges.")

    deployment = Deployment(
        software_id=software_id,
        target_value=target_dn,
        target_type=target_type,
        action=action,
        created_by=admin.id
    )
    

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
                         parts = target_dn.split(",")
                         if parts:
                             # Extract value from CN=Value
                             kv = parts[0].split("=", 1)
                             if len(kv) == 2 and kv[0].strip().lower() == "cn":
                                 hostname = kv[1].strip()
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

@router.get("/deployments")
def get_deployments(session: Session = Depends(get_session)):
    """Get all ACTIVE/PENDING deployments (hides completed ones)."""
    from sqlalchemy.orm import joinedload
    
    # 1. Fetch all deployments
    statement = select(Deployment).options(joinedload(Deployment.software)).order_by(Deployment.created_at.desc())
    all_deployments = session.exec(statement).all()
    
    # 2. Gather targets to resolve status
    machine_targets = set()
    for dep in all_deployments:
        if dep.target_type == "machine":
            machine_targets.add(dep.target_value)
            
    # 3. Resolve targets to Machine IDs
    # Map target_value -> machine_id
    target_map = {}
    if machine_targets:
        # Check for IDs
        numeric_ids = {int(t) for t in machine_targets if t.isdigit()}
        # Check for Hostnames (approximate)
        hostnames = {t for t in machine_targets if not t.isdigit()}
        
        # Query 1: By ID
        if numeric_ids:
            ms = session.exec(select(Machine).where(Machine.id.in_(numeric_ids))).all()
            for m in ms:
                target_map[str(m.id)] = m.id
        
        # Query 2: By Hostname (or CN=...)
        # Simplifying assumption: target_value is hostname or CN=hostname
        if hostnames:
            # We can't easily bulk query partial matches.
            # But we can try to bulk query exact hostnames
            # Clean targets
            clean_hosts = set()
            clean_map = {} # clean_host -> original_target
            for h in hostnames:
                val = h.lower()
                if val.startswith("cn="):
                    val = val.split(",")[0].split("=")[1].strip()
                clean_hosts.add(val)
                clean_map[val] = h
            
            ms = session.exec(select(Machine).where(Machine.hostname.in_(clean_hosts))).all()
            for m in ms:
                h_clean = m.hostname.lower()
                # Find which original target this matches
                # If target was "TP-IT01", matches. If "CN=TP-IT01", matches.
                # In clean_map?
                # This reverse mapping is tricky if many-to-one.
                # Simple loop:
                for target_val in hostnames:
                     t_clean = target_val.lower()
                     if t_clean.startswith("cn="):
                         t_clean = t_clean.split(",")[0].split("=")[1].strip()
                     
                     if t_clean == h_clean:
                         target_map[target_val] = m.id

    # 4. Fetch Links for relevant (Machine, Software) pairs
    # Optimize: Fetch all links for these machines?
    # Or just fetch all links for the machines involved in deployments?
    resolved_machine_ids = set(target_map.values())
    
    links_map = {} # (machine_id, software_id) -> status
    
    if resolved_machine_ids:
        # Fetch status for these machines
        # We also care about the software IDs in deployments
        # But fetching all links for these machines is probably okay (hundreds not millions)
        # Better: Filter by software too?
        # Let's just fetch links for these machines.
        l_stmt = select(MachineSoftwareLink).where(MachineSoftwareLink.machine_id.in_(resolved_machine_ids))
        links = session.exec(l_stmt).all()
        for l in links:
            links_map[(l.machine_id, l.software_id)] = l.status
            
    # 5. Filter List
    result = []
    for dep in all_deployments:
        if dep.target_type == "ou":
            # Always show OU policies (they are persistent)
            result.append(dep)
        elif dep.target_type == "machine":
            m_id = target_map.get(dep.target_value)
            
            # If machine not found, show it (it's pending/error state effectively)
            if not m_id:
                result.append(dep)
                continue
                
            status = links_map.get((m_id, dep.software_id))
            
            # Logic: Hide if completed
            hide = False
            if dep.action == "install":
                if status == "installed": hide = True
            elif dep.action == "uninstall":
                if status == "uninstalled": hide = True
                
            if not hide:
                result.append(dep)
                
    # 6. Resolve Hostnames for display
    # We want to show "tp-it01" instead of "2"
    # We have target_map mapping "2" -> 2 (int ID)
    # query machines
    
    machine_ids = set()
    for dep in result:
        if dep.target_type == "machine":
            # get resolved ID
            mid = target_map.get(dep.target_value)
            if mid: machine_ids.add(mid)
            
    id_to_hostname = {}
    if machine_ids:
        ms = session.exec(select(Machine).where(Machine.id.in_(machine_ids))).all()
        for m in ms:
            id_to_hostname[m.id] = m.hostname
            
    # Format Result
    final_output = []
    for dep in result:
        target_display = dep.target_value
        if dep.target_type == "machine":
            mid = target_map.get(dep.target_value)
            if mid and mid in id_to_hostname:
                target_display = id_to_hostname[mid]
        
        final_output.append({
            "id": dep.id,
            "software_id": dep.software_id,
            "target_value": dep.target_value,
            "target_name": target_display, # NEW FIELD
            "target_type": dep.target_type,
            "action": dep.action,
            "created_at": dep.created_at.isoformat() if dep.created_at else None,
            "software": {"name": dep.software.name} if dep.software else None
        })
    return final_output

@router.delete("/deploy/clear-all")
def clear_all_deployments(session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    """Clear all pending deployments. Emergency stop for all queued tasks."""
    

    if admin.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Insufficient privileges.")
    
    # Count before deletion for response
    count = len(session.exec(select(Deployment)).all())
    
    # Delete all deployments
    session.exec(select(Deployment)).all()
    for dep in session.exec(select(Deployment)).all():
        session.delete(dep)
    
    # Audit Log
    session.add(AuditLog(
        admin_id=admin.id,
        action="clear_all_deployments",
        target="ALL",
        details=f"Cleared {count} deployments",
        level="WARNING"
    ))
    
    session.commit()
    return {"status": "cleared", "count": count}

@router.delete("/deploy/{deployment_id}")
def delete_deployment(deployment_id: int, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):
    """Delete a single deployment / cancel a pending task."""
    
    deployment = session.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Get software name for audit log before deletion
    software_name = deployment.software.name if deployment.software else f"ID:{deployment.software_id}"
    
    session.delete(deployment)
    
    # Audit Log
    session.add(AuditLog(
        admin_id=admin.id,
        action="delete_deployment",
        target=f"{software_name} -> {deployment.target_value}",
        details=f"Action: {deployment.action}",
        level="INFO"
    ))
    
    session.commit()
    return {"status": "deleted", "id": deployment_id}

class BulkDeploymentRequest(SQLModel):
    software_ids: List[int]
    target_dns: List[str]
    action: str = "install"
    force_reinstall: bool = False

@router.post("/deploy/bulk")
def create_bulk_deployment(request: BulkDeploymentRequest, session: Session = Depends(get_session), admin: Admin = Depends(get_current_admin)):


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

    # 1. Bulk Machine Resolution
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

    new_deployments = []
    for dn in request.target_dns:
         # Determine type for DB record
         t_type = "machine"
         if dn.strip().upper().startswith(("OU=", "DC=")): t_type = "ou"
         
         # Verification for machine types:
         # If it's a machine, did we find it?
         if t_type == "machine":
             # We can check if this 'dn' string maps to any resolved machine
             # Our machines_dict keys are IDs.
             # We need to check if 'dn' (which could be ID or Hostname) was successfully resolved.
             # Inverse lookup or re-check:
             # An easy way is to check if we can resolve it again from machines_dict OR
             # more efficiently: we built valid_machine_lookup earlier? No we didn't.
             # Let's simple check:
             
             found_machine = False
             
             # Case 1: ID
             if dn.strip().isdigit():
                 if int(dn.strip()) in machines_dict: found_machine = True
             
             # Case 2: ID match failed? Check hostnames?
             # machines_dict only helps if we know the ID.
             # We should iterate machines_dict to find a match if we want to be strict.
             if not found_machine:
                 dn_lower = dn.strip().lower()
                 for m in machines_dict.values():
                     if str(m.id) == dn.strip():
                         found_machine = True; break
                     if m.hostname.lower() == dn_lower:
                         found_machine = True; break
                     if m.hostname.lower() == dn_lower.replace("cn=", ""):
                         found_machine = True; break
             
             if not found_machine:
                 # Skip invalid machine target
                 continue

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

    # 2. Bulk Update/Create Links
    if not machines_dict:
        session.commit()
        return {"status": "bulk deployment scheduled", "count": 0}

    all_machine_ids = list(machines_dict.keys())
    

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
                    link.status = "pending"
            
                link.last_updated = datetime.now(timezone.utc)
                session.add(link)
                # If existing, we updated it.
                count += 1
            else:
                # Link does not exist. Create it!
                new_link = MachineSoftwareLink(
                        machine_id=m_id,
                        software_id=sid,
                        status="pending",
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

    ALLOWED_EXTENSIONS = {'.msi', '.exe'}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension. Only .msi, .exe are allowed.")

    file_path = os.path.join(UPLOAD_DIR, filename)
    

    from config import settings
    MAX_FILE_SIZE = settings.MAX_UPLOAD_SIZE
    

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
                     limit_mb = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
                     raise HTTPException(status_code=413, detail=f"File too large (Max {limit_mb}MB)")
                file_handle.write(chunk)
        finally:
            file_handle.close()

    except HTTPException:
        raise
    except Exception as e:
        # race-proof cleanup: only delete if we actually set final_file_path and it still exists
        try:
            if final_file_path and os.path.exists(final_file_path):
                os.remove(final_file_path)
        except OSError:
            # Ignore errors if file is already gone
            pass
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
        
    # Return the URL where it can be accessed
    # In production, this should be a full URL or relative to a configured base
    return {"filename": filename, "url": f"/static/{filename}"}
