from typing import Optional, List
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship

# --- Join Tables ---
class MachineSoftwareLink(SQLModel, table=True):
    machine_id: Optional[int] = Field(default=None, foreign_key="machine.id", primary_key=True)
    software_id: Optional[int] = Field(default=None, foreign_key="software.id", primary_key=True)
    status: str = Field(default="pending") # pending, installing, installed, failed
    last_updated: datetime = Field(default_factory=datetime.utcnow)

# --- Main Models ---

class Machine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hostname: str = Field(index=True, unique=True)
    mac_address: str = Field(index=True, unique=True)
    ip_address: Optional[str] = None
    os_info: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    ou_path: str = Field(default="Unknown") # Cached OU path from AD

    deployments: List["Deployment"] = Relationship(back_populates="machine")

class Software(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    version: str
    description: Optional[str] = None
    download_url: str
    silent_args: str # e.g. /S /silent
    icon_url: Optional[str] = None
    
    deployments: List["Deployment"] = Relationship(back_populates="software")

class Deployment(SQLModel, table=True):
    """
    Represents a target state: "This software SHOULD be on this machine"
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: Optional[int] = Field(default=None, foreign_key="machine.id")
    software_id: Optional[int] = Field(default=None, foreign_key="software.id")
    target_type: str = Field(default="machine") # machine, ou
    target_value: str # machine_id or OU DN
    
    machine: Optional[Machine] = Relationship(back_populates="deployments")
    software: Optional[Software] = Relationship(back_populates="deployments")

class AgentLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: int = Field(foreign_key="machine.id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str # INFO, ERROR, WARN
    message: str
