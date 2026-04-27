import httpx
import asyncio

async def test():
    api_key = "AlzaSyAPAT6_5vmpC7nty7ECbzXWrpn6XwPl0ZI" # From user's screenshot
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        print(res.status_code)
        print(res.text)

if __name__ == "__main__":
    asyncio.run(test())
