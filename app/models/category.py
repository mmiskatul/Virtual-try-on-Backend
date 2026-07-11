from pydantic import BaseModel, Field, field_validator

from app.utils.categories import format_category_label, normalize_category_value


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class CategoryResponse(BaseModel):
    value: str
    label: str

    @classmethod
    def from_name(cls, name: str) -> "CategoryResponse":
        normalized_value = normalize_category_value(name)
        return cls(value=normalized_value, label=format_category_label(normalized_value))
