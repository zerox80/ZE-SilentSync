from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select, or_
from datetime import datetime, timedelta
from database import get_session
from models import Machine, Deployment, Software, AgentLog
from auth import verify_agent_token
import secrets
import re

router = APIRouter(prefix="/api/v1/agent", tags=["agent"], dependencies=[Depends(verify_agent_token)])

from pydantic import BaseModel

class HeartbeatRequest(BaseModel):
    hostname: str
    mac_address: str
    os_info: str

@router.post("/heartbeat")
def heartbeat(
    request: Request,
    data: HeartbeatRequest,
    session: Session = Depends(get_session)
):
    try:
        hostname = data.hostname
        mac_address = data.mac_address
        os_info = data.os_info
        # Find or create machine
        statement = select(Machine).where(Machine.mac_address == mac_address)
        machine = session.exec(statement).first()
        
        from config import settings
        
        # Determine OU Path
        ou_path = "Unknown"
        if settings.AGENT_ONLY:
            ou_path = "OU=Agents,DC=local"
    
        if not machine:
            # Check if hostname already exists (to prevent Unique Constraint Error)
            statement_host = select(Machine).where(Machine.hostname == hostname)
            machine_by_host = session.exec(statement_host).first()
            
            if machine_by_host:
                # Machine exists with different MAC -> Prevent Hijacking unless explicit admin action?
                # For now, we BLOCK it to fix the security hole.
                print(f"SECURITY WARNING: Hostname {hostname} collision. Request MAC: {mac_address}, Known MAC: {machine_by_host.mac_address}")
                raise HTTPException(status_code=409, detail="Hostname conflict. Contact Administrator.")
            else:
                # New Machine
                machine = Machine(
                    hostname=hostname, 
                    mac_address=mac_address, 
                    os_info=os_info,
                    last_seen=datetime.utcnow(),
                    ou_path=ou_path
                )
                session.add(machine)
        else:
            # Machine found by MAC
            
            # SECURITY FIX: Verify Machine Token if it exists
            if machine.api_key:
                token_header = request.headers.get("X-Machine-Token")
                # Handle case where header might be missing or different
                if not token_header or token_header != machine.api_key:
                     print(f"SECURITY ALERT: Invalid Machine Token for heartbeat from {mac_address}")
                     raise HTTPException(status_code=403, detail="Invalid Machine Token")

            if machine.hostname != hostname:
                # Hostname changed. Check if new hostname is already taken.
                statement_host = select(Machine).where(Machine.hostname == hostname)
                machine_by_host = session.exec(statement_host).first()
                
                if machine_by_host:
                    # Hostname collision! 
                    # WE MUST BLOCK THIS too to prevent renaming into an existing target.
                    print(f"SECURITY WARNING: Machine {machine.mac_address} tried to change hostname to {hostname}, which is already claimed by {machine_by_host.mac_address}")
                    raise HTTPException(status_code=409, detail="Hostname conflict. Contact Administrator.")
                    
                    # OLD LOGIC REMOVED security fix
                    # session.delete(machine) ...
            
            machine.last_seen = datetime.utcnow()
            machine.hostname = hostname
            machine.os_info = os_info
            # Ip Address Security / IDOR prep
            if request.client and request.client.host:
                 machine.ip_address = request.client.host
                 
            if settings.AGENT_ONLY:
                 machine.ou_path = ou_path
            session.add(machine)
        
        # --- Token Rotation / Provisioning ---
        if not machine.api_key:
            # Generate new token for this machine
            machine.api_key = secrets.token_urlsafe(32)
            session.add(machine)
            print(f"DEBUG: Generated new api_key for {machine.hostname}")
        
        try:
            session.commit()
            session.refresh(machine)
        except Exception as e:
            # Handle potential race conditions (IntegrityError)
            session.rollback()
            # If it was a unique constraint violation (e.g. parallel heartbeat), 
            # we can just ignore it for this heartbeat or fetch again.
            print(f"WARNING: Database commit failed (likely race condition): {e}")
            # Try to fetch fresh state to return tasks
            machine = session.exec(select(Machine).where(Machine.mac_address == mac_address)).first()
            if not machine:
                 raise HTTPException(status_code=500, detail="Could not recover machine state after race condition")
        
        # --- Task Resolution Logic ---
        current_time = datetime.utcnow()
        tasks = []
        processed_software_ids = set()
        
        print(f"DEBUG: Heartbeat for {hostname} (ID: {machine.id}). Checking deployments...")
    
        # 1. Get relevant deployments
        # Optimization: Filter IN SQL
        
        # Calculate parent OUs for OU targeting
        parent_ous = []
        if machine.ou_path and machine.ou_path != "Unknown":
            # Simple DN parsing
            # CN=PC1,OU=Sales,DC=example -> [OU=Sales,DC=example, DC=example]
            # Split by comma (naive, but usually works for AD unless comma in name)
            # Fix: Use regex to handle escaped commas
            parts = re.split(r'(?<!\\),', machine.ou_path)
            # If start with CN=, skip first part
            start_idx = 1 if parts[0].upper().startswith("CN=") else 0
            
            # Reconstruct parents
            current_dn = machine.ou_path
            if start_idx == 1:
                # Remove CN=...
                current_dn = ",".join(parts[1:])
                parent_ous.append(current_dn)
                
            # Now iterate upwards?
            # Actually, standard AD structure: OU=A,OU=B,DC=C
            # We want all suffixes.
            # simpler:
            parts = re.split(r'(?<!\\),', current_dn)
            for i in range(len(parts)):
                 # Only if it looks like a valid component (OU= or DC=)
                 dn_candidate = ",".join(parts[i:])
                 if dn_candidate:
                     parent_ous.append(dn_candidate)
        
        # Deployment Target Values we care about:
        # 1. Machine ID
        # 2. Hostname
        # 3. CN=Hostname (prefix)
        # 4. Any parent OU
        
        target_machine_values = [str(machine.id), machine.hostname, f"CN={machine.hostname}"]
        
        statement = select(Deployment).where(
            or_(
                (Deployment.target_type == "machine") & (Deployment.target_value.in_(target_machine_values)),
                (Deployment.target_type == "ou") & (Deployment.target_value.in_(parent_ous))
            )
        )
        potential_deployments = session.exec(statement).all()
        
        # Sort deployments to prioritize Machine (Specific) over OU (General)
        # Assuming 'target_type' is "machine" or "ou". 
        # We want "machine" first.
        potential_deployments.sort(key=lambda d: 0 if d.target_type == "machine" else 1)
        
        print(f"DEBUG: Found {len(potential_deployments)} potential deployments.")
        
        from models import MachineSoftwareLink
    
        for dep in potential_deployments:
            # Deduplication: If we already have a task for this software in this batch, skip.
            if dep.software_id in processed_software_ids:
                continue
    
            is_target = False
            
            # Target Check
            if dep.target_type == "machine":
                # Check ID Match (strict) OR Hostname Match (loose) OR DN Match (loose)
                # The backend might store just ID, or DN.
                if dep.target_value == str(machine.id):
                    is_target = True
                elif dep.target_value.lower() == machine.hostname.lower():
                     is_target = True
                elif dep.target_value.lower().startswith(f"cn={machine.hostname}".lower()):
                     # Check if it is exact match or comma follows (to avoid prefix matching like PC1 matching PC10)
                     val = dep.target_value.lower()
                     prefix = f"cn={machine.hostname}".lower()
                     if val == prefix or val.startswith(prefix + ","):
                         is_target = True
                     
            elif dep.target_type == "ou":
                # Robust OU matching
                if machine.ou_path and dep.target_value:
                    machine_dn = machine.ou_path.lower()
                    target_dn = dep.target_value.lower()
                    
                    if machine_dn.endswith(target_dn):
                        if machine_dn == target_dn or machine_dn.endswith("," + target_dn):
                            is_target = True
            
            if not is_target:
                # print(f"DEBUG: Dep {dep.id} skipped. Not target. (Type: {dep.target_type}, Val: {dep.target_value})")
                continue
    
            if is_target:
                # Schedule Check
                if dep.schedule_start and current_time < dep.schedule_start:
                    print(f"DEBUG: Dep {dep.id} skipped. Schedule start future.")
                    continue
                if dep.schedule_end and current_time > dep.schedule_end:
                    print(f"DEBUG: Dep {dep.id} skipped. Schedule end passed.")
                    continue
                    
                # Software Check
                if dep.software:
                    # CHECK IF ALREADY INSTALLED / UNINSTALLED
                    link = session.exec(select(MachineSoftwareLink).where(
                        (MachineSoftwareLink.machine_id == machine.id) &
                        (MachineSoftwareLink.software_id == dep.software_id)
                    )).first()
                    
                    # If Action is INSTALL
                    if dep.action == "install":
                        # Stop infinite loops: Skip if installed.
                        # For FAILED, we should allow retry after some time (e.g., 1 hour)
                        if link:
                            if link.status == "installed":
                                # VERSION CHECK FIX
                                installed_ver = link.installed_version
                                target_ver = dep.software.version
                                if installed_ver and installed_ver == target_ver:
                                     # Exact same version installed
                                     continue
                                else:
                                     print(f"DEBUG: Update detected for {dep.software.name}. Installed: {installed_ver}, Target: {target_ver}")
                                     # Proceed to install (update)
                                     pass
                            elif link.status == "failed":
                                # Retry after 1 hour
                                if datetime.utcnow() - link.last_updated < timedelta(hours=1):
                                    continue
                                # Else, fall through to retry
                    # If Action is UNINSTALL
                    elif dep.action == "uninstall":
                        # If not installed, we can't uninstall (or we assume success)
                        if not link or link.status != "installed":
                            print(f"DEBUG: Dep {dep.id} skipped. Not installed, can't uninstall.")
                            continue
    
                    download_url = dep.software.download_url
                    if download_url and download_url.startswith("/"):
                        # Construct absolute URL using secure BASE_URL
                        # Fix: Host Header Injection validation
                        base_url = settings.BASE_URL.rstrip("/")
                        download_url = f"{base_url}{download_url}"
    
                    tasks.append({
                        "id": dep.id,
                        "type": dep.action, # install or uninstall
                        "software_name": dep.software.name,
                        "download_url": download_url,
                        "silent_args": dep.software.silent_args,
                        "is_msi": dep.software.is_msi
                    })
                    processed_software_ids.add(dep.software_id)
                
        print(f"DEBUG: Returning {len(tasks)} tasks.")
        return {"status": "ok", "tasks": tasks, "machine_token": machine.api_key}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        import traceback
        error_msg = f"ERROR: Heartbeat failed for {data.hostname}: {e}\n{traceback.format_exc()}"
        print(error_msg)
        # LOG TO STDOUT ONLY
        pass
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

class AckRequest(BaseModel):
    task_id: int
    status: str # success, failed
    message: str = ""
    mac_address: str

@router.post("/ack")
def acknowledge_task(
    data: AckRequest,
    request: Request,
    session: Session = Depends(get_session)
):
    # Security: Verify Machine Token if exists
    token_header = request.headers.get("X-Machine-Token")
    # task_id is the deployment_id
    deployment = session.get(Deployment, data.task_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Find Machine
    statement = select(Machine).where(Machine.mac_address == data.mac_address)
    machine = session.exec(statement).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
        
    if machine.api_key:
        if token_header != machine.api_key:
             print(f"SECURITY WARNING: Invalid Machine Token for {data.mac_address}. Expected {machine.api_key[:5]}... got {token_header}")
             raise HTTPException(status_code=403, detail="Invalid Machine Token")

    # Update or Create Link
    from models import MachineSoftwareLink
    
    link = session.exec(select(MachineSoftwareLink).where(
        (MachineSoftwareLink.machine_id == machine.id) &
        (MachineSoftwareLink.software_id == deployment.software_id)
    )).first()
    
    if not link:
        link = MachineSoftwareLink(
            machine_id=machine.id,
            software_id=deployment.software_id,
            status="pending"
        )
        session.add(link)
    
    if data.status == "success":
        if deployment.action == "uninstall":
            link.status = "uninstalled" # or delete the link? Keeping it as history is better.
        else:
            link.status = "installed"
            if deployment.software:
                link.installed_version = deployment.software.version
    else:
        link.status = "failed"
        
    link.last_updated = datetime.utcnow()
    session.add(link)
    session.commit()
    
    return {"status": "acknowledged"}


@router.post("/log")
def log_agent_event(
    request: Request,
    mac_address: str,
    level: str,
    message: str,
    session: Session = Depends(get_session)
):
    statement = select(Machine).where(Machine.mac_address == mac_address)
    machine = session.exec(statement).first()
    
    if machine:
        # IDOR Security Check
        # If we have an IP recorded, we can check it.
        # This is a basic check.
        if machine.ip_address and request.client and request.client.host:
            if machine.ip_address != request.client.host:
                print(f"SECURITY WARNING: Log attempt for {mac_address} from unauthorized IP {request.client.host} (Expected {machine.ip_address})")
                # We could raise 403, or just drop the log silently to not leak info.
                return {"status": "ignored"}
                
        # Security: Verify Machine Token
        token_header = request.headers.get("X-Machine-Token")
        if machine.api_key:
             if token_header != machine.api_key:
                 print(f"SECURITY WARNING: Invalid Machine Token for log from {mac_address}")
                 # For logs, we might just drop it, but 403 is safer to signal misconfig
                 return {"status": "ignored", "reason": "invalid_token"}
                 
        log = AgentLog(machine_id=machine.id, level=level, message=message)
        session.add(log)
        session.commit()
    return {"status": "logged"}
