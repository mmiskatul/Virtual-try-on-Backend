from pydantic import BaseModel, Field, field_validator


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class AdminLoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
