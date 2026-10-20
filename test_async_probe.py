import asyncio

def test_async_probe():
    async def f():
        await asyncio.sleep(0.01)
        return 42
    assert asyncio.run(f()) == 42
