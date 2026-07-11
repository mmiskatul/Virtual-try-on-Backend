from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdminDailyMetric(BaseModel):
    date: str
    count: int


class AdminCategoryPerformance(BaseModel):
    category: str
    try_on_count: int
    percentage: float


class AdminTopProduct(BaseModel):
    id: str
    name: str
    category: str
    image_url: str
    try_on_count: int


class AdminAnalyticsResponse(BaseModel):
    period_days: int
    period_start: datetime
    period_end: datetime
    total_tryons: int
    period_tryons: int
    previous_period_tryons: int
    period_change_percent: float | None = None
    total_products: int
    active_products: int
    unique_products_tried: int
    result_storage_bytes: int
    results_with_metadata: int
    latest_tryon_at: datetime | None = None
    daily_tryons: list[AdminDailyMetric]
    category_performance: list[AdminCategoryPerformance]
    top_products: list[AdminTopProduct]


class AdminStudioSettingsUpdate(BaseModel):
    high_fidelity_rendering: bool = True
    real_time_physics: bool = True
    precision_calibration: bool = False
    theme_accent: Literal["gold", "black", "red"] = "gold"
    typography: Literal["Libre Caslon Text", "Inter", "Georgia"] = "Libre Caslon Text"


class AdminAccountSummary(BaseModel):
    username: str
    is_active: bool
    last_login_at: datetime | None = None


class AdminStudioSettingsResponse(AdminStudioSettingsUpdate):
    updated_at: datetime | None = None
    updated_by: str | None = None
    administrators: list[AdminAccountSummary] = Field(default_factory=list)
