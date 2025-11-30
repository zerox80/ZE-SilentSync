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
    
    # 1. Get all deployments potentially relevant
    # In a real app with many deployments, we would filter in SQL.
    # Here we fetch all and filter in python for logic clarity (OU matching).
    all_deployments = session.exec(select(Deployment)).all()
    
    for dep in all_deployments:
        is_target = False
        
        # Target Check
        if dep.target_type == "machine" and dep.target_value == str(machine.id):
            is_target = True
        elif dep.target_type == "ou":
            # Simple string containment for OU path (e.g. "CN=PC,OU=Sales,DC=..." contains "OU=Sales")
            # In production, use proper LDAP DN parsing.
            if dep.target_value in machine.ou_path:
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
