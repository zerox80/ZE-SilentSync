import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    AD_SERVER = os.getenv("AD_SERVER", "localhost")
    AD_USER = os.getenv("AD_USER", "admin@example.com")
    AD_PASSWORD = os.getenv("AD_PASSWORD")
    AD_BASE_DN = os.getenv("AD_BASE_DN", "DC=example,DC=com")
    USE_MOCK_LDAP = os.getenv("USE_MOCK_LDAP", "True").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY")
    AGENT_TOKEN = os.getenv("AGENT_TOKEN")
    AGENT_ONLY = os.getenv("AGENT_ONLY", "False").lower() == "true"
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

    def __init__(self):
        if not self.USE_MOCK_LDAP:
            if not self.AD_PASSWORD:
                raise ValueError("AD_PASSWORD must be set in production mode!")
        
        if not self.SECRET_KEY:
            if self.USE_MOCK_LDAP:
                import secrets
                self.SECRET_KEY = secrets.token_urlsafe(32)
                print("WARNING: SECRET_KEY not set. Generated a random one for Mock Mode.")
            else:
                raise ValueError("SECRET_KEY must be set in production mode!")

        # Default token logic: "agent-" + first 8 chars of SECRET_KEY (see SETUP.md)
        if not self.AGENT_TOKEN:
            if self.USE_MOCK_LDAP:
                import secrets
                self.AGENT_TOKEN = secrets.token_urlsafe(32)
                print(f"WARNING: AGENT_TOKEN not set. Generated a random secure token: {self.AGENT_TOKEN}")
                print("Please set AGENT_TOKEN in your .env file for persistence.")
            else:
                # Fail in production if not set to prevent connectivity loss on restart
                raise ValueError("AGENT_TOKEN must be set in production mode! Agents will lose connectivity on restart otherwise.")

settings = Settings()
