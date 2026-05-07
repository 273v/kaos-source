"""Typed dataclass models for eCFR API responses.

Mirrors the shapes returned by the eCFR REST API at
``https://www.ecfr.gov/api`` — titles, agencies, and the recursive
hierarchical structure (title → subtitle → chapter → subchapter → part
→ subpart → section).

Frozen + slotted where the record is immutable; ``ECFRStructureNode``
keeps the mutable+slotted shape because it carries a ``children`` list
populated incrementally by :func:`kaos_source.apis.ecfr.client._parse_structure`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ECFRTitle:
    """A CFR title (e.g. Title 40 — Protection of Environment)."""

    number: int
    name: str
    latest_amended_on: str | None = None
    latest_issue_date: str | None = None
    up_to_date_as_of: str | None = None
    reserved: bool = False


@dataclass(frozen=True, slots=True)
class ECFRAgency:
    """A CFR agency with references to titles/chapters."""

    name: str
    short_name: str = ""
    slug: str = ""
    cfr_references: list[dict[str, Any]] = field(default_factory=list)
    children: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ECFRStructureNode:
    """A node in the CFR hierarchical structure.

    Hierarchy: title → subtitle → chapter → subchapter → part → subpart → section
    """

    identifier: str
    type: str
    label: str
    label_level: str = ""
    label_description: str = ""
    reserved: bool = False
    children: list[ECFRStructureNode] = field(default_factory=list)

    def flatten(self) -> list[ECFRStructureNode]:
        """Flatten the tree to a list of all nodes."""
        result: list[ECFRStructureNode] = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result

    def find_sections(self) -> list[ECFRStructureNode]:
        """Find all section-type nodes in the subtree."""
        return [n for n in self.flatten() if n.type == "section"]

    def find_parts(self) -> list[ECFRStructureNode]:
        """Find all part-type nodes in the subtree."""
        return [n for n in self.flatten() if n.type == "part"]


__all__ = [
    "ECFRAgency",
    "ECFRStructureNode",
    "ECFRTitle",
]
