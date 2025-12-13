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
                            # Fix: Do not overwrite existing environment variables (Docker/Shell priority)
                            if k not in os.environ:
                                os.environ[k] = v
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
        # Fix: Use file locking to prevent race conditions
        import fcntl
        
        for filepath in [".env", "secrets.env"]:
            try:
                # Open in append mode, but we need a lock. 
                # We open with 'a+' to read/write/append
                with open(filepath, "a+") as f:
                    fcntl.flock(f, fcntl.LOCK_EX)
                    try:
                        # Check if key exists already to avoid duplicates?
                        # It's expensive to read all. We just append. 
                        # Last value usually wins in doten.
                        
                        ensure_newline = False
                        if f.tell() > 0:
                            f.seek(f.tell() - 1)
                            if f.read(1) != "\n":
                                ensure_newline = True
                        
                        if ensure_newline:
                            f.write("\n")
                        f.write(f"{key}={value}\n")
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)
            except Exception as e:
                print(f"Failed to save {key} to {filepath}: {e}")

    # _append_to_file removed as it is now integrated with locking above

settings = Settings()
