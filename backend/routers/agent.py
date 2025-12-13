from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select, or_
from datetime import datetime, timedelta, timezone
from database import get_session
from models import Machine, Deployment, Software, AgentLog
from auth import verify_agent_token
import secrets
import re
import threading
from config import settings

# Thread Safety Lock for Rate Limiters
_rate_limit_lock = threading.Lock()

def get_client_ip(req: Request) -> str:
    """
    Robust client IP extraction.
    If TRUST_PROXY_HEADERS is enabled, prefers X-Real-IP, then X-Forwarded-For (first IP).
    Otherwise falls back to direct client host.
    """
    if settings.TRUST_PROXY_HEADERS:
        # Prefer X-Real-IP
        real_ip = req.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        
        # Then X-Forwarded-For
        # Standard format: client, proxy1, proxy2
        # We want the client (first one) if we trust the chain.
        fwd = req.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
            
    return req.client.host if req.client else "unknown"

router = APIRouter(prefix="/api/v1/agent", tags=["agent"], dependencies=[Depends(verify_agent_token)])

from pydantic import BaseModel, Field

class HeartbeatRequest(BaseModel):
    hostname: str = Field(..., max_length=255)
    mac_address: str = Field(..., max_length=17)
    os_info: str = Field(..., max_length=100)

@router.post("/heartbeat")
def heartbeat(
    request: Request,
    data: HeartbeatRequest,
    session: Session = Depends(get_session)
):
    try:
        hostname = data.hostname
        mac_address = data.mac_address.lower() # Bug Fix: Normalize MAC Case
        os_info = data.os_info
        
        # Bug Fix 3: Rate Limiting for New Machine Creation (DoS Protection)
        # We limit specific MACs or IPs?
        # Limiting by IP for anonymous requests is good.
        # Simple In-Memory Limiter
        
        client_ip = get_client_ip(request)
        
        # Global limiters should be outside function, but for simplicity/module scope:
        if not hasattr(heartbeat, "rate_limit_store"):
             heartbeat.rate_limit_store = {}
             heartbeat.cleanup_time = datetime.now(timezone.utc)
             
        # Cleanup every minute
        now = datetime.now(timezone.utc)
        
        # Thread Safety for Global Limiters
        with _rate_limit_lock:
            if (now - heartbeat.cleanup_time).total_seconds() > 60:
                 heartbeat.rate_limit_store = {}
                 # Fix Bug 3: Clear creation store to prevent memory leak
                 if hasattr(heartbeat, "creation_limit_store"):
                     heartbeat.creation_limit_store = {}
                 heartbeat.cleanup_time = now
            
            # Rate Limit Key: Use MAC Address for Heartbeat (Fix NAT Issue)
            # Only use IP if MAC is missing (unlikely here) or for Creation logic
            limit_key = mac_address if mac_address else client_ip
            
            current_count = heartbeat.rate_limit_store.get(limit_key, 0)
            # Bug Fix 7: Stricter Rate Limit (100/min instead of 2000)
            if current_count > 100: 
                 raise HTTPException(status_code=429, detail="Rate limit exceeded")
            heartbeat.rate_limit_store[limit_key] = current_count + 1
        
        # Find or create machine
        statement = select(Machine).where(Machine.mac_address == mac_address)
        machine = session.exec(statement).first()
        
        from config import settings
        
        # Determine OU Path
        # Determine OU Path
        ou_path = "Unknown"
        if settings.AGENT_ONLY:
            ou_path = f"OU=Agents,{settings.AD_BASE_DN}"
        else:
            # Resolve for new machines or explicit unknown
            should_resolve = False
            if not machine:
                should_resolve = True
            elif machine.ou_path == "Unknown":
                should_resolve = True
            else:
                ou_path = machine.ou_path
                
            if should_resolve:
                from ldap_service import ldap_service
                ou_path = ldap_service.resolve_machine_ou(hostname, session)
    
        if not machine:
            # Check if hostname already exists (to prevent Unique Constraint Error)
            statement_host = select(Machine).where(Machine.hostname == hostname)
            machine_by_host = session.exec(statement_host).first()
            
            # Bug Fix 3: Strict Rate Limit for Creation
            # Store creation counts separately
            if not hasattr(heartbeat, "creation_limit_store"):
                 heartbeat.creation_limit_store = {}
            
            client_ip = get_client_ip(request)
            with _rate_limit_lock:
                created_count = heartbeat.creation_limit_store.get(client_ip, 0)
                if created_count > 5: # Max 5 new machines per minute per IP
                     print(f"DoS Protection: Blocking machine creation from {client_ip}")
                     raise HTTPException(status_code=429, detail="Registration Rate Limit Exception")
                heartbeat.creation_limit_store[client_ip] = created_count + 1
            
            if machine_by_host:
                # Machine exists with different MAC -> Prevent Hijacking unless explicit admin action?
                # Fix: Handle collision by renaming instead of DoS/Blocking
                suffix = secrets.token_hex(2)
                new_hostname = f"{hostname}-dup-{suffix}"
                print(f"Hostname conflict for {hostname}. Renaming to {new_hostname}")
                hostname = new_hostname
                
                # Now create with new hostname
                machine = Machine(
                    hostname=hostname, 
                    mac_address=mac_address, 
                    os_info=os_info,
                    last_seen=datetime.now(timezone.utc),
                    ou_path=ou_path
                )
                session.add(machine)
            else:
                # New Machine
                machine = Machine(
                    hostname=hostname, 
                    mac_address=mac_address, 
                    os_info=os_info,
                    last_seen=datetime.now(timezone.utc),
                    ou_path=ou_path
                )
                session.add(machine)
        else:
            # Machine found by MAC
            
            # SECURITY FIX: Verify Machine Token if it exists
            if machine.api_key:
                token_header = request.headers.get("X-Machine-Token")
                # Handle case where header might be missing or different
                if not token_header or not secrets.compare_digest(token_header, machine.api_key):
                     print(f"SECURITY ALERT: Invalid Machine Token for heartbeat from {mac_address}")
                     raise HTTPException(status_code=403, detail="Invalid Machine Token")

            machine_by_host = None  # Initialize to avoid NameError
            if machine.hostname != hostname:
                # Hostname changed. Check if new hostname is already taken.
                statement_host = select(Machine).where(Machine.hostname == hostname)
                machine_by_host = session.exec(statement_host).first()
                
            if machine_by_host:
                    # Hostname collision! 
                    # Fix: Handle collision by renaming instead of DoS
                    suffix = secrets.token_hex(2) 
                    new_hostname = f"{hostname}-dup-{suffix}"
                    print(f"SECURITY WARNING: Machine {machine.mac_address} tried to change hostname to {hostname}, which is claimed. Renaming to {new_hostname}")
                    hostname = new_hostname
                    # Continue with new hostname
                    
                    # OLD LOGIC REMOVED security fix
                    # session.delete(machine) ...
            
        # Update machine details
            machine.last_seen = datetime.now(timezone.utc)
            machine.hostname = hostname
            machine.os_info = os_info
            # Ip Address Security / IDOR prep
            # Bug Fix 1: Trust X-Forwarded-For ONLY if configured (Security)
            # Use unified helper
            resolved_ip = get_client_ip(request)
            
            if resolved_ip:
                machine.ip_address = resolved_ip
                 
            # Fix: Always update OU path to keep it fresh from AD/Logic
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
            # Bug 3 Fix: Handle IntegrityError explicitly for Hostname Collision
            # and implement retry logic.
            session.rollback()
            from sqlalchemy.exc import IntegrityError
            
            if isinstance(e, IntegrityError) or "unique constraint" in str(e).lower():
                print(f"WARNING: Race condition detected for {hostname} (IntegrityError). Retrying with new hostname...")
                
                # Retry logic with collision handling
                # Retry logic with collision handling
                try: 
                    # 1. Generate new unique hostname suffix
                    suffix = secrets.token_hex(2)
                    new_hostname = f"{data.hostname}-dup-{suffix}"
                    
                    # 2. Check if conflict was MAC or Hostname
                    # Try to find by MAC again
                    existing_machine = session.exec(select(Machine).where(Machine.mac_address == mac_address)).first()
                    
                    if existing_machine:
                         # It was an update collision or someone inserted same MAC
                         machine = existing_machine
                         # Fix: Do NOT rename the existing valid machine.
                         # Just accept it and update last_seen.
                         # machine.hostname = new_hostname  <-- REMOVED
                         machine.last_seen = datetime.now(timezone.utc)
                         machine.ou_path = ou_path
                         # Merge/Add
                         session.add(machine)
                    else:
                        # It was a hostname collision on INSERT, and MAC is unused
                        machine_retry = Machine(
                            hostname=new_hostname, # New Name
                            mac_address=mac_address, 
                            os_info=os_info,
                            last_seen=datetime.now(timezone.utc),
                            ou_path=ou_path,
                            api_key=secrets.token_urlsafe(32) # New Token
                        )
                        session.add(machine_retry)
                        # Fix: Ensure logic uses machine_retry
                        machine = machine_retry

                    session.commit()
                    session.refresh(machine)
                    print(f"Recovered from race condition. New hostname: {machine.hostname}")
                    
                except Exception as retry_e:
                     # If it fails again, we give up to avoid infinite loops
                     print(f"ERROR: Failed to recover from race condition: {retry_e}")
                     # Try to fetch state one last time? No, just fail.
                     session.rollback()
                     
                     # Final attempt: Just return what's in DB if exists
                     machine = session.exec(select(Machine).where(Machine.mac_address == mac_address)).first()
                     if not machine:
                          raise HTTPException(status_code=409, detail="Hostname collision could not be resolved.")
        
        # --- Task Resolution Logic ---
        current_time = datetime.now(timezone.utc)
        tasks = []
        processed_software_ids = set()
        
        print(f"DEBUG: Heartbeat for {hostname} (ID: {machine.id}). Checking deployments...")
    
        # 1. Get relevant deployments
        # Optimization: Filter IN SQL
        
        # Calculate parent OUs for OU targeting
        parent_ous = []
        if machine.ou_path and machine.ou_path != "Unknown":
            # Bug Fix 4: Use robust DN parsing instead of naive Regex
            from ldap3.utils.dn import parse_dn
            
            # parse_dn returns list of (attr, val, sep)
            # CN=PC1,OU=Sales,DC=example -> [('CN', 'PC1', ','), ('OU', 'Sales', ','), ('DC', 'example', '')]
            # We want headers.
            
            parsed = parse_dn(machine.ou_path)
            # Skip first RDN (CN=Hostname) if it matches hostname usually?
            # Existing logic was: "If start with CN=, skip first part"
            
            start_idx = 0
            if parsed and parsed[0][0].upper() == 'CN':
                 start_idx = 1
            
            # Reconstruct parents
            # Iterating from start_idx to end
            
            from ldap3.utils.dn import escape_dn_chars
            
            # Helper to reconstruct DN from parsed slice
            def reconstruct(p_slice):
                parts_str = []
                for attr, val, sep in p_slice:
                    # We must re-escape value
                    parts_str.append(f"{attr}={escape_dn_chars(val)}")
                return ",".join(parts_str)
            
            # Create all suffix permutations
            # e.g. OU=Sales,DC=example and DC=example
            
            current_slice = parsed[start_idx:]
            
            # Full parent DN
            if current_slice:
                 parent_ous.append(reconstruct(current_slice))
            
            # Walk up logic (add each parent)
            # "Simpler: we want all suffixes"
            # If current_slice is [OU=A, OU=B, DC=C]
            # We want [OU=A,OU=B,DC=C], [OU=B,DC=C], [DC=C]
            
            for i in range(1, len(current_slice)):
                 suffix = current_slice[i:]
                 if suffix:
                      parent_ous.append(reconstruct(suffix))
                
            # Old regex loop removed
            pass
        
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
    
        # Fix N+1: Fetch all links at once
        dep_software_ids = [d.software_id for d in potential_deployments]
        existing_links = session.exec(select(MachineSoftwareLink).where(
            (MachineSoftwareLink.machine_id == machine.id) &
            (MachineSoftwareLink.software_id.in_(dep_software_ids))
        )).all()
        # Map by software_id
        links_map = {link.software_id: link for link in existing_links}

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
                     
                # Robust OU matching
                if machine.ou_path and dep.target_value:
                    machine_dn = machine.ou_path.lower()
                    target_dn = dep.target_value.lower()
                    
                    # Fix: Ensure we match if target_dn is a parent in the machine_dn tree
                    # e.g. target="cn=computers,dc=local" and machine="cn=pc1,cn=computers,dc=local"
                    if machine_dn.endswith(target_dn):
                         # Ensure boundary correctness (comma or exact match)
                        if machine_dn == target_dn or machine_dn.endswith("," + target_dn):
                            is_target = True
            
            if not is_target:
                # print(f"DEBUG: Dep {dep.id} skipped. Not target. (Type: {dep.target_type}, Val: {dep.target_value})")
                continue
    
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
                # Use pre-fetched map
                link = links_map.get(dep.software_id)
                
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
                            if datetime.now(timezone.utc) - link.last_updated < timedelta(hours=1):
                                continue
                            # Else, fall through to retry
                # If Action is UNINSTALL
                elif dep.action == "uninstall":
                    # If not installed, we can't uninstall (or we assume success)
                    if not link:
                         continue
                    
                    if link.status in ["installed", "pending"]:
                         pass # Proceed
                    elif link.status == "failed":
                         # Retry uninstall after 1 hour similar to install
                         if datetime.now(timezone.utc) - link.last_updated < timedelta(hours=1):
                             continue
                         print(f"DEBUG: Retrying uninstall for {dep.software.name}")
                    else:
                         # print(f"DEBUG: Dep {dep.id} skipped. Not installed/failed, can't uninstall.")
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
        if not token_header or not secrets.compare_digest(token_header, machine.api_key):
             print(f"SECURITY WARNING: Invalid Machine Token for {data.mac_address}. Token mismatch.")
             raise HTTPException(status_code=403, detail="Invalid Machine Token")
    else:
        # This prevents spooling attacks on unprovisioned machines.
        print(f"SECURITY WARNING: Ack received for machine {data.mac_address} without API Key.")
        raise HTTPException(status_code=403, detail="Machine not provisioned (No API Key)")

    # FIX Bug 5: Validate Deployment Target
    # Check if deployment actually belongs to this machine
    is_valid_target = False
    if deployment.target_type == "machine":
        # ID or Hostname Check
        if deployment.target_value == str(machine.id):
             is_valid_target = True
        elif deployment.target_value.lower() == machine.hostname.lower():
             is_valid_target = True
        elif deployment.target_value.lower().startswith(f"cn={machine.hostname}".lower()):
             # Basic loose check, similar to agent logic
             is_valid_target = True
    elif deployment.target_type == "ou":
        # Check if machine matches OU logic
        if machine.ou_path:
             # Logic from heartbeat, simplified:
             # Does machine.ou_path end with deployment target value?
             m_dn = machine.ou_path.lower()
             t_dn = deployment.target_value.lower()
             if m_dn.endswith(t_dn):
                 if m_dn == t_dn or m_dn.endswith("," + t_dn):
                     is_valid_target = True

    if not is_valid_target:
         print(f"SECURITY ALERT: Machine {machine.hostname} tried to ACK deployment {deployment.id} which targets {deployment.target_value} ({deployment.target_type})")
         raise HTTPException(status_code=403, detail="Deployment does not target this machine")

    # Update or Create Link
    from models import MachineSoftwareLink
    
    link = session.exec(select(MachineSoftwareLink).where(
        (MachineSoftwareLink.machine_id == machine.id) &
        (MachineSoftwareLink.software_id == deployment.software_id)
    )).first()
    
    if not link:
        try:
             # Double check inside potential lock if we had one, but strict DB constraint is better.
             # Since we can't change schema easily, we'll try/except
             link = MachineSoftwareLink(
                machine_id=machine.id,
                software_id=deployment.software_id,
                status="pending"
             )
             session.add(link)
             session.flush() # Force insert to check constraint
        except Exception: # Handling IntegrityError
             session.rollback()
             # Re-fetch
             link = session.exec(select(MachineSoftwareLink).where(
                (MachineSoftwareLink.machine_id == machine.id) &
                (MachineSoftwareLink.software_id == deployment.software_id)
             )).first()
    
    if data.status == "success":
        if deployment.action == "uninstall":
            link.status = "uninstalled" # or delete the link? Keeping it as history is better.
        else:
            link.status = "installed"
            if deployment.software:
                link.installed_version = deployment.software.version
    else:
        link.status = "failed"
        
    link.last_updated = datetime.now(timezone.utc)
    session.add(link)
    session.commit()
    
    return {"status": "acknowledged"}


class LogRequest(BaseModel):
    mac_address: str = Field(..., max_length=17)
    level: str  # INFO, WARN, ERROR
    message: str = Field(..., max_length=2000)

@router.post("/log")
def log_agent_event(
    request: Request,
    data: LogRequest,
    session: Session = Depends(get_session)
):
    # Validate log level
    valid_levels = {"INFO", "WARN", "ERROR"}
    level = data.level.upper()
    if level not in valid_levels:
        # Fix: Reject invalid levels or Warn? Rejecting is better for API contract.
        # level = "INFO" 
        raise HTTPException(status_code=400, detail=f"Invalid log level. Must be one of {valid_levels}")
    
    statement = select(Machine).where(Machine.mac_address == data.mac_address)
    machine = session.exec(statement).first()
    
    if machine:
        # IDOR Security Check
        # IDOR Security Check
        # Use unified helper
        current_ip = get_client_ip(request)

        if machine.ip_address and current_ip:
            if machine.ip_address != current_ip:
                print(f"SECURITY WARNING: Log attempt for {data.mac_address} from unauthorized IP {current_ip} (Expected {machine.ip_address}). Allowing for robustness.")
                # We do NOT return ignored anymore, just log warning.
                pass
        
        # Bug 5 Fix: Rate Limiting
        # Limit logs to 60 per minute per machine
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        
        # Optimized Count Query
        statement = select(func.count()).where(
            (AgentLog.machine_id == machine.id) & 
            (AgentLog.timestamp > cutoff)
        )
        log_count_res = session.exec(statement).first()
        # Extract scalar
        log_count = log_count_res if isinstance(log_count_res, int) else log_count_res[0] if log_count_res else 0
        
        if log_count >= 60:
            print(f"Rate Limit Exceeded for {machine.hostname}")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Security: Verify Machine Token
        token_header = request.headers.get("X-Machine-Token")
        if machine.api_key:
             if not token_header or not secrets.compare_digest(token_header, machine.api_key):
                 print(f"SECURITY WARNING: Invalid Machine Token for log from {data.mac_address}")
                 # For logs, we might just drop it, but 403 is safer to signal misconfig
                 return {"status": "ignored", "reason": "invalid_token"}
                 
        log = AgentLog(machine_id=machine.id, level=level, message=data.message)
        session.add(log)
        session.commit()
    return {"status": "logged"}
