import os
import shutil
from sqlmodel import Session, SQLModel, create_engine, select
from datetime import datetime

# Setup Env for Testing
os.environ["SECRET_KEY"] = "testsecret"
os.environ["AGENT_TOKEN"] = "testagenttoken"
os.environ["USE_MOCK_LDAP"] = "True"
os.environ["AGENT_ONLY"] = "False"

from models import Software, Machine, Deployment, Admin, AuditLog
from routers import management, agent

# Create Test DB
sqlite_file_name = "test_database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

if os.path.exists(sqlite_file_name):
    os.remove(sqlite_file_name)
    
if os.path.exists("uploads"):
    shutil.rmtree("uploads")
os.makedirs("uploads")

SQLModel.metadata.create_all(engine)

# Helpers
class MockRequest:
    def __init__(self, headers=None, client=None):
        self.headers = headers or {}
        self.client = client

class MockClient:
    def __init__(self, host):
        self.host = host

def get_test_admin(session):
    admin = session.exec(select(Admin)).first()
    if not admin:
        admin = Admin(username="admin", hashed_password="pw", role="superadmin")
        session.add(admin)
        session.commit()
        session.refresh(admin)
    return admin

def test_file_deletion_safety():
    print("--- Test: File Deletion Safety ---")
    with Session(engine) as session:
        admin = get_test_admin(session)
        
        # Create dummy file
        with open("uploads/shared.msi", "w") as f:
            f.write("dummy content")
            
        # Create two softwares sharing functionality
        s1 = Software(name="Soft A", version="1.0", download_url="/static/shared.msi", silent_args="")
        s2 = Software(name="Soft B", version="1.0", download_url="/static/shared.msi", silent_args="")
        
        # We must set ID manually or let session do it? Session does it.
        # But create_software commits.
        
        # We call create_software logic (Simulated)
        # Note: create_software commits, so we must be careful with sharing session if functions close it?
        # The functions accept session, so it's fine.
        
        # Helper to call create
        management.create_software(s1, session, admin)
        management.create_software(s2, session, admin)
        
        # Check file exists
        if not os.path.exists("uploads/shared.msi"):
            print("FAIL: Test Setup Failed (file missing)")
            return

        # Delete S1
        print("Deleting Software A...")
        management.delete_software(s1.id, session, admin)
        
        # Check file STILL exists
        if os.path.exists("uploads/shared.msi"):
            print("PASS: File preserved after deleting first reference.")
        else:
            print("FAIL: File was deleted prematurely!")
            
        # Delete S2
        print("Deleting Software B...")
        management.delete_software(s2.id, session, admin)
        
        # Check file GONE
        if not os.path.exists("uploads/shared.msi"):
            print("PASS: File deleted after last reference removed.")
        else:
            print("FAIL: File still exists after last delete!")

def test_software_validation():
    print("\n--- Test: Software Validation ---")
    with Session(engine) as session:
        admin = get_test_admin(session)
        try:
            management.create_deployment(999, "CN=Test", "machine", "install", session, admin)
            print("FAIL: Did not raise error for missing software")
        except Exception as e:
            if "404" in str(e):
                print("PASS: Raised 404 for missing software.")
            else:
                 print(f"FAIL: Raised unexpected error: {e}")

def test_audit_logs():
    print("\n--- Test: Audit Logging ---")
    with Session(engine) as session:
        logs = session.exec(select(AuditLog)).all()
        print(f"Found {len(logs)} audit logs.")
        for log in logs:
            print(f" - {log.action}: {log.target}")
            
        if len(logs) >= 3: # 2 creates + 2 deletes + failed deploy? (failed deploy might not log)
            # We did 2 creates (Soft A, Soft B) -> 2 logs
            # We did 2 deletes -> 2 logs
            print("PASS: Audit logs present.")
        else:
            print("FAIL: Insufficient audit logs.")

def test_hostname_collision():
    print("\n--- Test: Hostname Collision ---")
    with Session(engine) as session:
        # 1. Register Machine 1
        req = MockRequest(client=MockClient("192.168.1.10"))
        data = agent.HeartbeatRequest(hostname="PC-Collision", mac_address="AA:BB:CC:00:00:01", os_info="Win10")
        
        # Call heartbeat
        res1 = agent.heartbeat(req, data, session)
        print(f"Machine 1 Registered: API Key present: {bool(res1.get('machine_token'))}")
        
        # 2. Register Machine 2 (Same Hostname, Diff MAC)
        req2 = MockRequest(client=MockClient("192.168.1.11"))
        data2 = agent.HeartbeatRequest(hostname="PC-Collision", mac_address="AA:BB:CC:00:00:02", os_info="Win10")
        
        try:
            res2 = agent.heartbeat(req2, data2, session)
            print("PASS: No 409 Conflict Raised.")
            
            # Check Hostname in DB
            m2 = session.exec(select(Machine).where(Machine.mac_address == "AA:BB:CC:00:00:02")).first()
            print(f"Machine 2 Hostname: {m2.hostname}")
            if "PC-Collision-dup-" in m2.hostname:
                 print("PASS: Hostname renamed correctly.")
            else:
                 print(f"FAIL: Hostname not renamed? {m2.hostname}")
                 
        except Exception as e:
            print(f"FAIL: Exception raised: {e}")

def run_tests():
    test_file_deletion_safety()
    test_software_validation()
    test_audit_logs()
    test_hostname_collision()

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
