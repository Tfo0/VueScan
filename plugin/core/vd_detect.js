(function () {
    "use strict";

    function normalizePath(path) {
        if (path === undefined || path === null) {
            return "";
        }
        let value = String(path).trim();
        if (!value) {
            return "/";
        }
        if (value.startsWith("http://") || value.startsWith("https://")) {
            return value;
        }
        if (value.startsWith("#")) {
            value = value.slice(1);
        }
        if (!value.startsWith("/")) {
            value = "/" + value;
        }
        value = value.replace(/\/{2,}/g, "/");
        if (value.length > 1 && value.endsWith("/")) {
            value = value.slice(0, -1);
        }
        return value || "/";
    }

    function joinPath(base, path) {
        const right = String(path || "").trim();
        if (!right) {
            return normalizePath(base || "/");
        }
        if (right.startsWith("/")) {
            return normalizePath(right);
        }
        const left = normalizePath(base || "/");
        if (left === "/") {
            return normalizePath("/" + right);
        }
        return normalizePath(left + "/" + right);
    }

    function isRouterLike(router) {
        if (!router || typeof router !== "object") {
            return false;
        }
        return (
            typeof router.getRoutes === "function" ||
            !!(router.matcher && typeof router.matcher.getRoutes === "function") ||
            !!(router.options && Array.isArray(router.options.routes)) ||
            typeof router.push === "function"
        );
    }

    function findRouterFromProvides(provides) {
        if (!provides || typeof provides !== "object") {
            return null;
        }
        const keys = Object.keys(provides).concat(Object.getOwnPropertySymbols(provides));
        for (let i = 0; i < keys.length; i += 1) {
            const value = provides[keys[i]];
            if (isRouterLike(value)) {
                return value;
            }
        }
        return null;
    }

    function findVueRootNode() {
        const app = document.querySelector("#app");
        if (app && (app.__vue_app__ || app.__vue__ || app._vnode)) {
            return app;
        }
        const nodes = document.querySelectorAll("*");
        for (let i = 0; i < nodes.length; i += 1) {
            const node = nodes[i];
            if (node.__vue_app__ || node.__vue__ || node._vnode) {
                return node;
            }
        }
        return null;
    }

    function findVueRouter() {
        const vueRoot = findVueRootNode();
        if (!vueRoot) {
            return null;
        }

        try {
            if (vueRoot.__vue_app__) {
                const app = vueRoot.__vue_app__;
                const routerFromGlobal = app && app.config && app.config.globalProperties
                    ? app.config.globalProperties.$router
                    : null;
                if (isRouterLike(routerFromGlobal)) {
                    return routerFromGlobal;
                }

                const routerFromInstance = app && app._instance && app._instance.appContext && app._instance.appContext.config
                    ? app._instance.appContext.config.globalProperties.$router
                    : null;
                if (isRouterLike(routerFromInstance)) {
                    return routerFromInstance;
                }

                const routerFromProvides = app && app._context ? findRouterFromProvides(app._context.provides) : null;
                if (isRouterLike(routerFromProvides)) {
                    return routerFromProvides;
                }
            }

            if (vueRoot.__vue__) {
                const vue = vueRoot.__vue__;
                const candidates = [
                    vue.$router,
                    vue.$root ? vue.$root.$router : null,
                    vue.$root && vue.$root.$options ? vue.$root.$options.router : null,
                    vue._router
                ];
                for (let i = 0; i < candidates.length; i += 1) {
                    if (isRouterLike(candidates[i])) {
                        return candidates[i];
                    }
                }
            }
        } catch (e) {
            return null;
        }

        return null;
    }

    function collectRouteCount(router) {
        if (!isRouterLike(router)) {
            return 0;
        }

        const seen = new Set();
        function addPath(path) {
            const value = normalizePath(path);
            if (!value) {
                return;
            }
            seen.add(value);
        }

        function walkRouteTree(routes, basePath) {
            if (!Array.isArray(routes)) {
                return;
            }
            for (let i = 0; i < routes.length; i += 1) {
                const route = routes[i];
                if (!route || typeof route !== "object") {
                    continue;
                }
                const fullPath = joinPath(basePath, route.path || "");
                addPath(fullPath);
                if (Array.isArray(route.children) && route.children.length > 0) {
                    walkRouteTree(route.children, fullPath);
                }
            }
        }

        try {
            if (typeof router.getRoutes === "function") {
                const routes = router.getRoutes();
                if (Array.isArray(routes)) {
                    for (let i = 0; i < routes.length; i += 1) {
                        const route = routes[i];
                        if (!route || typeof route !== "object") {
                            continue;
                        }
                        addPath(route.path || "");
                    }
                }
            }
        } catch (e) {
            // ignore
        }

        try {
            if (router.matcher && typeof router.matcher.getRoutes === "function") {
                const routes = router.matcher.getRoutes();
                if (Array.isArray(routes)) {
                    for (let i = 0; i < routes.length; i += 1) {
                        const route = routes[i];
                        if (!route || typeof route !== "object") {
                            continue;
                        }
                        addPath(route.path || "");
                    }
                }
            }
        } catch (e) {
            // ignore
        }

        try {
            if (router.options && Array.isArray(router.options.routes)) {
                walkRouteTree(router.options.routes, "");
            }
        } catch (e) {
            // ignore
        }

        return seen.size;
    }

    function hasScopedAttrHint() {
        const nodes = document.querySelectorAll("*");
        const maxScan = Math.min(nodes.length, 1200);
        for (let i = 0; i < maxScan; i += 1) {
            const node = nodes[i];
            if (!node || !node.attributes) {
                continue;
            }
            for (let j = 0; j < node.attributes.length; j += 1) {
                const attrName = node.attributes[j].name || "";
                if (attrName.startsWith("data-v-")) {
                    return true;
                }
            }
        }
        return false;
    }

    function hasVueRuntimeMarker() {
        if (window.__VUE__ || window.Vue || window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
            return true;
        }

        const app = document.querySelector("#app");
        if (app && (app.__vue_app__ || app.__vue__ || app._vnode)) {
            return true;
        }

        const nodes = document.querySelectorAll("*");
        for (let i = 0; i < nodes.length; i += 1) {
            const node = nodes[i];
            if (node.__vue_app__ || node.__vue__ || node._vnode) {
                return true;
            }
        }
        return false;
    }

    function hasVueDomHint() {
        if (hasScopedAttrHint()) {
            return true;
        }

        const html = document.documentElement ? document.documentElement.outerHTML : "";
        return /\bcreateApp\s*\(|\bnew\s+Vue\s*\(|__VUE_DEVTOOLS_GLOBAL_HOOK__|\bvue-router\b|__vue_app__/i.test(
            html
        );
    }

    function detectMethod() {
        if (hasVueRuntimeMarker()) {
            return "runtime";
        }
        if (hasVueDomHint()) {
            return "dom_hint";
        }
        return "none";
    }

    function detectVueRuntime() {
        const method = detectMethod();
        let routeCount = 0;
        if (method !== "none") {
            routeCount = collectRouteCount(findVueRouter());
            if (!Number.isFinite(routeCount) || routeCount < 0) {
                routeCount = 0;
            }
        }
        return {
            vueDetected: method !== "none",
            method: method,
            href: location.href,
            title: document.title || "",
            routeCount: routeCount
        };
    }

    window.__VD_DETECT__ = detectVueRuntime;
})();
