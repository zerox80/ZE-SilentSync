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

    def __init__(self):
        if not self.USE_MOCK_LDAP:
            if not self.AD_PASSWORD:
                raise ValueError("AD_PASSWORD must be set in production mode!")
        
        if not self.SECRET_KEY:
            if self.USE_MOCK_LDAP:
                self.SECRET_KEY = "unsafe-secret-key-change-me"
                print("WARNING: Using insecure default SECRET_KEY. Do not use in production!")
            else:
                raise ValueError("SECRET_KEY must be set in production mode!")

        if not self.AGENT_TOKEN:
            if self.USE_MOCK_LDAP:
                self.AGENT_TOKEN = "dev-agent-token"
                print("WARNING: Using insecure default AGENT_TOKEN. Do not use in production!")
            else:
                raise ValueError("AGENT_TOKEN must be set in production mode!")

settings = Settings()
