"""Small unit-double support; real Lua is qualified in integration tests."""


class AdmissionLuaDouble:
    async def eval(self, script, count, *args):
        keys, values = args[:count], args[count:]
        if script.startswith("-- execution:release"):
            if await self.get(keys[0]) == values[0]:
                await self.delete(keys[0])
                return 1
            return 0
        if script.startswith("-- execution:finalize"):
            if (
                await self.get(keys[0]) != values[0]
                or await self.get(keys[1]) != values[1]
            ):
                return 0
            await self.set(keys[2], values[2])
            await self.set(keys[1], values[3])
            return 1
        raise AssertionError("Unexpected script in unit double")
