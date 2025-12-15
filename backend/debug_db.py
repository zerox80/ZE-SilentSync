from database import get_session
from models import MachineSoftwareLink, Deployment, Machine
from sqlmodel import select

session = next(get_session())

print("--- DEPLOYMENTS ---")
deps = session.exec(select(Deployment)).all()
for d in deps:
    print(f"Dep ID: {d.id}, Target: {d.target_value} ({d.target_type}), Action: {d.action}, SoftwareID: {d.software_id}")

print("\n--- MACHINES ---")
machines = session.exec(select(Machine)).all()
for m in machines:
    print(f"Machine ID: {m.id}, Hostname: {m.hostname}")

print("\n--- LINKS ---")
links = session.exec(select(MachineSoftwareLink)).all()
for l in links:
    print(f"Machine: {l.machine_id}, Software: {l.software_id}, Status: {l.status}, Version: {l.installed_version}")
