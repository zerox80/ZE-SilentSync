import os
import secrets
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
                self.SECRET_KEY = secrets.token_urlsafe(32)
                print("WARNING: SECRET_KEY not set. Generated a random one for Mock Mode.")
            else:
                self.SECRET_KEY = secrets.token_urlsafe(32)
                # Fix: Persist to .env
                self._append_to_env("SECRET_KEY", self.SECRET_KEY)
                print("WARNING: SECRET_KEY was missing. Generated and saved to .env")

        # Default token logic: "agent-" + first 8 chars of SECRET_KEY (see SETUP.md)
        if not self.AGENT_TOKEN:
            if self.USE_MOCK_LDAP:
                self.AGENT_TOKEN = secrets.token_urlsafe(32)
                print(f"WARNING: AGENT_TOKEN not set. Generated a random secure token: {self.AGENT_TOKEN}")
            else:
                # Fix: Generate a secure random token and PERSIST it
                self.AGENT_TOKEN = secrets.token_urlsafe(32)
                self._append_to_env("AGENT_TOKEN", self.AGENT_TOKEN)
                print(f"WARNING: AGENT_TOKEN was missing. Generated and saved to .env")
                
    def _append_to_env(self, key, value):
        try:
            # Fix: Ensure we don't corrupt the file if it doesn't end with a newline
            prefix = ""
            if os.path.exists(".env"):
                with open(".env", "rb") as f:
                    try:
                        f.seek(-1, os.SEEK_END)
                        last_char = f.read(1)
                        if last_char != b"\n":
                            prefix = "\n"
                    except OSError:
                        # Empty file or other issue
                        pass

            with open(".env", "a") as f:
                f.write(f"{prefix}{key}={value}\n")
        except Exception as e:
            print(f"Failed to save {key} to .env: {e}")

settings = Settings()
