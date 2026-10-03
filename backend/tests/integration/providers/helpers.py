"""Small helpers shared by the REST connector driver tests."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse


def json_body(call: Any) -> Any:
    """Decode the JSON body of a recorded ``responses`` call."""
    body = call.request.body
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    return json.loads(body)


def form_body(call: Any) -> Dict[str, str]:
    """Decode an ``application/x-www-form-urlencoded`` body of a recorded call."""
    body = call.request.body
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    return {k: v[0] for k, v in parse_qs(body).items()}


def query_params(call: Any) -> Dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


def decoded_url(call: Any) -> str:
    """Full URL with percent-escapes decoded (handy for OData ``$filter`` assertions)."""
    return unquote(call.request.url)


def calls_matching(rsps: Any, method: Optional[str] = None, contains: str = "") -> List[Any]:
    return [
        c
        for c in rsps.calls
        if (method is None or c.request.method == method) and contains in unquote(c.request.url)
    ]
