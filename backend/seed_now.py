from sqlmodel import Session, select, create_engine
from models import Software, Machine
from database import sqlite_url

engine = create_engine(sqlite_url)

def seed_now():
    with Session(engine) as session:
        if not session.exec(select(Software)).first():
            print("Seeding Mock Software...")
            softwares = [
                Software(name="Google Chrome", version="120.0", download_url="https://dl.google.com/chrome/install/chrome_installer.exe", silent_args="/silent /install", is_msi=False),
                Software(name="Mozilla Firefox", version="121.0", download_url="https://download.mozilla.org/?product=firefox-msi-latest", silent_args="/qn", is_msi=True),
                Software(name="7-Zip", version="23.01", download_url="https://www.7-zip.org/a/7z2301-x64.msi", silent_args="/qn", is_msi=True),
                Software(name="VLC Media Player", version="3.0.20", download_url="https://get.videolan.org/vlc/3.0.20/win64/vlc-3.0.20-win64.exe", silent_args="/S", is_msi=False),
            ]
            for s in softwares:
                session.add(s)
            
            if not session.exec(select(Machine)).first():
                 session.add(Machine(hostname="TEST-PC-01", mac_address="00:11:22:33:44:55", os_info="Windows 11 Pro", ou_path="OU=Sales,DC=example,DC=com"))
            
            session.commit()
            print("Seeding complete.")
        else:
            print("Database already has data.")

if __name__ == "__main__":
    seed_now()
