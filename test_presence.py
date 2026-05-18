import asyncio
import httpx

async def test_presence():
    url = "https://evolution-api-latest-qxsg.onrender.com"
    api_key = "Aseel.709293"
    
    # We don't have the exact instance name or phone, we just want to see if the endpoint exists (e.g. 404 vs 400).
    # Let's try to query instances first to get an instance name.
    
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        # Get instances
        res = await client.get(f"{url}/instance/fetchInstances", headers=headers)
        if res.status_code == 200:
            instances = res.json()
            if instances:
                instance = instances[0].get('instance', {}).get('instanceName')
                if instance:
                    print(f"Found instance: {instance}")
                    
                    # Test sendPresence
                    payload = {"number": "966579331312", "presence": "composing", "delay": 2000}
                    pres_res = await client.post(f"{url}/chat/sendPresence/{instance}", headers=headers, json=payload)
                    print(f"Presence Response {pres_res.status_code}: {pres_res.text}")
                else:
                    print("No instance name found")
        else:
            print(f"Failed to fetch instances: {res.status_code} {res.text}")

asyncio.run(test_presence())
