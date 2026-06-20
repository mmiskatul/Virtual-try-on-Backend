from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TryOnGenerateRequest(BaseModel):
    user_image_url: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    prompt_optional: str | None = Field(default=None, max_length=1000)


class TryOnResultResponse(BaseModel):
    id: str
    user_image_url: str
    product_id: str
    product_name: str
    garment_image_url: str
    result_image_url: str
    prompt: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
