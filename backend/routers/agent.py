from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from datetime import datetime
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
        machine = Machine(
            hostname=hostname, 
            mac_address=mac_address, 
            os_info=os_info,
            last_seen=datetime.utcnow(),
            ou_path=ou_path
        )
        session.add(machine)
    else:
        machine.last_seen = datetime.utcnow()
        machine.hostname = hostname
        machine.os_info = os_info
        if settings.AGENT_ONLY:
             machine.ou_path = ou_path
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
    
    from models import MachineSoftwareLink

    for dep in potential_deployments:
        is_target = False
        
        # Target Check
        if dep.target_type == "machine":
            # Already filtered by SQL, but safe to keep check
            if dep.target_value == str(machine.id):
                is_target = True
        elif dep.target_type == "ou":
            # Robust OU matching
            machine_dn = machine.ou_path.lower()
            target_dn = dep.target_value.lower()
            
            if machine_dn.endswith(target_dn):
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
                # CHECK IF ALREADY INSTALLED
                link = session.exec(select(MachineSoftwareLink).where(
                    (MachineSoftwareLink.machine_id == machine.id) &
                    (MachineSoftwareLink.software_id == dep.software_id)
                )).first()
                
                if link and link.status == "installed":
                    continue

                download_url = dep.software.download_url
                if download_url.startswith("/"):
                    # Construct absolute URL from request
                    base_url = str(request.base_url).rstrip("/")
                    download_url = f"{base_url}{download_url}"

                tasks.append({
                    "id": dep.id,
                    "type": "install",
                    "software_name": dep.software.name,
                    "download_url": download_url,
                    "silent_args": dep.software.silent_args,
                    "is_msi": dep.software.is_msi
                })
            
    return {"status": "ok", "tasks": tasks}

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
