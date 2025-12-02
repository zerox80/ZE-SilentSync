from sqlmodel import Session, select
from database import engine
from models import Machine

def list_machines():
    with Session(engine) as session:
        machines = session.exec(select(Machine)).all()
        print(f"Found {len(machines)} machines:")
        for m in machines:
            print(f"ID: {m.id} | Hostname: {m.hostname} | MAC: {m.mac_address} | OU: {m.ou_path}")

if __name__ == "__main__":
    list_machines()
