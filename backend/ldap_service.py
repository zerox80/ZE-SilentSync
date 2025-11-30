from typing import List, Dict, Any

class MockLDAPService:
    def __init__(self):
        # Simulated AD Structure
        self.structure = {
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
        return self.structure

    def get_computers_in_ou(self, ou_dn: str) -> List[Dict[str, str]]:
        """Returns a list of computers in a specific OU (mock implementation)."""
        # Simplified traversal for the mock
        computers = []
        # In a real implementation, we would query LDAP.
        # Here we just return some dummy data based on the string for demo purposes
        if "Sales" in ou_dn:
             computers.append({"name": "Sales01", "dn": "CN=Sales01,OU=Sales,DC=example,DC=com"})
             computers.append({"name": "Sales02", "dn": "CN=Sales02,OU=Sales,DC=example,DC=com"})
        elif "Management" in ou_dn:
             computers.append({"name": "AdminPC", "dn": "CN=AdminPC,OU=Management,DC=example,DC=com"})
        
        return computers

ldap_service = MockLDAPService()
