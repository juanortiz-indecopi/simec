"""Recorrido del JSON que las páginas traen incrustado en <script type="application/json">."""
import json
from collections.abc import Iterator
from typing import Any


def iter_dicts(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for child in node.values():
            yield from iter_dicts(child)
    elif isinstance(node, list):
        for child in node:
            yield from iter_dicts(child)


def nodes(scripts: list[str], marker: str) -> Iterator[dict[str, Any]]:
    """Objetos de los scripts que contienen `marker`."""
    for script in scripts:
        if marker not in script:
            continue
        try:
            root = json.loads(script)
        except ValueError:
            continue
        yield from iter_dicts(root)
