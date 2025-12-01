from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from main import app
from database import get_session
from auth import get_current_admin, verify_agent_token
from models import Admin, Software, Machine, MachineSoftwareLink, Deployment
import pytest

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")
# Import all models to ensure they are registered
from models import Machine, Software, Deployment, Admin, MachineSoftwareLink, AgentLog, SoftwareDependency
SQLModel.metadata.create_all(engine)
print("Tables created:", SQLModel.metadata.tables.keys())

def get_session_override():
    print("DEBUG: Using overridden session")
    with Session(engine) as session:
        yield session

def get_current_admin_override():
    return Admin(username="testadmin", id=1, role="admin", hashed_password="fake")

def verify_agent_token_override():
    return True

app.dependency_overrides[get_session] = get_session_override
app.dependency_overrides[get_current_admin] = get_current_admin_override
app.dependency_overrides[verify_agent_token] = verify_agent_token_override

client = TestClient(app)

def test_management_flow():
    # 1. Create Software
    software_data = {
        "name": "Test App",
        "version": "1.0",
        "download_url": "http://example.com/app.exe",
        "silent_args": "/S",
        "is_msi": False
    }
    resp = client.post("/api/v1/management/software", json=software_data)
    assert resp.status_code == 200
    software_id = resp.json()["id"]

    # 2. Delete Software
    resp = client.delete(f"/api/v1/management/software/{software_id}")
    assert resp.status_code == 200
    
    # Verify it's gone
    with Session(engine) as session:
        s = session.get(Software, software_id)
        assert s is None

    # 3. Create Software again for deployment test
    resp = client.post("/api/v1/management/software", json=software_data)
    software_id = resp.json()["id"]

    # 4. Create Machine (via Heartbeat)
    hb_data = {
        "hostname": "test-pc",
        "mac_address": "00:11:22:33:44:55",
        "os_info": "Windows 10"
    }
    resp = client.post("/api/v1/agent/heartbeat", json=hb_data)
    assert resp.status_code == 200
    
    # Get machine ID
    with Session(engine) as session:
        machine = session.exec(select(Machine).where(Machine.hostname == "test-pc")).first()
        machine_id = machine.id
        # Ensure machine has OU path for matching if needed, but we'll target by machine ID implicitly or OU
        # The bulk deploy uses target_dns. Let's assume we target by OU or we need to know how agent matches.
        # Agent matches by machine ID if target_type is machine.
        # Let's update machine to have a known OU
        machine.ou_path = "OU=Test,DC=local"
        session.add(machine)
        session.commit()

    # 5. Deploy (Install)
    deploy_data = {
        "software_ids": [software_id],
        "target_dns": ["OU=Test,DC=local"], # Target by OU to match logic
        "action": "install",
        "force_reinstall": False
    }
    resp = client.post("/api/v1/management/deploy/bulk", json=deploy_data)
    assert resp.status_code == 200

    # 6. Simulate Agent Heartbeat -> Receive Task
    resp = client.post("/api/v1/agent/heartbeat", json=hb_data)
    data = resp.json()
    assert len(data["tasks"]) == 1
    task_id = data["tasks"][0]["id"]
    assert data["tasks"][0]["software_name"] == "Test App"

    # 7. Simulate Agent ACK (Success)
    ack_data = {
        "task_id": task_id,
        "status": "success",
        "message": "Installed",
        "mac_address": "00:11:22:33:44:55"
    }
    resp = client.post("/api/v1/agent/ack", json=ack_data)
    assert resp.status_code == 200

    # 8. Verify status is "installed"
    with Session(engine) as session:
        link = session.exec(select(MachineSoftwareLink).where(
            (MachineSoftwareLink.machine_id == machine_id) &
            (MachineSoftwareLink.software_id == software_id)
        )).first()
        assert link.status == "installed"

    # 9. Deploy AGAIN with force_reinstall=False -> Should NOT receive task
    resp = client.post("/api/v1/management/deploy/bulk", json=deploy_data)
    assert resp.status_code == 200
    
    resp = client.post("/api/v1/agent/heartbeat", json=hb_data)
    data = resp.json()
    assert len(data["tasks"]) == 0 # Should be empty because already installed

    # 10. Deploy AGAIN with force_reinstall=True
    deploy_data["force_reinstall"] = True
    resp = client.post("/api/v1/management/deploy/bulk", json=deploy_data)
    assert resp.status_code == 200

    # Verify status is reset to "pending"
    with Session(engine) as session:
        session.expire_all() # Refresh
        link = session.exec(select(MachineSoftwareLink).where(
            (MachineSoftwareLink.machine_id == machine_id) &
            (MachineSoftwareLink.software_id == software_id)
        )).first()
        assert link.status == "pending"

    # 11. Simulate Agent Heartbeat -> Should Receive Task AGAIN
    resp = client.post("/api/v1/agent/heartbeat", json=hb_data)
    data = resp.json()
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["software_name"] == "Test App"

    print("Test Passed!")

if __name__ == "__main__":
    test_management_flow()
