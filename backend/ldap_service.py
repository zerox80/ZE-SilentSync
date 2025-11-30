from typing import List, Dict, Any
from ldap3 import Server, Connection, ALL, SUBTREE
from config import settings

class LDAPService:
    def __init__(self):
        self.mock_structure = {
            "DC=example,DC=com": {
                "OU=Management": {
                    "CN=AdminPC": {"type": "computer", "dn": "CN=AdminPC,OU=Management,DC=example,DC=com"},
                    "CN=ManagerLaptop": {"type": "computer", "dn": "CN=ManagerLaptop,OU=Management,DC=example,DC=com"}
                },
                "OU=Sales": {
                    "CN=Sales01": {"type": "computer", "dn": "CN=Sales01,OU=Sales,DC=example,DC=com"},
                    "CN=Sales02": {"type": "computer", "dn": "CN=Sales02,OU=Sales,DC=example,DC=com"}
                },
                "OU=IT": {
                    "CN=DevWorkstation": {"type": "computer", "dn": "CN=DevWorkstation,OU=IT,DC=example,DC=com"}
                }
            }
        }

    def get_ou_tree(self) -> Dict[str, Any]:
        """Returns the full OU structure."""
        if settings.USE_MOCK_LDAP:
            return self.mock_structure
        
        return self._fetch_real_ad_structure()

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
                parent_dn = ",".join(comp_dn.split(",")[1:])
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
