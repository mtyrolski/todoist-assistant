"""FastAPI route aggregator for the web API."""

from fastapi import APIRouter

from todoist.web.routes.admin_settings import router as _admin_settings_router
from todoist.web.routes.dashboard import router as _dashboard_router
from todoist.web.routes.llm_chat import router as _llm_chat_router
from todoist.web.routes.runtime_admin import router as _runtime_admin_router
from todoist.web.routes.task_status import router as _task_status_router

router = APIRouter()
router.include_router(_dashboard_router)
router.include_router(_llm_chat_router)
router.include_router(_runtime_admin_router)
router.include_router(_task_status_router)
router.include_router(_admin_settings_router)
