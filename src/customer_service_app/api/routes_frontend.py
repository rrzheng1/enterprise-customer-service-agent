from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from customer_service_app.core.config import get_settings

router = APIRouter(tags=["frontend"])
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


class UIConfigView(BaseModel):
    api_prefix: str
    authentication_required: bool


@router.get("/ui/config", response_model=UIConfigView)
async def ui_config() -> UIConfigView:
    settings = get_settings()
    return UIConfigView(api_prefix=settings.api_prefix, authentication_required=settings.security_enabled
                        or settings.runtime_env.lower() not in {"local", "development", "test"})


@router.get("/", include_in_schema=False)
@router.get("/chat", include_in_schema=False)
@router.get("/chat/{conversation_id}", include_in_schema=False)
@router.get("/operations", include_in_schema=False)
@router.get("/demo", include_in_schema=False)
async def product_page(conversation_id: str | None = None):
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return HTMLResponse("<html lang='zh-CN'><meta charset='utf-8'><title>前端尚未构建</title>"
        "<h1>智能客服工作空间</h1><p>请在 frontend 目录执行 npm ci 和 npm run build，"
        "或使用 Vite 开发服务器。</p><a href='/ops'>打开原验证台</a></html>", status_code=503)


@router.get("/assets/{asset_path:path}", include_in_schema=False)
async def frontend_asset(asset_path: str):
    root = (FRONTEND_DIST / "assets").resolve()
    path = (root / asset_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(path)
