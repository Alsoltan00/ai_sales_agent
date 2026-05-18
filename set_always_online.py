import asyncio
import httpx
from database.db_client import get_db_client

async def main():
    db = get_db_client()
    
    # Get Evolution API credentials
    res = await db.table("global_settings").select("value").eq("key", "evolution_api").single().execute_async()
    if not res.data:
        print("No global settings found.")
        return
        
    value = res.data.get("value", {})
    server_url = value.get("url", "").rstrip("/")
    api_key = value.get("api_key", "")
    
    # Get all active instances
    configs = await db.table("channels_config").select("evolution_instance_name").execute_async()
    
    async with httpx.AsyncClient() as client:
        for config in configs.data:
            instance = config.get("evolution_instance_name")
            if instance:
                print(f"Setting alwaysOnline for {instance}...")
                try:
                    r = await client.post(
                        f"{server_url}/settings/set/{instance}",
                        json={"alwaysOnline": True},
                        headers={"apikey": api_key, "Content-Type": "application/json"},
                        timeout=5
                    )
                    print(f"Response: {r.status_code} - {r.text}")
                except Exception as e:
                    print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
