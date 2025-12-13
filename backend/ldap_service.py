from typing import List, Dict, Any, Optional
import re
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn, escape_dn_chars
from sqlmodel import Session, select
from config import settings
from models import Machine

class LDAPService:
    def __init__(self):
        self.mock_structure = {
            "id": "DC=example,DC=com",
            "name": "example.com",
            "type": "domain",
            "children": [
                {
                    "id": "OU=Management,DC=example,DC=com",
                    "name": "Management",
                    "type": "ou",
                    "children": [
                        {"id": "CN=AdminPC,OU=Management,DC=example,DC=com", "name": "AdminPC", "type": "computer"},
                        {"id": "CN=ManagerLaptop,OU=Management,DC=example,DC=com", "name": "ManagerLaptop", "type": "computer"}
                    ]
                },
                {
                    "id": "OU=Sales,DC=example,DC=com",
                    "name": "Sales",
                    "type": "ou",
                    "children": [
                        {"id": "CN=Sales01,OU=Sales,DC=example,DC=com", "name": "Sales01", "type": "computer"},
                        {"id": "CN=Sales02,OU=Sales,DC=example,DC=com", "name": "Sales02", "type": "computer"}
                    ]
                },
                {
                    "id": "OU=IT,DC=example,DC=com",
                    "name": "IT",
                    "type": "ou",
                    "children": [
                        {"id": "CN=DevWorkstation,OU=IT,DC=example,DC=com", "name": "DevWorkstation", "type": "computer"}
                    ]
                }
            ]
        }

    def verify_user(self, username, password):
        """Verifies credentials against AD. Returns status string."""
        if settings.USE_MOCK_LDAP:
            # Mock Auth
            return "SUCCESS" # In mock mode, any password works for 'admin' usually
            
        try:
             # Fix: Use AD_SERVER and bind with the user's credentials
             from ldap3.core.exceptions import LDAPBindError
             
             try:
                 server = Server(settings.AD_SERVER, get_info=ALL, connect_timeout=2)
                 
                 # 1. Search for User DN
                 # Bind with service account first
                 with Connection(server, user=settings.AD_USER, password=settings.AD_PASSWORD, auto_bind=True) as conn:
                     conn.search(settings.AD_BASE_DN, f'(&(objectClass=user)(sAMAccountName={escape_filter_chars(username)}))', attributes=['distinguishedName'])
                     if not conn.entries:
                         return "NOT_FOUND"
                     user_dn = str(conn.entries[0].distinguishedName)
                     
                 # 2. Verify password by binding as that user
                 # This raises LDAPBindError if password is wrong
                 with Connection(server, user=user_dn, password=password, auto_bind=True):
                     return "SUCCESS"
                     
             except LDAPBindError:
                 return "INVALID_CREDENTIALS"
                 
        except Exception as e:
            print(f"LDAP Auth Error: {e}")
            return "ERROR"

    def resolve_machine_ou(self, hostname: str, session: Optional[Session] = None) -> str:
        """Finds the DN for a given hostname."""
        if settings.AGENT_ONLY:
            # Fix: Use dynamic root matching configured base DN or fallback
            from ldap3.utils.dn import escape_dn_chars
            return f"CN={escape_dn_chars(hostname)},OU=Agents,{settings.AD_BASE_DN}"
            
        if settings.USE_MOCK_LDAP:
            # Search in mock structure
            # Logic: Helper to traverse tree
            def find_computer(node, name):
                if node.get("type") == "computer" and node.get("name").lower() == name.lower():
                    return node.get("id")
                for child in node.get("children", []):
                    res = find_computer(child, name)
                    if res: return res
                return None
            
            res = find_computer(self.mock_structure, hostname)
            return res or "Unknown"

        # Real LDAP
        try:
             server = Server(settings.AD_SERVER, get_info=ALL, connect_timeout=2)
             with Connection(server, user=settings.AD_USER, password=settings.AD_PASSWORD, auto_bind=True) as conn:
                 # Search for computer
                 conn.search(settings.AD_BASE_DN, f'(&(objectClass=computer)(name={escape_filter_chars(hostname)}))', attributes=['distinguishedName'])
                 if conn.entries:
                     return str(conn.entries[0].distinguishedName)
             return "Unknown"
        except Exception as e:
            # Fix Bug 8: Improve error logging for debugging
            print(f"LDAP Lookup Error in resolve_machine_ou for {hostname}: {e}")
            return "Unknown"

    def get_ou_tree(self, session: Optional[Session] = None) -> Dict[str, Any]:
        """Returns the full OU structure."""
        if settings.AGENT_ONLY:
            return self._build_agent_tree(session)

        if settings.USE_MOCK_LDAP:
            return self.mock_structure
        
        return self._fetch_real_ad_structure()

    def _build_agent_tree(self, session: Optional[Session]) -> Dict[str, Any]:
        """Builds a virtual tree from registered agents."""
        if not session:
            return {"Error": {"type": "error", "name": "Database session required for Agent Only mode"}}
            
        machines = session.exec(select(Machine)).all()
        
        # Helper to get domain parts
        root_dn = settings.AD_BASE_DN # Use configured base instead of hardcoded local
        root_name = root_dn.replace("DC=", "").replace(",", ".")

        children_nodes = []
        for machine in machines:
            # Fix: Use configured Root
            from ldap3.utils.dn import escape_dn_chars
            machine_dn = f"CN={escape_dn_chars(machine.hostname)},OU=Agents,{root_dn}"
            # Use ID as string for key if needed, or DN
            children_nodes.append({
                "name": machine.hostname,
                "type": "computer",
                "id": str(machine.id), # Frontend uses ID for selection
                "dn": machine_dn
            })

        root_node = {
            "id": root_dn,
            "name": f"Agent Network ({root_name})",
            "type": "domain",
            "children": [
                {
                    "id": f"OU=Agents,{root_dn}",
                    "name": "Registered Agents",
                    "type": "ou",
                    "children": children_nodes
                }
            ]
        }
            
        return root_node

    def _fetch_real_ad_structure(self) -> Dict[str, Any]:
        """Connects to real AD and builds the tree."""
        try:
             server = Server(settings.AD_SERVER, get_info=ALL, connect_timeout=2)
            # Fix: Use context manager to ensure unbind
            with Connection(server, user=settings.AD_USER, password=settings.AD_PASSWORD, auto_bind=True, raise_exceptions=True) as conn:
                # Search for OUs and Computers
                conn.search(settings.AD_BASE_DN, '(objectClass=organizationalUnit)', attributes=['distinguishedName', 'name'])
                ous = [entry for entry in conn.entries]
                
                conn.search(settings.AD_BASE_DN, '(objectClass=computer)', attributes=['distinguishedName', 'name'])
                computers = [entry for entry in conn.entries]
            
            # The connection is now closed, but we have the data in 'ous' and 'computers' lists

            
            # Build a hierarchical tree structure
            
            # Map all OUs by DN
            # Fix: Normalize DN keys to ensure matching (lowercase keys)
            ou_map = {}
            for ou in ous:
                ou_dn = str(ou.distinguishedName)
                ou_map[ou_dn.lower()] = {
                    "id": ou_dn,
                    "name": str(ou.name),
                    "type": "ou",
                    "children": []
                }
            
            # Root node (Domain)
            root_dn = settings.AD_BASE_DN
            root_node = {
                "id": root_dn,
                "name": root_dn.replace("DC=", "").replace(",", "."), # Simple name from DN
                "type": "domain",
                "children": []
            }
            
            # Helper to find parent DN
            def get_parent_dn(dn):
                try:
                     # Fix Bug 1: Use robust DN parsing
                     parsed = parse_dn(dn)
                     if len(parsed) > 1:
                         # Reconstruct parent by skipping the first RDN
                         parent_parts = []
                         for i in range(1, len(parsed)):
                             attr, val, sep = parsed[i]
                             # We must re-escape special characters in the value
                             # escape_dn_chars handles ',', '+', '"', '\', '<', '>', ';', etc.
                             escaped_val = escape_dn_chars(val)
                             parent_parts.append(f"{attr}={escaped_val}")
                         
                         return ",".join(parent_parts)
                except Exception:
                    pass
                return None

            # Attach OUs to their parents
            for dn_key, node in ou_map.items():
                # dn_key is lower cased
                # node['id'] is original case
                
                parent_dn = get_parent_dn(node['id'])
                if not parent_dn: 
                    continue
                    
                parent_dn_lower = parent_dn.lower()
                
                if parent_dn_lower == root_dn.lower():
                    root_node["children"].append(node)
                elif parent_dn_lower in ou_map:
                    ou_map[parent_dn_lower]["children"].append(node)
                else:
                    # Parent might be a container we didn't fetch or it's out of scope
                    # For safety, add to root or ignore. Let's add to root to be safe.
                    if parent_dn_lower != root_dn.lower(): 
                         root_node["children"].append(node)

            # Attach Computers to their OUs
            for comp in computers:
                comp_dn = str(comp.distinguishedName)
                comp_name = str(comp.name)
                parent_dn = get_parent_dn(comp_dn)
                
                comp_node = {"id": comp_dn, "name": comp_name, "type": "computer"}
                
                if not parent_dn:
                    root_node["children"].append(comp_node)
                    continue

                parent_dn_lower = parent_dn.lower()

                if parent_dn_lower == root_dn.lower():
                    root_node["children"].append(comp_node)
                elif parent_dn_lower in ou_map:
                    ou_map[parent_dn_lower]["children"].append(comp_node)
                else:
                    root_node["children"].append(comp_node)
            
            return root_node
            
        except Exception as e:
            print(f"LDAP Error: {e}")
            return {"Error": {"type": "error", "name": str(e)}}

ldap_service = LDAPService()
