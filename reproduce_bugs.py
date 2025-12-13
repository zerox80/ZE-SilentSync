import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Allow importing from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))

class TestBugs(unittest.TestCase):

    def test_bug1_dn_parsing(self):
        """Test the DN reconstruction logic in ldap_service.py"""
        from ldap3.utils.dn import parse_dn
        
        # Reproduce the logic from ldap_service.py (inner function get_parent_dn)
        def get_parent_dn_buggy(dn):
            try:
                parsed = parse_dn(dn)
                if len(parsed) > 1:
                    parent_parts = []
                    for i in range(1, len(parsed)):
                        attr, val, sep = parsed[i]
                        parent_parts.append(f"{attr}={val}")
                    return ",".join(parent_parts)
            except Exception:
                pass
            return None

        # Complex DN with escaped comma
        # "CN=PC1,OU=Dev\, Ops,DC=example" -> Parent should be "OU=Dev\, Ops,DC=example"
        # Parse DN splits it into: ('CN', 'PC1', ','), ('OU', 'Dev, Ops', ','), ('DC', 'example', '')
        # The buggy function reconstructs: "OU=Dev, Ops,DC=example" (MISSING ESCAPE)
        
        child_dn = "CN=PC1,OU=Dev\, Ops,DC=example"
        expected_parent = "OU=Dev\, Ops,DC=example"
        
        # Test Buggy Implementation behavior (confirm it produces WRONG result)
        buggy_result = get_parent_dn_buggy(child_dn)
        print(f"\n[Bug 1] Input: {child_dn}")
        print(f"[Bug 1] Buggy Result: {buggy_result}")
        # Note: ldap3's parse_dn unescapes the value 'Dev, Ops'. 
        # Simple reconstruction "OU=" + "Dev, Ops" creates "OU=Dev, Ops" which is INVALID merely because it lacks escape of comma.
        
        # Verification of FIX (we will simulate what the fix should do)
        # We need to verify that the ACTUAL code (once fixed) produces expected_parent.
        # But for now, we just assert that the bug exists (result != expected)
        
        # Actually, let's try to import the REAL service to test it directly
        try:
            from ldap_service import LDAPService
            service = LDAPService()
            # We need to access the inner function or similar logic. 
            # Since it's inside _fetch_real_ad_structure and that connects to AD, 
            # we can't easily call it without mocking entire AD.
            # So this unit test demonstrating the logic flaw is sufficient for "Reproduction".
            
            self.assertNotEqual(buggy_result, expected_parent, "Bug 1 Reproduction: Buggy logic accidentally worked?")
            print("[Bug 1] Reproduced: The current logic fails to preserve escaping.")
            
        except ImportError:
            print("Could not import LDAPService")

    def test_bug3_config_agent_token(self):
        """Test Bug 3: Config crashes if AGENT_TOKEN missing in production"""
        # Mock environment to simulate production (USE_MOCK_LDAP=False)
        # and standard vars, but MISSING AGENT_TOKEN
        
        env_vars = {
            "SECRET_KEY": "test-secret-key-123",
            "AD_PASSWORD": "password", 
            "USE_MOCK_LDAP": "False",
            # "AGENT_TOKEN": MISSING
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # We need to reload config or create a new check
            # Since config.py instantiates 'settings' at module level, 
            # we must reload it or test the class directly.
            
            try:
                # Reload config to force re-evaluation
                if 'config' in sys.modules:
                    del sys.modules['config']
                import config
                
                # If bug exists, this might raise ValueError or have None
                print(f"[Bug 3] AGENT_TOKEN: {config.settings.AGENT_TOKEN}")
                
            except ValueError as e:
                print(f"[Bug 3] Caught expected crash: {e}")
                self.assertIn("AGENT_TOKEN must be set", str(e))
                return

            # If we are here, maybe it didn't crash? 
            # If so, check if token is None or derived? 
            # Current code raises ValueError in prod if missing.
            
            # If we fixed it, it should NOT crash and should be "agent-" + ...
            # But we haven't fixed it yet.

if __name__ == '__main__':
    unittest.main()
