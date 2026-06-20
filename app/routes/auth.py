from fastapi import APIRouter, Depends, HTTPException, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.database import get_db
from app.models.auth import AdminLoginRequest, AdminLoginResponse
from app.utils.auth import create_admin_access_token, require_admin
from app.utils.passwords import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    payload: AdminLoginRequest,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AdminLoginResponse:
    admin_user = await db.admin_users.find_one({"username": payload.username, "is_active": True})
    if not admin_user or not verify_password(
        payload.password,
        admin_user["password_hash"],
        admin_user["salt"],
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )

    access_token = create_admin_access_token(admin_user["username"])
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    return AdminLoginResponse(token=access_token)


@router.post("/logout")
async def admin_logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"detail": "Logged out."}


@router.get("/me")
async def admin_me(username: str = Depends(require_admin)) -> dict[str, str]:
    return {"username": username}
