"""HubSpot twin: CRM v3. Numeric ids, properties-wrapped objects, createdAt/
updatedAt/archived, and {results:[…], total} list envelope. Nested paths
(/crm/v3/objects/contacts/{id}) resolve via spec.target.
"""
import random
import time

from twins.engine import Twin


class HubSpotTwin(Twin):
    def new_id(self, resource):
        return str(random.randint(10**11, 10**12 - 1))  # HubSpot ids are numeric strings

    def on_create(self, resource, body):
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        return {"id": self.new_id(resource), "properties": body.get("properties", {}),
                "createdAt": now, "updatedAt": now, "archived": False}

    def wrap_list(self, resource, rows):
        return {"results": rows, "total": len(rows)}


def _demo():
    import sqlite3
    t = HubSpotTwin(sqlite3.connect(":memory:"))
    c, st = t.create("contacts", {"properties": {"email": "a@b.c", "firstname": "Al"}})
    assert st == 201 and c["id"].isdigit() and c["properties"]["email"] == "a@b.c", c
    assert c["archived"] is False and "createdAt" in c
    lst = t.wrap_list("contacts", [c])
    assert lst["total"] == 1 and lst["results"][0]["id"] == c["id"], lst
    print("ok")


if __name__ == "__main__":
    _demo()
