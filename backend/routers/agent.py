from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from datetime import datetime, timedelta
from database import get_session
from models import Machine, Deployment, Software, AgentLog
from auth import verify_agent_token

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
                # Machine exists with different MAC -> Update MAC
                print(f"WARNING: Hostname {hostname} found with different MAC. Updating MAC from {machine_by_host.mac_address} to {mac_address}.")
                machine = machine_by_host
                machine.mac_address = mac_address
                machine.last_seen = datetime.utcnow()
                machine.os_info = os_info
                if settings.AGENT_ONLY:
                     machine.ou_path = ou_path
                session.add(machine)
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
            if machine.hostname != hostname:
                # Hostname changed. Check if new hostname is already taken.
                statement_host = select(Machine).where(Machine.hostname == hostname)
                machine_by_host = session.exec(statement_host).first()
                
                if machine_by_host:
                    # Hostname collision! 
                    # Scenario: We have Machine A (hostname=Target) and Machine B (mac=Current).
                    # We want to be Machine A, but with Machine B's MAC.
                    # We must delete Machine B (current record) and update Machine A.
                    print(f"WARNING: Merging machine {machine.hostname} ({machine.mac_address}) into {machine_by_host.hostname} ({machine_by_host.mac_address})")
                    
                    # Delete the current machine (Machine B)
                    session.delete(machine)
                    session.flush() # Ensure deletion happens before update to avoid MAC collision if we were to swap
                    
                    # Switch to Machine A
                    machine = machine_by_host
                    machine.mac_address = mac_address # Update to new MAC
            
            machine.last_seen = datetime.utcnow()
            machine.hostname = hostname
            machine.os_info = os_info
            if settings.AGENT_ONLY:
                 machine.ou_path = ou_path
            session.add(machine)
        
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
        # Optimization: Filter by machine ID or OU type in SQL
        statement = select(Deployment).where(
            ((Deployment.target_type == "machine") & (Deployment.target_value == str(machine.id))) |
            (Deployment.target_type == "ou")
        )
        potential_deployments = session.exec(statement).all()
        print(f"DEBUG: Found {len(potential_deployments)} potential deployments.")
        
        from models import MachineSoftwareLink
    
        for dep in potential_deployments:
            # Deduplication: If we already have a task for this software in this batch, skip.
            if dep.software_id in processed_software_ids:
                continue
    
            is_target = False
            
            # Target Check
            if dep.target_type == "machine":
                # Already filtered by SQL, but safe to keep check
                if dep.target_value == str(machine.id):
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
                                continue
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
                        # Construct absolute URL from request
                        base_url = str(request.base_url).rstrip("/")
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
        return {"status": "ok", "tasks": tasks}
    except Exception as e:
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
    session: Session = Depends(get_session)
):
    # task_id is the deployment_id
    deployment = session.get(Deployment, data.task_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Find Machine
    statement = select(Machine).where(Machine.mac_address == data.mac_address)
    machine = session.exec(statement).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

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
    else:
        link.status = "failed"
        
    link.last_updated = datetime.utcnow()
    session.add(link)
    session.commit()
    
    return {"status": "acknowledged"}


@router.post("/log")
def log_agent_event(
    mac_address: str,
    level: str,
    message: str,
    session: Session = Depends(get_session)
):
    statement = select(Machine).where(Machine.mac_address == mac_address)
    machine = session.exec(statement).first()
    if machine:
        log = AgentLog(machine_id=machine.id, level=level, message=message)
        session.add(log)
        session.commit()
    return {"status": "logged"}
