"""Position, company and other options API."""

from fastapi import APIRouter

from realmock.domains.interview.routes.options_data import build_options_payload
from realmock.domains.interview.schemas import OptionsResponse

router = APIRouter()


@router.get("", response_model=OptionsResponse)
def get_options():
    """Setup-page dropdown payload (workflows / personalities / voices / avatars)."""
    return OptionsResponse(**build_options_payload())
