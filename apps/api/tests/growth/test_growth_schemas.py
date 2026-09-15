"""Schema tests for realmock.domains.growth.schemas.

Covers: package importability reservation for future models.
Conventions: import-only; no I/O.
"""

from __future__ import annotations


def test_growth_schemas_package_importable() -> None:
    import realmock.domains.growth.schemas as schemas

    assert schemas.__name__.endswith("growth.schemas")
