"""Position, company and other options API."""

from fastapi import APIRouter

from realmock.domains.interview.options_data import build_options_payload
from realmock.domains.interview.schemas import OptionsResponse

router = APIRouter()


@router.get("", response_model=OptionsResponse)
def get_options():
    return OptionsResponse(**build_options_payload())
