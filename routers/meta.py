from fastapi import APIRouter
from core.database import languages_col, levels_col

router = APIRouter(prefix="/meta", tags=["Meta"])

@router.get("")
async def get_meta():
    langs = await languages_col().find(
        {}, {"_id": 0, "code": 1, "display_name": 1, "native_symbol": 1, "roman_symbol": 1, "speech_code": 1}
    ).to_list(None)
    
    lvls = await levels_col().find(
        {}, {"_id": 0, "code": 1, "description": 1, "default_scenario": 1, "scenarios": 1}
    ).sort("code", 1).to_list(None)

    return {
        "languages": langs,
        "levels": lvls,
    }