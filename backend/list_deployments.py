from sqlmodel import Session, select
from database import engine
from models import Deployment, Software

def list_deployments():
    with Session(engine) as session:
        deployments = session.exec(select(Deployment)).all()
        print(f"Found {len(deployments)} deployments:")
        for d in deployments:
            soft_name = d.software.name if d.software else "UNKNOWN"
            print(f"ID: {d.id} | Software: {soft_name} | Target Type: {d.target_type} | Target Value: {d.target_value}")

if __name__ == "__main__":
    list_deployments()
