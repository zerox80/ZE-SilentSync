
import sys
import os
# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, SQLModel, create_engine, select
from routers.management import create_bulk_deployment, BulkDeploymentRequest
from models import Deployment, Machine, MachineSoftwareLink, Software

def test_reproduce_bugs():
    # Setup In-Memory DB
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Seed Data
        soft = Software(name="TestSoft", version="1.0", download_url="http://test", silent_args="")
        session.add(soft)
        
        mach = Machine(hostname="PC1", mac_address="00:00:00:00:00:00", ou_path="OU=Sales,DC=example")
        session.add(mach)
        session.commit()
        
        # Link for reinstall test
        link = MachineSoftwareLink(machine_id=mach.id, software_id=soft.id, status="installed")
        session.add(link)
        session.commit()

        print("\n--- Test 1: Logic Bug (Target Identification) ---")
        # Bug: "OU=" in string makes it an OU, even if it is a computer CN
        target_dn = "CN=PC1,OU=Sales,DC=example"
        req = BulkDeploymentRequest(
            software_ids=[soft.id],
            target_dns=[target_dn],
            action="install"
        )
        
        try:
            create_bulk_deployment(req, session)
            # Check what happened
            dep = session.exec(select(Deployment)).first()
            print(f"Deployment created with target_type: '{dep.target_type}'")
            
            if dep.target_type == "ou":
                print("FAIL: CN=... identified as OU! (Bug Reproduced)")
            else:
                print("PASS: CN=... identified as machine.")
                
        except Exception as e:
            print(f"Error in Test 1: {e}")

        # Clear deployments
        session.exec(dep.__class__.delete()) # pseudo code, actually just delete
        session.delete(dep)
        session.commit()

        print("\n--- Test 2: NameError (Force Reinstall) ---")
        # Bug: force_reinstall accesses undefined 'target_value'
        req_force = BulkDeploymentRequest(
            software_ids=[soft.id],
            target_dns=[target_dn], # usage of CN should trigger machine logic path in ideal world, but let's see where it crashes
            action="install",
            force_reinstall=True
        )
        
        try:
            create_bulk_deployment(req_force, session)
            print("PASS: Force reinstall completed without error.")
        except NameError as e:
             if "name 'target_value' is not defined" in str(e):
                 print(f"FAIL: Scaught expected NameError: {e} (Bug Reproduced)")
             else:
                 print(f"FAIL: Caught NameError but unexpected message: {e}")
        except Exception as e:
            # If logic bug 1 persists, it might erroneously go into OU path which might NOT trigger the NameError if the NameError is in the "machine" block?
            # Let's check code.
            # In existing code:
            # if target_type == "machine": ... machine_id = int(target_value) ...
            # else: ... OU path ...
            #
            # Wait, line 101: machine_id = int(target_value). 'target_value' is undefined.
            # But wait, if Bug 1 makes it an "ou", it goes to 'else' block (line 106).
            # In 'else' block: machines = session.exec(...).all(). 
            # So Bug 1 actually HIDES Bug 2 for CN inputs!
            # To reproduce Bug 2, we must provide something that DOES NOT have "OU=" in it, or fix Bug 1 first.
            # But wait, a machine ID "1" does not have "OU=".
            print(f"Caught unexpected exception: {type(e).__name__}: {e}")

        print("\n--- Test 3: NameError (Force Reinstall with ID) ---")
        # Testing with ID to force "machine" path despite Bug 1
        req_id = BulkDeploymentRequest(
            software_ids=[soft.id],
            target_dns=["1"], # ID 1
            action="install",
            force_reinstall=True
        )
        try:
            create_bulk_deployment(req_id, session)
            print("PASS: ID Force reinstall completed.")
        except NameError as e:
             print(f"FAIL: Caught expected NameError: {e} (Bug Reproduced)")
        except Exception as e:
             print(f"Caught unexpected exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_reproduce_bugs()
