from fastapi import APIRouter
from models.schemas import Language, Level

router = APIRouter(prefix="/meta", tags=["Meta"])

@router.get("")
async def get_meta():
    return {
        "languages": [l.value for l in Language],
        "levels": [l.value for l in Level],
    }