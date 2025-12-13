from sqlmodel import Session, select
from database import engine
from models import Machine

def inspect():
    with Session(engine) as session:
        machines = session.exec(select(Machine)).all()
        for m in machines:
            print(f"ID: {m.id} | Hostname repr: {repr(m.hostname)}")

if __name__ == "__main__":
    inspect()
