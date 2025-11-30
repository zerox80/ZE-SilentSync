from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from datetime import datetime
from ..database import get_session
from ..models import Machine, Deployment, Software, AgentLog

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

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
        machine.hostname = hostname # Update hostname if changed
        machine.os_info = os_info
        session.add(machine)
    
    session.commit()
    session.refresh(machine)
    
    # Check for pending deployments
    # Simple logic: Find deployments for this machine or its OU (not fully implemented OU resolution here for brevity)
    # We just check for deployments targeting this machine ID specifically for now
    
    # TODO: Add logic to check for OU-based deployments by matching machine.ou_path
    
    deployments = session.exec(select(Deployment).where(Deployment.target_value == str(machine.id))).all()
    
    tasks = []
    for dep in deployments:
        # In a real app, we would check if it's already installed.
        # Here we just send the task if it exists in the deployment table.
        if dep.software:
            tasks.append({
                "id": dep.id,
                "type": "install",
                "software_name": dep.software.name,
                "download_url": dep.software.download_url,
                "silent_args": dep.software.silent_args
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
