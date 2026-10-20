import asyncio, os

os.kill(os.getpid(), 0)
print("after kill, alive", flush=True)

async def f():
    await asyncio.sleep(0.01)
    return 1

print("asyncio result:", asyncio.run(f()))
