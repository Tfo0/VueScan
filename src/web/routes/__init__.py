from src.web.routes.core_bundle import CoreRouteBundle, CoreRouteBundleDeps, build_core_route_bundle
from src.web.routes.frontend import FrontendRouteDeps, build_frontend_app_handler, build_frontend_routes
from src.web.routes.pages import PageRouteDeps, build_page_routes
from src.web.routes.system import SystemRouteDeps, build_system_routes
from src.web.routes.vue_api import VueApiRouteDeps, build_vue_api_routes
from src.web.routes.vue_api_actions import VueApiActionRouteDeps, build_vue_api_action_routes
from src.web.routes.vue_api_bundle import VueApiRouteBundle, VueApiRouteBundleDeps, build_vue_api_route_bundle
from src.web.routes.vue_chunk import VueChunkRouteDeps, build_vue_chunk_routes
from src.web.routes.vue_chunk_actions import VueChunkActionRouteDeps, build_vue_chunk_action_routes
from src.web.routes.vue_chunk_bundle import VueChunkRouteBundle, VueChunkRouteBundleDeps, build_vue_chunk_route_bundle
from src.web.routes.vue_detect import VueDetectRouteDeps, build_vue_detect_routes
from src.web.routes.vue_detect_actions import VueDetectActionRouteDeps, build_vue_detect_action_routes
from src.web.routes.vue_detect_bundle import VueDetectRouteBundle, VueDetectRouteBundleDeps, build_vue_detect_route_bundle
from src.web.routes.vue_request import VueRequestRouteDeps, build_vue_request_routes
from src.web.routes.vue_request_actions import VueRequestActionRouteDeps, build_vue_request_action_routes
from src.web.routes.vue_request_bundle import VueRequestRouteBundle, VueRequestRouteBundleDeps, build_vue_request_route_bundle

__all__ = [
    "CoreRouteBundle",
    "CoreRouteBundleDeps",
    "FrontendRouteDeps",
    "PageRouteDeps",
    "SystemRouteDeps",
    "VueApiRouteDeps",
    "VueApiActionRouteDeps",
    "VueApiRouteBundle",
    "VueApiRouteBundleDeps",
    "VueChunkRouteDeps",
    "VueChunkActionRouteDeps",
    "VueChunkRouteBundle",
    "VueChunkRouteBundleDeps",
    "VueDetectRouteDeps",
    "VueDetectActionRouteDeps",
    "VueDetectRouteBundle",
    "VueDetectRouteBundleDeps",
    "VueRequestRouteDeps",
    "VueRequestActionRouteDeps",
    "VueRequestRouteBundle",
    "VueRequestRouteBundleDeps",
    "build_core_route_bundle",
    "build_frontend_app_handler",
    "build_frontend_routes",
    "build_page_routes",
    "build_system_routes",
    "build_vue_api_routes",
    "build_vue_api_action_routes",
    "build_vue_api_route_bundle",
    "build_vue_chunk_routes",
    "build_vue_chunk_action_routes",
    "build_vue_chunk_route_bundle",
    "build_vue_detect_routes",
    "build_vue_detect_action_routes",
    "build_vue_detect_route_bundle",
    "build_vue_request_routes",
    "build_vue_request_action_routes",
    "build_vue_request_route_bundle",
]
