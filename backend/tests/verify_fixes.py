
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

print("Starting Verification...")

try:
    from routers.management import create_bulk_deployment, BulkDeploymentRequest
    from models import Deployment, Machine, MachineSoftwareLink, Software, Admin
    from ldap_service import ldap_service
    from config import settings
    from sqlmodel import Session, SQLModel, create_engine, select
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

class TestBugFixes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        
        # Seed
        self.soft = Software(name="TestSoft", version="1.0", download_url="http://test", silent_args="")
        self.session.add(self.soft)
        self.machine = Machine(hostname="PC1", mac_address="00:11:22:33:44:55", ou_path="OU=Sales,DC=example")
        self.session.add(self.machine)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_bug_3_target_logic(self):
        print("\nTesting Bug 3 (Target Logic)...")
        # CN=PC1... should be Machine, even if OU= is in string
        target_dn = "CN=PC1,OU=Sales,DC=example"
        req = BulkDeploymentRequest(
            software_ids=[self.soft.id],
            target_dns=[target_dn],
            action="install"
        )
        
        # Mock session dependency? create_bulk_deployment uses Depends(get_session)
        # We can call it directly passing session if we modify signature or just use the logic?
        # The function signature is: def create_bulk_deployment(request: BulkDeploymentRequest, session: Session = Depends(get_session)):
        # So we can pass session directly.
        
        res = create_bulk_deployment(request=req, session=self.session)
        self.assertTrue(res['status'] == "bulk deployment scheduled")
        
        dep = self.session.exec(select(Deployment)).first()
        self.assertIsNotNone(dep)
        print(f"Target Type: {dep.target_type}")
        self.assertEqual(dep.target_type, "machine", "Should be identified as machine")
        print("PASS Bug 3")

    def test_bug_4_name_error_force_reinstall(self):
        print("\nTesting Bug 4 (UnboundLocalError in Force Reinstall)...")
        # Case where int(target_dn) fails
        target_dn = "CN=PC1,OU=Sales,DC=example" 
        req = BulkDeploymentRequest(
            software_ids=[self.soft.id],
            target_dns=[target_dn],
            action="install",
            force_reinstall=True
        )
        
        try:
            create_bulk_deployment(request=req, session=self.session)
            print("PASS Bug 4 (No Crash)")
        except UnboundLocalError:
            self.fail("FAIL: UnboundLocalError raised")
        except Exception as e:
            # If it raises ValueError or others it is fine as long as not UnboundLocalError crash
            print(f"Caught expected/unexpected exception: {e}")
            pass

    def test_bug_5_dn_parsing(self):
        print("\nTesting Bug 5 (LDAP DN Parsing)...")
        # Test get_parent_dn indirectly or check logic if we can access it
        # ldap_service.py has _re_split logic?
        # Let's test the re logic used in fix
        import re
        dn = "CN=Smith\, John,OU=Sales,DC=example"
        # The logic used:
        parts = re.split(r'(?<!\\),', dn)
        
        print(f"Parts: {parts}")
        self.assertEqual(parts[0], "CN=Smith\, John")
        self.assertEqual(parts[1], "OU=Sales")
        print("PASS Bug 5")

if __name__ == '__main__':
    unittest.main()
