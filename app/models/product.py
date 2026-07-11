from datetime import datetime
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


class Coverage(str, Enum):
    upper = "upper"
    lower = "lower"
    full = "full"
    accessory = "accessory"


class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    gender: Gender
    category: Category
    image_url: HttpUrl | str
    price: float = Field(..., ge=0)
    description: str = Field(..., min_length=5, max_length=500)
    materials: str | None = Field(default=None, max_length=300)
    cloth_type: str | None = Field(default=None, max_length=100)
    coverage: Coverage | None = None
    available_sizes: list[str] = Field(default_factory=list)
    size_details: str | None = Field(default=None, max_length=1000)
    fit_type: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    occasion: str | None = Field(default=None, max_length=100)
    care_instructions: str | None = Field(default=None, max_length=300)
    brand: str | None = Field(default=None, max_length=80)
    is_active: bool = True


class ProductCreate(ProductBase):
    id: str | None = Field(default=None, max_length=80)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    gender: Gender | None = None
    category: Category | None = None
    image_url: HttpUrl | str | None = None
    price: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, min_length=5, max_length=500)
    materials: str | None = Field(default=None, max_length=300)
    cloth_type: str | None = Field(default=None, max_length=100)
    coverage: Coverage | None = None
    available_sizes: list[str] | None = None
    size_details: str | None = Field(default=None, max_length=1000)
    fit_type: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    occasion: str | None = Field(default=None, max_length=100)
    care_instructions: str | None = Field(default=None, max_length=300)
    brand: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)


class AdminDashboardProduct(ProductResponse):
    try_on_count: int = 0
    last_try_on_at: datetime | None = None


class AdminRecentTryOn(BaseModel):
    id: str
    product_id: str
    product_name: str
    user_image_url: str
    garment_image_url: str
    result_image_url: str
    created_at: datetime


class AdminDailyTryOnCount(BaseModel):
    date: str
    count: int


class AdminDashboardSummary(BaseModel):
    total_products: int
    active_products: int
    inactive_products: int
    total_tryons: int
    tryons_today: int
    tryons_last_7_days: list[AdminDailyTryOnCount]
    top_product_name: str | None = None
    top_product_try_on_count: int = 0
    recent_products: list[ProductResponse]
    products: list[AdminDashboardProduct]
    recent_tryons: list[AdminRecentTryOn]


class ErrorResponse(BaseModel):
    detail: str
