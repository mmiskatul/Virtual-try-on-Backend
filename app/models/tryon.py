from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TryOnGenerateRequest(BaseModel):
    user_image_url: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    selected_size: str = Field(..., min_length=1, max_length=10)
    user_body_size: str = Field(..., min_length=1, max_length=10)
    user_size_details: str | None = Field(default=None, max_length=500)
    prompt_optional: str | None = Field(default=None, max_length=1000)



class TryOnImageDetails(BaseModel):
    provider: str
    model: str
    request_id: str | None = None
    source_result_url: str | None = None
    content_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    seed: int | None = None


class TryOnResultResponse(BaseModel):
    id: str
    user_image_url: str
    product_id: str
    product_name: str
    garment_image_url: str
    result_image_url: str
    prompt: str
    selected_size: str | None = None
    user_body_size: str | None = None
    image_details: TryOnImageDetails | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
