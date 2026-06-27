"""Excel twin (Microsoft Graph workbook): add/list table rows and list
worksheets. Collections use the Graph {value:[…]} envelope; rows get a
sequential index and @odata.id. Table/worksheet ids in the path are ignored.
"""
import uuid

from twins.engine import Twin


class ExcelTwin(Twin):
    def new_id(self, resource):
        return uuid.uuid4().hex[:8]

    def on_create(self, resource, body):           # resource == "rows"
        index = len(self._all("rows"))             # next index (pre-insert count)
        return {"id": self.new_id(resource), "index": index,
                "values": body.get("values", []),
                "@odata.id": f"/workbook/tables/rows/itemAt(index={index})"}

    def wrap_list(self, resource, rows):
        return {"value": rows}


def _demo():
    import sqlite3
    t = ExcelTwin(sqlite3.connect(":memory:"))
    r0, st = t.create("rows", {"values": [["a", "b", 1]]})
    r1, _ = t.create("rows", {"values": [["c", "d", 2]]})
    assert st == 201 and r0["index"] == 0 and r1["index"] == 1, (r0, r1)
    lst = t.wrap_list("rows", t._all("rows"))
    assert "value" in lst and len(lst["value"]) == 2, lst
    print("ok")


if __name__ == "__main__":
    _demo()
