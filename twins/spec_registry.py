"""The schema registry: versioned OpenAPI specs on disk, one dir per
service + version. Picks a spec the way you'd pick an image tag.

Layout:  registry/<service>/<version>/openapi.json

Gives the twin three things: which template a request path matches, the
operation for (method, path), and the request/response JSON schemas.
"""
import json
import re
from pathlib import Path

REGISTRY = Path(__file__).parent / "registry"


class Spec:
    def __init__(self, doc: dict):
        self.doc = doc
        # Precompile each templated path: "/widgets/{id}" -> ^/widgets/[^/]+$
        self._paths = []
        for tmpl in doc.get("paths", {}):
            rx = "^" + re.sub(r"\{[^/]+\}", r"[^/]+", re.escape(tmpl).replace(r"\{", "{").replace(r"\}", "}")) + "$"
            self._paths.append((re.compile(rx), tmpl))

    def match(self, path: str) -> str | None:
        """Concrete path -> the template that declares it (or None)."""
        for rx, tmpl in self._paths:
            if rx.match(path):
                return tmpl
        return None

    def operation(self, method: str, path: str) -> dict | None:
        tmpl = self.match(path)
        if tmpl is None:
            return None
        return self.doc["paths"][tmpl].get(method.lower())

    def target(self, path: str) -> tuple[str, str | None] | None:
        """(resource, id) from the matched template — handles nested paths.

        /customers/{id}                  -> ("customers", "<val>")
        /crm/v3/objects/contacts         -> ("contacts", None)
        /crm/v3/objects/contacts/{id}    -> ("contacts", "<val>")
        /chat.postMessage                -> ("chat.postMessage", None)
        """
        tmpl = self.match(path)
        if tmpl is None:
            return None
        tparts = tmpl.strip("/").split("/")
        pparts = path.strip("/").split("/")
        # resource = last literal segment; id = trailing value only if the
        # template ends in a {param} (so mid-path {userId} is not mistaken for an id).
        resource = next((tp for tp in reversed(tparts) if not tp.startswith("{")), None)
        rid = pparts[-1] if tparts[-1].startswith("{") else None
        return resource, rid

    @staticmethod
    def request_schema(op: dict) -> dict | None:
        try:
            return op["requestBody"]["content"]["application/json"]["schema"]
        except (KeyError, TypeError):
            return None

    @staticmethod
    def response_schema(op: dict, status: int) -> dict | None:
        resps = op.get("responses", {})
        r = resps.get(str(status)) or resps.get("default")
        try:
            return r["content"]["application/json"]["schema"]
        except (KeyError, TypeError):
            return None

    @property
    def components(self) -> dict:
        return self.doc.get("components", {})


def load(service: str, version: str) -> Spec:
    path = REGISTRY / service / version / "openapi.json"
    return Spec(json.loads(path.read_text()))


def _demo():
    spec = Spec({"paths": {
        "/widgets": {"post": {}, "get": {}},
        "/widgets/{id}": {"get": {}, "delete": {}},
    }})
    assert spec.match("/widgets") == "/widgets"
    assert spec.match("/widgets/abc-123") == "/widgets/{id}"
    assert spec.match("/widgets/abc/extra") is None
    assert spec.match("/unknown") is None
    assert spec.operation("POST", "/widgets") == {}
    assert spec.operation("DELETE", "/widgets/x") == {}
    assert spec.operation("PUT", "/widgets/x") is None  # method not declared

    nested = Spec({"paths": {
        "/crm/v3/objects/contacts": {"get": {}},
        "/crm/v3/objects/contacts/{id}": {"get": {}},
        "/gmail/v1/users/{userId}/messages": {"get": {}},
        "/gmail/v1/users/{userId}/messages/{id}": {"get": {}},
    }})
    assert nested.target("/crm/v3/objects/contacts") == ("contacts", None)
    assert nested.target("/crm/v3/objects/contacts/501") == ("contacts", "501")
    # mid-path {userId} must NOT be read as the id:
    assert nested.target("/gmail/v1/users/me/messages") == ("messages", None)
    assert nested.target("/gmail/v1/users/me/messages/abc") == ("messages", "abc")
    assert spec.target("/widgets/abc") == ("widgets", "abc")
    print("ok")


if __name__ == "__main__":
    _demo()
