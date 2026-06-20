from fastapi import APIRouter, File, UploadFile

from app.services.file_service import save_upload_file

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/user-photo")
async def upload_user_photo(file: UploadFile = File(...)) -> dict[str, str]:
    image_url = await save_upload_file(file)
    return {"image_url": image_url}
