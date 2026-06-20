from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Gender(str, Enum):
    male = "male"
    female = "female"
    unisex = "unisex"


class Category(str, Enum):
    shirt = "shirt"
    t_shirt = "t-shirt"
    pant = "pant"
    kurti = "kurti"
    dress = "dress"


class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    gender: Gender
    category: Category
    image_url: HttpUrl | str
    price: float = Field(..., ge=0)
    description: str = Field(..., min_length=5, max_length=500)
    is_active: bool = True


class ProductCreate(ProductBase):
    id: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    gender: Gender | None = None
    category: Category | None = None
    image_url: HttpUrl | str | None = None
    price: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, min_length=5, max_length=500)
    is_active: bool | None = None


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    detail: str
