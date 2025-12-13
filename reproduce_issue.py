import sys
import os
import json
from datetime import datetime

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from models import Machine

def test_machine_serialization():
    # Create a machine instance with sensitive API Key
    machine = Machine(
        id=1,
        hostname="Sensitive-PC",
        mac_address="00:11:22:33:44:55",
        api_key="SUPER_SECRET_TOKEN_DO_NOT_LEAK",
        last_seen=datetime.now()
    )

    # FastAPI uses .model_dump() (Pydantic v2) or .dict() (v1) for serialization
    # SQLModel is based on Pydantic.
    
    try:
        data = machine.model_dump()
    except AttributeError:
        data = machine.dict()
        
    print("Serialized Machine Data:")
    print(json.dumps(data, default=str, indent=2))
    
    if "api_key" in data:
        print("\n[FAIL] BUG REPRODUCED: 'api_key' is present in the serialized output.")
        print(f"Leaked Value: {data['api_key']}")
    else:
        print("\n[PASS] 'api_key' is NOT present in the output.")

if __name__ == "__main__":
    test_machine_serialization()
