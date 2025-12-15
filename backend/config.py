import os
import sys
import secrets
from dotenv import load_dotenv

load_dotenv()

# Cross-platform file locking helper
def _lock_file(f, exclusive=True):
    """Lock a file in a cross-platform way."""
    if sys.platform == 'win32':
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if exclusive else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

def _unlock_file(f):
    """Unlock a file in a cross-platform way."""
    if sys.platform == 'win32':
        import msvcrt
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass  # Ignore unlock errors on Windows
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)

class Settings:
    AD_SERVER = os.getenv("AD_SERVER", "localhost")
    AD_USER = os.getenv("AD_USER", "admin@example.com")
    AD_PASSWORD = os.getenv("AD_PASSWORD")
    AD_BASE_DN = os.getenv("AD_BASE_DN", "DC=example,DC=com")
    USE_MOCK_LDAP = os.getenv("USE_MOCK_LDAP", "True").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY")
    AGENT_TOKEN = os.getenv("AGENT_TOKEN")
    AGENT_ONLY = os.getenv("AGENT_ONLY", "False").lower() == "true"
    ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")]
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "False").lower() == "true"
    MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024 * 1024)) # 10 GB Default

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
                 raise ValueError("CRITICAL ERROR: AD_PASSWORD is missing in production mode!")
        
        # Secrets Management
        if not self.SECRET_KEY:
            if not self.USE_MOCK_LDAP:
                 print("CRITICAL WARNING: SECRET_KEY is missing in production. Sessions will be insecure.")
                 # Ideally we should raise here too, but for now we warn loudly.
            else:
                self.SECRET_KEY = secrets.token_urlsafe(32)
                self._save_secret("SECRET_KEY", self.SECRET_KEY)
                print("WARNING: SECRET_KEY was missing. Generated and saved (Dev/Mock Mode).")

        # Default token logic: "agent-" + first 8 chars of SECRET_KEY (see SETUP.md)
        if not self.AGENT_TOKEN:
            if not self.USE_MOCK_LDAP:
                # Security Fix: In production, we must persist this token if possible, otherwise agents disconnect on restart.
                print("CRITICAL WARNING: AGENT_TOKEN is missing in production! Generating and SAVING a random token.")
                self.AGENT_TOKEN = f"agent-PROD-{secrets.token_urlsafe(24)}"
                self._save_secret("AGENT_TOKEN", self.AGENT_TOKEN)
            else:
                # In Mock/Dev, we can auto-generate
                prefix = self.SECRET_KEY[:8] if self.SECRET_KEY else "unknown"
                self.AGENT_TOKEN = f"agent-{prefix}-{secrets.token_urlsafe(24)}"
                self._save_secret("AGENT_TOKEN", self.AGENT_TOKEN)
                print(f"WARNING: AGENT_TOKEN was missing. Generated and saved (Dev/Mock Mode).")


    def _load_from_secrets_file(self):
        """Load secrets from a dedicated persistence file."""
        try:
            if os.path.exists("secrets.env"):
                with open("secrets.env", "r") as f:
                    _lock_file(f, exclusive=False)
                    try:
                        # Loop over lines
                        for line in f:
                            if "=" in line:
                                k, v = line.strip().split("=", 1)
                                # Fix: Do not mutate global os.environ
                                # if k not in os.environ:
                                #    os.environ[k] = v
                                
                                # Also update self if it maps to a property, respecting type
                                if hasattr(self, k):
                                    current_val = getattr(self, k)
                                    # Fix: Handle None values - treat as string type
                                    if current_val is None:
                                        v_typed = v
                                    else:
                                        target_type = type(current_val)
                                        
                                        if target_type == bool:
                                            v_typed = v.lower() in ("true", "1", "yes", "on")
                                        elif target_type == int:
                                            try:
                                                v_typed = int(v)
                                            except ValueError:
                                                v_typed = v
                                        else:
                                            v_typed = v
                                        
                                    setattr(self, k, v_typed)
                    finally:
                        _unlock_file(f)
        except Exception as e:
            print(f"Failed to load secrets.env: {e}")

    def _save_secret(self, key, value):
        """Persist secret to both .env and secrets.env for redundancy"""
        for filepath in [".env", "secrets.env"]:
            try:
                # Open in append mode, but we need a lock. 
                # We open with 'a+' to read/write/append
                with open(filepath, "a+") as f:
                    _lock_file(f, exclusive=True)
                    try:
                        # Check if key exists already to avoid duplicates?
                        # It's expensive to read all. We just append. 
                        # Last value usually wins in doten.
                        
                        ensure_newline = False
                        f.seek(0, 2)  # Seek to end
                        file_size = f.tell()
                        if file_size > 0:
                            f.seek(file_size - 1)
                            if f.read(1) != "\n":
                                ensure_newline = True
                        
                        if ensure_newline:
                            f.write("\n")
                        f.write(f"{key}={value}\n")
                    finally:
                        _unlock_file(f)
            except Exception as e:
                print(f"Failed to save {key} to {filepath}: {e}")

    # _append_to_file removed as it is now integrated with locking above

settings = Settings()
