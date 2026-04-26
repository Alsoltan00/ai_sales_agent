import httpx
import asyncio

async def run():
    res = await httpx.AsyncClient().post(
        'http://localhost:8000/api/auth/login',
        json={'contact_info': 'admin@ai-sales.com', 'password': 'admin'}
    )
    print(res.status_code)
    print(res.text)

if __name__ == "__main__":
    asyncio.run(run())
