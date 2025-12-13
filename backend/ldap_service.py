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

    def resolve_machine_ou(self, hostname: str, session: Optional[Session] = None) -> str:
        """Finds the DN for a given hostname."""
        if settings.AGENT_ONLY:
            return f"CN={hostname},OU=Agents,DC=local"
            
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
             server = Server(settings.AD_SERVER, get_info=ALL, connect_timeout=5)
             conn = Connection(server, user=settings.AD_USER, password=settings.AD_PASSWORD, auto_bind=True)
             
             # Search for computer
             conn.search(settings.AD_BASE_DN, f'(&(objectClass=computer)(name={escape_filter_chars(hostname)}))', attributes=['distinguishedName'])
             if conn.entries:
                 return str(conn.entries[0].distinguishedName)
             return "Unknown"
        except Exception as e:
            print(f"LDAP Lookup Error: {e}")
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
        
        # Create a virtual root "Agents"
        # Frontend expects a single root node object, not a dictionary of nodes
        
        children_nodes = []
        for machine in machines:
            # Use a fake DN for the machine
            machine_dn = f"CN={machine.hostname},OU=Agents,DC=local"
            # Use ID as string for key if needed, or DN
            children_nodes.append({
                "name": machine.hostname,
                "type": "computer",
                "id": str(machine.id), # Frontend uses ID for selection
                "dn": machine_dn
            })

        root_node = {
            "id": "DC=local",
            "name": "Agent Network",
            "type": "domain",
            "children": [
                {
                    "id": "OU=Agents,DC=local",
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
            server = Server(settings.AD_SERVER, get_info=ALL, connect_timeout=5)
            conn = Connection(server, user=settings.AD_USER, password=settings.AD_PASSWORD, auto_bind=True, raise_exceptions=True)
            
            # Search for OUs and Computers
            conn.search(settings.AD_BASE_DN, '(objectClass=organizationalUnit)', attributes=['distinguishedName', 'name'])
            ous = [entry for entry in conn.entries]
            
            conn.search(settings.AD_BASE_DN, '(objectClass=computer)', attributes=['distinguishedName', 'name'])
            computers = [entry for entry in conn.entries]
            
            # Build a hierarchical tree structure
            
            # Map all OUs by DN
            ou_map = {}
            for ou in ous:
                ou_dn = str(ou.distinguishedName)
                # Ensure unified casing for keys if needed, but AD is usually case-insensitive but consistent.
                # We'll use the DN as is.
                ou_map[ou_dn] = {
                    "id": ou_dn,
                    "name": str(ou.name),
                    "type": "ou",
                    "children": []
                }
            
            # Root node (Domain)
            # Assuming AD_BASE_DN is the domain root like DC=example,DC=com
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
                    parsed = parse_dn(dn)
                    if len(parsed) > 1:
                        # Reconstruct the parent DN by joining components after the first one
                        parent_parts = []
                        for i in range(1, len(parsed)):
                            attr, val, sep = parsed[i]
                            # Fix: Properly escape the value to ensure valid DN syntax
                            parent_parts.append(f"{attr}={escape_dn_chars(val)}")
                        
                        return ",".join(parent_parts)
                except Exception:
                    pass
                return None

            # Attach OUs to their parents
            for dn, node in ou_map.items():
                parent_dn = get_parent_dn(dn)
                if parent_dn == root_dn:
                    root_node["children"].append(node)
                elif parent_dn in ou_map:
                    ou_map[parent_dn]["children"].append(node)
                else:
                    # Parent might be a container we didn't fetch or it's out of scope
                    # For safety, add to root or ignore. Let's add to root to be safe.
                    if dn != root_dn: # Avoid self-loop if something is weird
                         root_node["children"].append(node)

            # Attach Computers to their OUs
            for comp in computers:
                comp_dn = str(comp.distinguishedName)
                comp_name = str(comp.name)
                parent_dn = get_parent_dn(comp_dn)
                
                comp_node = {"id": comp_dn, "name": comp_name, "type": "computer"}
                
                if parent_dn == root_dn:
                    root_node["children"].append(comp_node)
                elif parent_dn in ou_map:
                    ou_map[parent_dn]["children"].append(comp_node)
                else:
                    # Fallback
                    root_node["children"].append(comp_node)
            
            return root_node
            
        except Exception as e:
            print(f"LDAP Error: {e}")
            return {"Error": {"type": "error", "name": str(e)}}

ldap_service = LDAPService()
