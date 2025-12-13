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
        # Fix: Load from .env first, then secrets file fallback
        self._load_from_secrets_file()
        
        # Load again from env to ensure priority
        self.AD_PASSWORD = os.getenv("AD_PASSWORD", self.AD_PASSWORD)
        self.SECRET_KEY = os.getenv("SECRET_KEY", self.SECRET_KEY)
        # Fix: AGENT_TOKEN fallback should use the value loaded from secrets.env if not in os.getenv
        self.AGENT_TOKEN = os.getenv("AGENT_TOKEN", self.AGENT_TOKEN)

        if not self.USE_MOCK_LDAP:
            if not self.AD_PASSWORD:
                raise ValueError("AD_PASSWORD must be set in production mode!")
        
        if not self.SECRET_KEY:
            self.SECRET_KEY = secrets.token_urlsafe(32)
            self._save_secret("SECRET_KEY", self.SECRET_KEY)
            print("WARNING: SECRET_KEY was missing. Generated and saved.")

        # Default token logic: "agent-" + first 8 chars of SECRET_KEY (see SETUP.md)
        if not self.AGENT_TOKEN:
            prefix = self.SECRET_KEY[:8] if self.SECRET_KEY else "unknown"
            self.AGENT_TOKEN = f"agent-{prefix}-{secrets.token_urlsafe(24)}"
            self._save_secret("AGENT_TOKEN", self.AGENT_TOKEN)
            print(f"WARNING: AGENT_TOKEN was missing. Generated and saved.")


    def _load_from_secrets_file(self):
        """Load secrets from a dedicated persistence file."""
        try:
            if os.path.exists("secrets.env"):
                with open("secrets.env", "r") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            os.environ[k] = v # Load into env for consistency
                            # Also update self if it maps to a property, respecting type
                            if hasattr(self, k):
                                current_val = getattr(self, k)
                                target_type = type(current_val)
                                
                                if target_type == bool:
                                    v_typed = v.lower() == "true"
                                elif target_type == int:
                                    try:
                                        v_typed = int(v)
                                    except ValueError:
                                        v_typed = v
                                else:
                                    v_typed = v
                                    
                                setattr(self, k, v_typed)
        except Exception as e:
            print(f"Failed to load secrets.env: {e}")

    def _save_secret(self, key, value):
        """Persist secret to both .env and secrets.env for redundancy"""
        # 1. Update .env (Best Effort)
        self._append_to_file(".env", key, value)
        # 2. Update secrets.env (Robust persistence for Docker volumes)
        self._append_to_file("secrets.env", key, value)
        
    def _append_to_file(self, filepath, key, value):
        try:
            # Ensure proper newline handling
            prefix = ""
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    try:
                        f.seek(-1, os.SEEK_END)
                        last_char = f.read(1)
                        if last_char != b"\n":
                            prefix = "\n"
                    except OSError:
                        pass # Empty file

            with open(filepath, "a") as f:
                f.write(f"{prefix}{key}={value}\n")
        except Exception as e:
            print(f"Failed to save {key} to {filepath}: {e}")

settings = Settings()
