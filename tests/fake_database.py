"""A tiny in-memory stand-in for the Supabase client, used only in tests.

It supports just the calls the app makes, for example:
    client.table(name).select("*").eq("id", 1).limit(1).execute()
    client.table(name).upsert(row).execute()
    client.table(name).insert(rows).execute()
    client.table(name).update(changes).eq("id", 1).execute()
"""

import copy


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.action = None
        self.payload = None
        self.filters = {}
        self.order_by = None

    def select(self, columns):
        self.action = "select"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def limit(self, count):
        return self

    def order(self, column, desc=False):
        self.order_by = column
        return self

    def upsert(self, row):
        self.action, self.payload = "upsert", row
        return self

    def insert(self, rows):
        self.action, self.payload = "insert", rows
        return self

    def update(self, changes):
        self.action, self.payload = "update", changes
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self.filters.items())

    def execute(self):
        db = self.database
        if db.fail_with or self.table in db.fail_tables:
            raise db.fail_with or ConnectionError(f"{self.table} is down")
        rows = db.tables.setdefault(self.table, {})

        if self.action == "upsert":
            db.upsert_calls += 1
            if not db.confirm_writes:
                return FakeResponse([])
            rows[self.payload["id"]] = copy.deepcopy(self.payload)
            return FakeResponse([copy.deepcopy(self.payload)])

        if self.action == "insert":
            new_rows = self.payload if isinstance(self.payload, list) else [self.payload]
            keys = {r.get("company_key") for r in rows.values()}
            for row in new_rows:
                if row.get("company_key") and row["company_key"] in keys:
                    raise ValueError("duplicate key value violates unique constraint")
            saved = []
            for row in new_rows:
                db.next_id += 1
                full = {**db.defaults.get(self.table, {}), **copy.deepcopy(row), "id": db.next_id}
                rows[db.next_id] = full
                saved.append(copy.deepcopy(full))
            return FakeResponse(saved)

        if self.action == "update":
            if not db.confirm_writes:
                return FakeResponse([])
            changed = []
            for row in rows.values():
                if self._matches(row):
                    row.update(copy.deepcopy(self.payload))
                    changed.append(copy.deepcopy(row))
            return FakeResponse(changed)

        matches = [copy.deepcopy(r) for r in rows.values() if self._matches(r)]
        if self.order_by:
            matches.sort(key=lambda r: r.get(self.order_by))
        return FakeResponse(matches)


# Column defaults from supabase/schema.sql, so inserted rows look real.
LEAD_DEFAULTS = {
    "website": "", "source": "provided", "discovery_reason": "", "discovery_sources": [],
    "status": "new", "research": None, "research_sources": [], "researched_at": None,
    "research_error": "", "qualification": None, "qualification_result": "",
    "email_subject": "", "email_body": "", "linkedin_note": "",
    "drafts_generated_at": None, "drafts_edited_at": None, "notes": "",
}


class FakeDatabase:
    def __init__(self):
        self.tables = {}
        self.fail_with = None  # set to an exception to simulate an outage
        self.fail_tables = set()  # names of tables that are "down"
        self.confirm_writes = True  # False simulates a write with no data back
        self.upsert_calls = 0
        self.next_id = 0
        self.defaults = {"leads": LEAD_DEFAULTS}

    def table(self, name):
        return FakeQuery(self, name)
