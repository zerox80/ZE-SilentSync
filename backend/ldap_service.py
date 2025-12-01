from typing import List, Dict, Any, Optional
from ldap3 import Server, Connection, ALL, SUBTREE
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
            
            # Build a simplified tree structure (Flat list for now for simplicity, or nested if we had more time)
            # For this MVP, we will return a flat structure that the frontend can handle or we structure it simply.
            
            # NOTE: Building a perfect nested tree from flat LDAP DNs is complex.
            # We will return a simplified structure where top level keys are OUs.
            
            tree = {}
            for ou in ous:
                ou_dn = str(ou.distinguishedName)
                ou_name = str(ou.name)
                tree[ou_dn] = {"type": "ou", "name": ou_name, "children": []}
                
            for comp in computers:
                comp_dn = str(comp.distinguishedName)
                comp_name = str(comp.name)
                # Find parent OU
                # Find parent OU
                # Robust parent resolution:
                # Split by comma, remove the first component (CN=...), and join back.
                # This works for standard AD DNs.
                parts = comp_dn.split(",")
                if len(parts) > 1:
                    parent_dn = ",".join(parts[1:])
                else:
                    parent_dn = "Root"

                if parent_dn in tree:
                    tree[parent_dn]["children"].append({"name": comp_name, "type": "computer", "dn": comp_dn})
                else:
                    # Root or unknown parent
                    if "Root" not in tree:
                         tree["Root"] = {"type": "domain", "children": []}
                    tree["Root"]["children"].append({"name": comp_name, "type": "computer", "dn": comp_dn})
                    
            return tree
            
        except Exception as e:
            print(f"LDAP Error: {e}")
            return {"Error": {"type": "error", "name": str(e)}}

ldap_service = LDAPService()
