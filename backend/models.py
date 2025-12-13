from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship

# --- Join Tables ---
class MachineSoftwareLink(SQLModel, table=True):
    machine_id: Optional[int] = Field(default=None, foreign_key="machine.id", primary_key=True)
    software_id: Optional[int] = Field(default=None, foreign_key="software.id", primary_key=True)
    status: str = Field(default="pending") # pending, installing, installed, failed
    installed_version: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class SoftwareDependency(SQLModel, table=True):
    software_id: Optional[int] = Field(default=None, foreign_key="software.id", primary_key=True)
    dependency_id: Optional[int] = Field(default=None, foreign_key="software.id", primary_key=True)

# --- Main Models ---

class Admin(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str = Field(default="admin") # admin, viewer
    hashed_password: str
    last_login: Optional[datetime] = None

class Machine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hostname: str = Field(index=True, unique=True)
    mac_address: str = Field(index=True, unique=True)
    ip_address: Optional[str] = None
    os_info: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    ou_path: str = Field(default="Unknown") # Cached OU path from AD
    api_key: Optional[str] = None # Per-machine unique token
    
    deployments: List["Deployment"] = Relationship(back_populates="machine")

class Software(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    version: str
    description: Optional[str] = None
    download_url: str
    silent_args: str # e.g. /S /silent
    uninstall_args: Optional[str] = None
    is_msi: bool = Field(default=False)
    icon_url: Optional[str] = None
    
    deployments: List["Deployment"] = Relationship(back_populates="software")

class Deployment(SQLModel, table=True):
    """
    Represents a target state: "This software SHOULD be on this machine/OU"
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: Optional[int] = Field(default=None, foreign_key="machine.id")
    software_id: Optional[int] = Field(default=None, foreign_key="software.id")
    
    target_type: str = Field(default="machine") # machine, ou, group
    target_value: str # machine_id or OU DN
    action: str = Field(default="install") # install, uninstall
    
    schedule_start: Optional[datetime] = None
    schedule_end: Optional[datetime] = None
    
    created_by: Optional[int] = Field(default=None, foreign_key="admin.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    machine: Optional[Machine] = Relationship(back_populates="deployments")
    software: Optional[Software] = Relationship(back_populates="deployments")

class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    admin_id: Optional[int] = Field(default=None, foreign_key="admin.id")
    action: str
    target: str
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str # INFO, ERROR, WARN

class AgentLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: int = Field(foreign_key="machine.id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str # INFO, ERROR, WARN
    message: str
