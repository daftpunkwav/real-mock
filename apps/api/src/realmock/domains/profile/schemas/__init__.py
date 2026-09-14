"""Profile domain schema exports.

Public surface:
- ``UserProfileResponse`` / ``UserProfileUpdate`` — HTTP contracts
- ``REQUIRED_STRING_FIELDS`` — required string keys (not tech_domains)
- ``clean_tech_domains`` — shared strip/dedupe helper

ORM coerce and PUT normalize helpers stay in ``tech_domains``; import them
from that module if a caller outside HTTP needs them.
"""

from realmock.domains.profile.schemas.required import REQUIRED_STRING_FIELDS
from realmock.domains.profile.schemas.response import UserProfileResponse
from realmock.domains.profile.schemas.tech_domains import clean_tech_domains
from realmock.domains.profile.schemas.update import UserProfileUpdate

__all__ = [
    "REQUIRED_STRING_FIELDS",
    "UserProfileResponse",
    "UserProfileUpdate",
    "clean_tech_domains",
]
