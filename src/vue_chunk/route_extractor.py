import asyncio
import json
import os
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import PROJECTS_DIR


def _normalize_route_path(path):
    if path is None:
        return ""

    value = str(path).strip()
    if not value:
        return ""

    if value.startswith(("http://", "https://")):
        return value

    if value.startswith("#"):
        value = value[1:]

    value = value.strip()
    if not value or value == "*":
        return ""

    if not value.startswith("/"):
        value = "/" + value

    while "//" in value:
        value = value.replace("//", "/")

    return value


def _dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _normalize_join_path(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        return "/"
    if not value.startswith("/"):
        value = f"/{value}"
    while "//" in value:
        value = value.replace("//", "/")
    if len(value) > 1 and value.endswith("/"):
        value = value.rstrip("/")
    return value or "/"


def _join_history_path(base_path: str, route_path: str) -> str:
    right = _normalize_join_path(route_path)
    left = _normalize_join_path(base_path) if str(base_path or "").strip() else ""
    if not left:
        return right

    left_no = left.lstrip("/")
    right_no = right.lstrip("/")
    if right_no == left_no or right_no.startswith(f"{left_no}/"):
        return right
    if right == "/":
        return left
    return f"{left.rstrip('/')}/{right.lstrip('/')}"


def _infer_history_basepath(target_url: str, routes: list[dict]) -> str:
    raw = str(target_url or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if "#" in raw:
        return ""

    target_path = _normalize_join_path(parsed.path or "/")
    if target_path == "/":
        return ""

    route_paths: list[str] = []
    for item in routes:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_route_path(item.get("path"))
        if not normalized or normalized.startswith(("http://", "https://")):
            continue
        route_paths.append(_normalize_join_path(normalized))

    if not route_paths:
        return ""

    segments = [segment for segment in target_path.split("/") if segment]
    candidates = [""]
    prefix = ""
    for segment in segments:
        prefix = f"{prefix}/{segment}"
        candidates.append(prefix)

    best_candidate = ""
    best_score: tuple[int, int, int] = (-1, -1, 0)
    for candidate in candidates:
        max_route_len = 0
        hit = False
        for route_path in route_paths:
            composed = _normalize_join_path(_join_history_path(candidate, route_path))
            if composed == target_path:
                hit = True
                max_route_len = max(max_route_len, len(route_path))
        score = (1 if hit else 0, max_route_len, -len(candidate))
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_score[0] > 0:
        return _normalize_join_path(best_candidate) if best_candidate else ""
    return ""


def _build_full_url(target_url, route_path, history_basepath: str = ""):
    if route_path.startswith(("http://", "https://")):
        return route_path

    if "#" in target_url:
        hash_base = str(target_url or "").split("#", 1)[0].strip()
        if not hash_base:
            hash_base = str(target_url or "").strip()
        if not hash_base.endswith("/"):
            hash_base = f"{hash_base}/"
        return f"{hash_base}#/{route_path.lstrip('/')}"

    parsed = urlsplit((target_url or "").strip())
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    merged_path = _join_history_path(history_basepath, str(route_path or ""))
    return origin + merged_path


def _fallback_route_path(target_url: str) -> str:
    parsed = urlsplit((target_url or "").strip())
    fragment = str(parsed.fragment or "").strip()
    if fragment:
        if not fragment.startswith("/"):
            fragment = f"/{fragment}"
        return fragment
    path = str(parsed.path or "").strip() or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _build_navigation_candidates(target_url: str) -> list[str]:
    raw = str(target_url or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return [raw] if raw else []

    candidates: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        token = str(url or "").strip()
        if not token or token in seen:
            return
        seen.add(token)
        candidates.append(token)

    add(raw)

    path = parsed.path or "/"
    if path and path != "/":
        trimmed = path.rstrip("/")
        if trimmed and trimmed != path:
            add(urlunsplit((parsed.scheme, parsed.netloc, trimmed, parsed.query, parsed.fragment)))
        if not path.endswith("/"):
            add(urlunsplit((parsed.scheme, parsed.netloc, f"{path}/", parsed.query, parsed.fragment)))

    swapped_scheme = "http" if parsed.scheme.lower() == "https" else "https"
    add(urlunsplit((swapped_scheme, parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment)))

    return candidates


async def _collect_routes_via_runtime_probe(page) -> list[dict]:
    script = r"""
() => {
  function normalizePath(path) {
    if (path === undefined || path === null) return "";
    let value = String(path).trim();
    if (!value) return "";
    if (value.startsWith("http://") || value.startsWith("https://")) return value;
    if (value.startsWith("#")) value = value.slice(1);
    if (!value.startsWith("/")) value = "/" + value;
    value = value.replace(/\/{2,}/g, "/");
    if (value.length > 1 && value.endsWith("/")) value = value.slice(0, -1);
    return value || "/";
  }

  function joinPath(base, path) {
    const right = String(path || "").trim();
    if (!right) return normalizePath(base || "/");
    if (right.startsWith("/")) return normalizePath(right);
    const left = normalizePath(base || "/");
    if (!left || left === "/") return normalizePath("/" + right);
    return normalizePath(left + "/" + right);
  }

  function isRouterLike(router) {
    if (!router || typeof router !== "object") return false;
    return (
      typeof router.getRoutes === "function" ||
      !!(router.matcher && typeof router.matcher.getRoutes === "function") ||
      !!(router.options && Array.isArray(router.options.routes)) ||
      typeof router.push === "function"
    );
  }

  function findRouterFromProvides(provides) {
    if (!provides || typeof provides !== "object") return null;
    const keys = Object.keys(provides).concat(Object.getOwnPropertySymbols(provides));
    for (const key of keys) {
      const value = provides[key];
      if (isRouterLike(value)) return value;
    }
    return null;
  }

  function findVueRootNode() {
    const app = document.querySelector("#app");
    if (app && (app.__vue_app__ || app.__vue__ || app._vnode)) return app;
    const all = document.querySelectorAll("*");
    for (let i = 0; i < all.length; i += 1) {
      const node = all[i];
      if (node.__vue_app__ || node.__vue__ || node._vnode) return node;
    }
    return null;
  }

  function findVueRouter() {
    const root = findVueRootNode();
    if (!root) return null;
    try {
      if (root.__vue_app__) {
        const app = root.__vue_app__;
        const r1 = app?.config?.globalProperties?.$router;
        if (isRouterLike(r1)) return r1;
        const r2 = app?._instance?.appContext?.config?.globalProperties?.$router;
        if (isRouterLike(r2)) return r2;
        const r3 = app?._context ? findRouterFromProvides(app._context.provides) : null;
        if (isRouterLike(r3)) return r3;
      }
      if (root.__vue__) {
        const vue = root.__vue__;
        const candidates = [vue.$router, vue.$root?.$router, vue.$root?.$options?.router, vue._router];
        for (const candidate of candidates) {
          if (isRouterLike(candidate)) return candidate;
        }
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  function walkRouteTree(routes, basePath, add) {
    if (!Array.isArray(routes)) return;
    for (const route of routes) {
      if (!route || typeof route !== "object") continue;
      const fullPath = joinPath(basePath, route.path || "");
      add(route.name || "", fullPath);
      if (Array.isArray(route.children) && route.children.length > 0) {
        walkRouteTree(route.children, fullPath, add);
      }
    }
  }

  const router = findVueRouter();
  if (!router) return [];

  const rows = [];
  const seen = new Set();
  function addRoute(name, path) {
    const normalized = normalizePath(path);
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    rows.push({ name: String(name || ""), path: normalized });
  }

  try {
    if (typeof router.getRoutes === "function") {
      const current = router.getRoutes() || [];
      for (const item of current) {
        addRoute(item?.name || "", item?.path || "");
      }
    }
  } catch (_) {}

  try {
    if (router.matcher && typeof router.matcher.getRoutes === "function") {
      const current = router.matcher.getRoutes() || [];
      for (const item of current) {
        addRoute(item?.name || "", item?.path || "");
      }
    }
  } catch (_) {}

  try {
    if (router.options && Array.isArray(router.options.routes)) {
      walkRouteTree(router.options.routes, "", addRoute);
    }
  } catch (_) {}

  rows.sort((a, b) => {
    if (String(a.path) === String(b.path)) return String(a.name).localeCompare(String(b.name));
    return String(a.path).localeCompare(String(b.path));
  });
  return rows;
}
"""
    try:
        payload = await page.evaluate(script)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "name": str(item.get("name") or ""),
                "path": str(item.get("path") or ""),
            }
        )
    return rows


async def extract_routes(page, main_domain, target_url):
    route_map = {}
    route_event = asyncio.Event()
    analysis_state = {"received": False}

    def add_route(name, path):
        normalized_path = _normalize_route_path(path)
        if not normalized_path:
            return False

        route_name = str(name).strip() if name is not None else ""
        route_name = route_name or "(unnamed)"

        existing = route_map.get(normalized_path)
        if not existing:
            route_map[normalized_path] = {"name": route_name, "path": normalized_path}
            return True

        if existing["name"] == "(unnamed)" and route_name != "(unnamed)":
            existing["name"] = route_name
            return True

        return False

    def collect_route_candidates(payload):
        changed = False
        if isinstance(payload, list):
            for route in payload:
                if not isinstance(route, dict):
                    continue
                changed = add_route(
                    route.get("Name") or route.get("name"),
                    route.get("Path") or route.get("path"),
                ) or changed
            return changed

        if isinstance(payload, dict):
            changed = add_route(
                payload.get("Name") or payload.get("name"),
                payload.get("Path") or payload.get("path"),
            ) or changed

        return changed

    async def handle_console(msg):
        for arg in msg.args:
            value = None
            try:
                value = await arg.json_value()
            except Exception:
                try:
                    str_value = await arg.evaluate("obj => JSON.stringify(obj)")
                    if str_value:
                        value = json.loads(str_value)
                except Exception:
                    value = None

            if value is None:
                continue

            if msg.type == "table":
                if collect_route_candidates(value):
                    route_event.set()
                continue

            if isinstance(value, dict) and "allRoutes" in value:
                if collect_route_candidates(value.get("allRoutes")):
                    route_event.set()
                continue

            if collect_route_candidates(value):
                route_event.set()

    page.on("console", handle_console)

    async def handle_data_from_js(data):
        if not isinstance(data, dict):
            return
        if data.get("type") != "VUE_ROUTER_ANALYSIS_RESULT":
            return

        analysis_state["received"] = True
        result = data.get("result", {})
        collect_route_candidates(result.get("allRoutes", []))
        route_event.set()

    try:
        await page.expose_function("sendData", handle_data_from_js)
    except Exception as e:
        # Re-run safety: ignore duplicate registration on the same page.
        if "has been already registered" not in str(e):
            raise

    async def goto_with_retry(max_attempts=2):
        last_error = None
        candidates = _build_navigation_candidates(target_url)
        wait_modes = ("domcontentloaded", "commit")
        for candidate in candidates:
            for wait_mode in wait_modes:
                for attempt in range(1, max_attempts + 1):
                    try:
                        await page.goto(candidate, wait_until=wait_mode, timeout=90000)
                        return candidate, wait_mode
                    except Exception as e:
                        last_error = e
                        if attempt < max_attempts:
                            await page.wait_for_timeout(700 * attempt)
        raise last_error

    used_url = str(target_url or "").strip()
    used_wait_until = "domcontentloaded"
    navigation_error = ""

    async def wait_for_routes(timeout_ms=22000, poll_ms=300, stable_rounds=3):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000)
        last_count = -1
        stable_hits = 0

        while loop.time() < deadline:
            current_count = len(route_map)
            if current_count == last_count:
                stable_hits += 1
            else:
                stable_hits = 0

            # Route count stabilized.
            if current_count > 0 and stable_hits >= stable_rounds:
                return

            # Analysis already sent and no more change observed.
            if analysis_state["received"] and stable_hits >= 2:
                return

            last_count = current_count
            wait_s = min(poll_ms / 1000, max(0.0, deadline - loop.time()))
            if wait_s <= 0:
                break

            try:
                await asyncio.wait_for(route_event.wait(), timeout=wait_s)
                route_event.clear()
            except asyncio.TimeoutError:
                pass

    try:
        used_url, used_wait_until = await goto_with_retry(max_attempts=2)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass
        await wait_for_routes(timeout_ms=22000, poll_ms=300, stable_rounds=3)
        # Fallback probe: some sites register router/routes later than plugin callback.
        # Probe runtime router multiple times and keep merging to avoid seed-only result.
        for _ in range(4):
            runtime_routes = await _collect_routes_via_runtime_probe(page)
            if runtime_routes:
                collect_route_candidates(runtime_routes)
            if len(route_map) >= 2:
                break
            await page.wait_for_timeout(1200)
    except Exception as e:
        navigation_error = str(e)
        print(f"Target navigation failed: {e}")
    finally:
        page.remove_listener("console", handle_console)

    routes = sorted(route_map.values(), key=lambda item: (item["path"], item["name"]))
    if not routes:
        seed_path = _fallback_route_path(target_url)
        if seed_path:
            routes = [{"name": "(seed)", "path": seed_path}]

    history_basepath = _infer_history_basepath(target_url, routes)
    full_urls = _dedupe_keep_order(
        [_build_full_url(target_url, route["path"], history_basepath=history_basepath) for route in routes]
    )
    if not full_urls:
        full_urls = _dedupe_keep_order([str(target_url or "").strip()])

    outputs_dir = os.path.join(str(PROJECTS_DIR), main_domain)
    vue_router_dir = os.path.join(outputs_dir, "vueRouter")
    os.makedirs(vue_router_dir, exist_ok=True)

    routes_file = os.path.join(vue_router_dir, "routes.json")
    with open(routes_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "routes": routes,
                "meta": {
                    "target_url": str(target_url or "").strip(),
                    "used_url": used_url,
                    "used_wait_until": used_wait_until,
                    "navigation_error": navigation_error,
                    "history_basepath": history_basepath,
                },
            },
            f,
            ensure_ascii=False,
            indent=4,
        )
    print("\n\033[1m--- Save Path ---\033[0m")
    print(f"Routes saved to: \033[36m{routes_file}\033[0m")

    url_file = os.path.join(vue_router_dir, "urls.txt")
    with open(url_file, "w", encoding="utf-8") as f:
        f.write("\n".join(full_urls))
    print(f"URLs saved to: \033[36m{url_file}\033[0m\n")

    print("\033[1m--- Full URL List ---\033[0m")
    for idx, url in enumerate(full_urls, 1):
        print(f"{idx}. {url}")

    return full_urls
