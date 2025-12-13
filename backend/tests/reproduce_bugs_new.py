
import requests
import sys
import os

# Configuration
BASE_URL = "http://localhost:8000"
AGENT_TOKEN = "agent-secret" # Adjust if your .env is different

def test_unbound_local_error():
    print("Testing UnboundLocalError (Bug 1)...")
    # This requires the server to be running and ideally AGENT_ONLY=True for easy trigger,
    # or we simulate the condition. 
    # The bug is:
    # if settings.AGENT_ONLY:
    #    ou_path = ...
    # else:
    #    should_resolve = ...
    #    if should_resolve: ...
    #
    # if not machine: ... 
    
    # Wait, looking at the code again:
    # 38: if settings.AGENT_ONLY:
    # 39:     ou_path = "OU=Agents,DC=local"
    # 40: else:
    # 41:     # Resolve for new machines or explicit unknown
    # 42:     should_resolve = False
    # ...
    # 51:                 from ldap_service import ldap_service
    # 52:                 ou_path = ldap_service.resolve_machine_ou(hostname, session)
    
    # It seems 'should_resolve' IS defined in the else block.
    # Ah, but if settings.AGENT_ONLY is True, we go into the 'if' block.
    # Then later (lines 54+), is 'should_resolve' used?
    # No, it's not used outside.
    
    # Let's re-read the code carefully.
    # Lines 38-52 define ou_path.
    # Then lines 54+ use ou_path.
    
    # Wait, I might have misread the potential bug.
    # Let's look at the file content again.
    pass

def test_log_validation():
    print("Testing Log Validation (Bug 2)...")
    headers = {"X-Agent-Token": AGENT_TOKEN}
    
    # 1. Huge message
    huge_msg = "A" * 100000
    try:
        resp = requests.post(f"{BASE_URL}/api/v1/agent/log", 
                             params={"mac_address": "00:00:00:00:00:00", "level": "INFO", "message": huge_msg},
                             headers=headers)
        if resp.status_code == 200:
             print("FAIL: Hugely long message accepted.")
        else:
             print(f"PASS: Huge message rejected with {resp.status_code}")
    except Exception as e:
        print(f"Error connecting: {e}")

if __name__ == "__main__":
    test_log_validation()
