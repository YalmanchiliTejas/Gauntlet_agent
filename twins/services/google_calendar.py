"""Google Calendar twin: calendars.events. insert returns the Event at HTTP 200
with status=confirmed, kind, htmlLink, created/updated; list returns
{kind:"calendar#events", items:[…]}. {calendarId} is ignored (single calendar).
"""
import time
import uuid

from twins.engine import Twin


class GoogleCalendarTwin(Twin):
    def new_id(self, resource):
        return uuid.uuid4().hex[:26]

    def on_create(self, resource, body):
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        eid = self.new_id(resource)
        return {**body, "id": eid, "status": "confirmed", "kind": "calendar#event",
                "htmlLink": f"https://www.google.com/calendar/event?eid={eid}",
                "created": now, "updated": now}

    def create(self, resource, body):
        rec, _ = super().create(resource, body)   # store
        return rec, 200                            # Calendar insert returns 200

    def wrap_list(self, resource, rows):
        return {"kind": "calendar#events", "items": rows}


def _demo():
    import sqlite3
    t = GoogleCalendarTwin(sqlite3.connect(":memory:"))
    ev, st = t.create("events", {"summary": "Standup",
                                 "start": {"dateTime": "2026-07-01T10:00:00Z"},
                                 "end": {"dateTime": "2026-07-01T10:15:00Z"}})
    assert st == 200 and ev["status"] == "confirmed" and ev["kind"] == "calendar#event", ev
    assert ev["summary"] == "Standup" and ev["htmlLink"]
    lst = t.wrap_list("events", [ev])
    assert lst["kind"] == "calendar#events" and lst["items"][0]["id"] == ev["id"], lst
    print("ok")


if __name__ == "__main__":
    _demo()
