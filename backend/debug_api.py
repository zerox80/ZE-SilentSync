import httpx
import asyncio
from config import settings

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient() as client:
        # 1. Login
        print(f"Logging in with admin / {settings.SECRET_KEY[:5]}...")
        try:
            resp = await client.post(f"{BASE_URL}/auth/token", data={
                "username": "admin",
                "password": settings.SECRET_KEY
            })
            if resp.status_code != 200:
                print(f"Login Failed: {resp.status_code} {resp.text}")
                # Try default just in case
                resp = await client.post(f"{BASE_URL}/auth/token", data={
                    "username": "admin",
                    "password": "unsafe-secret-key-change-me"
                })
                if resp.status_code != 200:
                    print("Login failed with default key too.")
                    return
            
            token = resp.json()["access_token"]
            print("Login Success!")
            headers = {"Authorization": f"Bearer {token}"}
            
            # 2. Get AD Tree
            print("\n--- AD TREE ---")
            resp = await client.get(f"{BASE_URL}/management/ad/tree", headers=headers)
            print(resp.json())
            
            # 3. Get Software
            print("\n--- SOFTWARE ---")
            resp = await client.get(f"{BASE_URL}/management/software", headers=headers)
            print(resp.json())
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
