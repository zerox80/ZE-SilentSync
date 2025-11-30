from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from datetime import datetime
from database import get_session
from models import Machine, Deployment, Software, AgentLog
from auth import verify_agent_token

router = APIRouter(prefix="/api/v1/agent", tags=["agent"], dependencies=[Depends(verify_agent_token)])

@router.post("/heartbeat")
def heartbeat(
    hostname: str, 
    mac_address: str, 
    os_info: str, 
    session: Session = Depends(get_session)
):
    # Find or create machine
    statement = select(Machine).where(Machine.mac_address == mac_address)
    machine = session.exec(statement).first()
    
    if not machine:
        machine = Machine(
            hostname=hostname, 
            mac_address=mac_address, 
            os_info=os_info,
            last_seen=datetime.utcnow()
        )
        session.add(machine)
    else:
        machine.last_seen = datetime.utcnow()
        machine.hostname = hostname
        machine.os_info = os_info
        session.add(machine)
    
    session.commit()
    session.refresh(machine)
    
    # --- Task Resolution Logic ---
    current_time = datetime.utcnow()
    tasks = []
    
    # 1. Get relevant deployments
    # Optimization: Filter by machine ID or OU type in SQL
    statement = select(Deployment).where(
        ((Deployment.target_type == "machine") & (Deployment.target_value == str(machine.id))) |
        (Deployment.target_type == "ou")
    )
    potential_deployments = session.exec(statement).all()
    
    for dep in potential_deployments:
        is_target = False
        
        # Target Check
        if dep.target_type == "machine":
            # Already filtered by SQL, but safe to keep check
            if dep.target_value == str(machine.id):
                is_target = True
        elif dep.target_type == "ou":
            # Robust OU matching
            # Check if the machine's OU path ends with the target OU DN (case-insensitive)
            # This ensures we match "OU=Sales,DC=example,DC=com" with target "OU=Sales,DC=example,DC=com"
            # but NOT "OU=SalesForce,DC=..." with target "OU=Sales,DC=..."
            
            machine_dn = machine.ou_path.lower()
            target_dn = dep.target_value.lower()
            
            # Simple suffix check is better than 'in', but ideally we parse DNs.
            # For this fix, we ensure it matches as a component suffix.
            if machine_dn.endswith(target_dn):
                # Ensure boundary safety (e.g. ensure preceding char is ',' or it's exact match)
                if machine_dn == target_dn or machine_dn.endswith("," + target_dn):
                    is_target = True
                
        if is_target:
            # Schedule Check
            if dep.schedule_start and current_time < dep.schedule_start:
                continue
            if dep.schedule_end and current_time > dep.schedule_end:
                continue
                
            # Software Check
            if dep.software:
                # Dependency Check (Recursive placeholder)
                # if dep.software.dependencies: ...
                
                # Uninstall Check
                # If we had a "target_state=absent", we would send uninstall task.
                # For now, we assume Deployment means "Install".
                
                tasks.append({
                    "id": dep.id,
                    "type": "install",
                    "software_name": dep.software.name,
                    "download_url": dep.software.download_url,
                    "silent_args": dep.software.silent_args,
                    "is_msi": dep.software.is_msi
                })
            
    return {"status": "ok", "tasks": tasks}

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
