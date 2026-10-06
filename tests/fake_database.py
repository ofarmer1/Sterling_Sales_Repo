"""A tiny in-memory stand-in for the Supabase client, used only in tests.

It supports just the calls settings_store.py makes:
    client.table(name).select("*").eq("id", 1).limit(1).execute()
    client.table(name).upsert(row).execute()
"""


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.action = None
        self.row = None
        self.filters = {}

    def select(self, columns):
        self.action = "select"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, count):
        return self

    def upsert(self, row):
        self.action = "upsert"
        self.row = row
        return self

    def execute(self):
        if self.database.fail_with:
            raise self.database.fail_with
        rows = self.database.tables.setdefault(self.table, {})
        if self.action == "upsert":
            self.database.upsert_calls += 1
            if self.database.confirm_writes:
                rows[self.row["id"]] = dict(self.row)
                return FakeResponse([dict(self.row)])
            return FakeResponse([])
        matches = [
            dict(row)
            for row in rows.values()
            if all(row.get(k) == v for k, v in self.filters.items())
        ]
        return FakeResponse(matches)


class FakeDatabase:
    def __init__(self):
        self.tables = {}
        self.fail_with = None  # set to an exception to simulate an outage
        self.confirm_writes = True  # False simulates a write with no data back
        self.upsert_calls = 0

    def table(self, name):
        return FakeQuery(self, name)
