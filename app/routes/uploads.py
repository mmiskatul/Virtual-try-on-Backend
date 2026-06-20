from fastapi import APIRouter, Depends, File, UploadFile

from app.services.file_service import save_product_image, save_user_photo
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/user-photo")
async def upload_user_photo(file: UploadFile = File(...)) -> dict[str, str]:
    image_url = await save_user_photo(file)
    return {"image_url": image_url}


@router.post("/product-image")
async def upload_product_image(
    file: UploadFile = File(...),
    _: None = Depends(require_admin),
) -> dict[str, str]:
    image_url = await save_product_image(file)
    return {"image_url": image_url}
