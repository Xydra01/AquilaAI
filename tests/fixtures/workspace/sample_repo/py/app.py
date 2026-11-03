import functools


@functools.cache
def cached(n):
    return n * 2


class Store:
    def __init__(self):
        self.items = []

    def add(self, item):
        def check(x):
            return x is not None

        if check(item):
            self.items.append(item)

    async def flush(self):
        return len(self.items)
