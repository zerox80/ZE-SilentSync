from sqlmodel import Session, select, create_engine
from models import Software, Machine
from database import sqlite_url

# Force absolute path if needed, but relative should work in container
engine = create_engine(sqlite_url)

try:
    with Session(engine) as session:
        print("--- DIAGNOSTIC START ---")
        softwares = session.exec(select(Software)).all()
        machines = session.exec(select(Machine)).all()
        
        print(f"Softwares found: {len(softwares)}")
        for s in softwares:
            print(f" - {s.name} ({s.version})")
            
        print(f"Machines found: {len(machines)}")
        for m in machines:
            print(f" - {m.hostname} ({m.mac_address})")
        print("--- DIAGNOSTIC END ---")
except Exception as e:
    print(f"Error: {e}")
