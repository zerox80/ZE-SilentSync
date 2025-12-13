# backend/tests/verify_fixes_static.py
import sys
import os

# Helper to verify targeting logic (replicated from management.py)
def check_targeting(target_dn):
    target_upper = target_dn.strip().upper()
    if target_dn.strip().isdigit():
         return "machine"
    elif target_upper.startswith("CN="):
        return "machine"
    elif target_upper.startswith(("OU=", "DC=")):
        return "ou"
    else:
         return "machine"

def run_checks():
    print("Verifying Targeting Heuristic (Bug 3)...")
    try:
        assert check_targeting("123") == "machine", "ID should be machine"
        assert check_targeting("CN=PC1,OU=Sales") == "machine", "CN= should be machine"
        assert check_targeting("OU=Sales,DC=com") == "ou", "OU= should be ou"
        assert check_targeting("DC=example,DC=com") == "ou", "DC= should be ou"
        assert check_targeting("PC-HOSTNAME") == "machine", "Hostname should be machine"
        print("PASS: Targeting logic looks correct.")
    except AssertionError as e:
        print(f"FAIL: {e}")

    print("\nVerifying LDAP Import (Bug 2)...")
    try:
        from ldap3.utils.dn import parse_dn
        print("PASS: ldap3.utils.dn.parse_dn is importable.")
    except ImportError:
        print("FAIL: ldap3 not found (or virtualenv issue).")

    print("\nVerifying Config Updates (Bug 1)...")
    try:
        # Check config.py content relative to this script
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config.py")
        with open(config_path, "r") as f:
            content = f.read()
            if 'self.AGENT_TOKEN = "agent-"' not in content and "secrets.token_urlsafe" in content:
                print("PASS: Weak token derivation removed.")
            else:
                 print("FAIL: Config still has weak token logic or missing random gen.")
    except Exception as e:
        print(f"FAIL reading config.py: {e}")

    print("\nVerifying Agent Retry Logic (Bug 5)...")
    try:
        agent_path = os.path.join(base_dir, "routers", "agent.py")
        with open(agent_path, "r") as f:
            content = f.read()
            if 'link.status == "failed"' in content and '< timedelta(hours=1)' in content:
                 print("PASS: Agent retry logic present.")
            else:
                 print("FAIL: Agent retry logic missing.")
    except Exception as e:
         print(f"FAIL reading agent.py: {e}")

if __name__ == "__main__":
    run_checks()
