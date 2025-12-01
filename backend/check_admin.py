from sqlmodel import Session, select, create_engine
from models import Admin
from passlib.context import CryptContext

# Connect to the database
engine = create_engine("sqlite:///database.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

with Session(engine) as session:
    admins = session.exec(select(Admin)).all()
    print(f"Found {len(admins)} admins.")
    
    if not admins:
        print("Creating default admin user...")
        hashed_pwd = get_password_hash("unsafe-secret-key-change-me")
        admin = Admin(username="admin", role="superadmin", hashed_password=hashed_pwd)
        session.add(admin)
        session.commit()
        print("Admin user created.")
    else:
        for admin in admins:
            print(f"Username: {admin.username}, Role: {admin.role}, Hash: {admin.hashed_password[:10]}...")
