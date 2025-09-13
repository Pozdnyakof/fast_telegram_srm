import asyncio
from app.services.db import Database

async def main():
    db = Database('./data/app.db')
    await db.init_db()
    await db.upsert_channel(987654321, 'Smoke Sheet')
    name = await db.get_sheet_name(987654321)
    print('DB_SMOKE_RESULT:', name)

if __name__ == '__main__':
    asyncio.run(main())
