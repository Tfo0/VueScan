(function () {
    'use strict';

    const LOG_PREFIX = '[VueChunk]';

    function log(...args) {
        console.log(LOG_PREFIX, ...args);
    }

    function warn(...args) {
        console.warn(LOG_PREFIX, ...args);
    }

    function sendData(payload) {
        try {
            if (typeof window.sendData === 'function') {
                window.sendData(payload);
            }
        } catch (e) {
            warn('sendData failed:', e);
        }
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function normalizePath(path) {
        if (path === undefined || path === null) {
            return '';
        }

        let value = String(path).trim();
        if (!value) {
            return '/';
        }

        if (value.startsWith('http://') || value.startsWith('https://')) {
            return value;
        }

        if (value.startsWith('#')) {
            value = value.slice(1);
        }

        if (!value.startsWith('/')) {
            value = '/' + value;
        }

        value = value.replace(/\/{2,}/g, '/');
        if (value.length > 1 && value.endsWith('/')) {
            value = value.slice(0, -1);
        }

        return value || '/';
    }

    function joinPath(base, path) {
        if (!path) {
            return normalizePath(base || '/');
        }

        if (String(path).startsWith('/')) {
            return normalizePath(path);
        }

        const left = normalizePath(base || '/');
        const right = String(path).replace(/^\/+/, '');
        if (left === '/') {
            return normalizePath('/' + right);
        }
        return normalizePath(left + '/' + right);
    }

    function findVueRootOnce() {
        const appEl = document.querySelector('#app');
        if (appEl && (appEl.__vue_app__ || appEl.__vue__ || appEl._vnode)) {
            return appEl;
        }

        const allNodes = document.querySelectorAll('*');
        for (let i = 0; i < allNodes.length; i++) {
            const node = allNodes[i];
            if (node.__vue_app__ || node.__vue__ || node._vnode) {
                return node;
            }
        }

        return null;
    }

    async function waitForVueRoot(timeoutMs = 12000, intervalMs = 250) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            const root = findVueRootOnce();
            if (root) {
                return root;
            }
            await sleep(intervalMs);
        }
        return null;
    }

    function getVueVersion(vueRoot) {
        try {
            const fromRoot = vueRoot?.__vue_app__?.version
                || vueRoot?.__vue__?.$root?.$options?._base?.version;
            if (fromRoot) {
                return fromRoot;
            }

            if (window.Vue && window.Vue.version) {
                return window.Vue.version;
            }

            const hookVue = window.__VUE_DEVTOOLS_GLOBAL_HOOK__?.Vue;
            if (hookVue && hookVue.version) {
                return hookVue.version;
            }
        } catch (e) {
            warn('getVueVersion failed:', e);
        }
        return 'unknown';
    }

    function isRouterLike(router) {
        if (!router || typeof router !== 'object') {
            return false;
        }
        return typeof router.getRoutes === 'function'
            || !!router.options?.routes
            || !!router.matcher
            || typeof router.push === 'function';
    }

    function findRouterFromProvides(provides) {
        if (!provides || typeof provides !== 'object') {
            return null;
        }

        const symbolKeys = Object.getOwnPropertySymbols(provides);
        const stringKeys = Object.keys(provides);
        const keys = stringKeys.concat(symbolKeys);

        for (const key of keys) {
            const value = provides[key];
            if (isRouterLike(value)) {
                return value;
            }
        }
        return null;
    }

    function findVueRouter(vueRoot) {
        try {
            if (vueRoot?.__vue_app__) {
                const app = vueRoot.__vue_app__;

                const globalRouter = app?.config?.globalProperties?.$router;
                if (isRouterLike(globalRouter)) {
                    return globalRouter;
                }

                const instanceRouter = app?._instance?.appContext?.config?.globalProperties?.$router;
                if (isRouterLike(instanceRouter)) {
                    return instanceRouter;
                }

                const providesRouter = findRouterFromProvides(app?._context?.provides);
                if (isRouterLike(providesRouter)) {
                    return providesRouter;
                }
            }

            if (vueRoot?.__vue__) {
                const vue = vueRoot.__vue__;
                const candidates = [
                    vue.$router,
                    vue.$root?.$router,
                    vue.$root?.$options?.router,
                    vue._router
                ];
                for (const item of candidates) {
                    if (isRouterLike(item)) {
                        return item;
                    }
                }
            }
        } catch (e) {
            warn('findVueRouter failed:', e);
        }
        return null;
    }

    function clearGuardContainer(container) {
        if (!container) {
            return false;
        }

        if (Array.isArray(container)) {
            if (container.length > 0) {
                container.length = 0;
                return true;
            }
            return false;
        }

        if (Array.isArray(container.list)) {
            if (container.list.length > 0) {
                container.list.length = 0;
                return true;
            }
            return false;
        }

        if (typeof container.clear === 'function') {
            try {
                container.clear();
                return true;
            } catch (e) {
                return false;
            }
        }

        return false;
    }

    function patchRouterGuards(router) {
        let changed = false;

        try {
            const registerHooks = ['beforeEach', 'beforeResolve', 'afterEach'];
            for (const hook of registerHooks) {
                if (typeof router[hook] === 'function') {
                    router[hook] = function () {
                        return function () {};
                    };
                    changed = true;
                }
            }

            const guardContainers = [
                'beforeGuards', 'beforeResolveGuards', 'afterGuards',
                'beforeHooks', 'resolveHooks', 'afterHooks'
            ];
            for (const key of guardContainers) {
                if (clearGuardContainer(router[key])) {
                    changed = true;
                }
            }
        } catch (e) {
            warn('patchRouterGuards failed:', e);
        }

        if (changed) {
            log('router guards patched');
        }
        return changed;
    }

    function isAuthTrue(value) {
        return value === true || value === 'true' || value === 1 || value === '1';
    }

    function sanitizeMeta(meta) {
        if (!meta || typeof meta !== 'object') {
            return {};
        }

        const out = {};
        for (const key of Object.keys(meta)) {
            const val = meta[key];
            if (val === null || val === undefined) {
                out[key] = val;
            } else if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') {
                out[key] = val;
            } else if (Array.isArray(val)) {
                out[key] = val.map(item => {
                    if (item === null || item === undefined) return item;
                    const t = typeof item;
                    if (t === 'string' || t === 'number' || t === 'boolean') return item;
                    return '[Object]';
                });
            } else {
                out[key] = '[Object]';
            }
        }
        return out;
    }

    function walkRouteTree(routes, basePath, routeCallback) {
        if (!Array.isArray(routes)) {
            return;
        }

        routes.forEach(route => {
            if (!route || typeof route !== 'object') {
                return;
            }

            const fullPath = joinPath(basePath, route.path || '');
            routeCallback(route, fullPath);

            if (Array.isArray(route.children) && route.children.length > 0) {
                walkRouteTree(route.children, fullPath, routeCallback);
            }
        });
    }

    function collectRouteRecords(router) {
        const records = [];
        const seen = new Set();

        function addRecord(route, fullPath) {
            if (!route || typeof route !== 'object') {
                return;
            }

            const key = `${fullPath || normalizePath(route.path || '')}::${route.name || ''}`;
            if (seen.has(key)) {
                return;
            }
            seen.add(key);
            records.push({ route, fullPath: fullPath || normalizePath(route.path || '') });
        }

        try {
            if (typeof router.getRoutes === 'function') {
                router.getRoutes().forEach(route => addRecord(route, normalizePath(route.path || '')));
            }
        } catch (e) {
            warn('collectRouteRecords getRoutes failed:', e);
        }

        try {
            if (router.matcher && typeof router.matcher.getRoutes === 'function') {
                router.matcher.getRoutes().forEach(route => addRecord(route, normalizePath(route.path || '')));
            }
        } catch (e) {
            warn('collectRouteRecords matcher.getRoutes failed:', e);
        }

        try {
            if (router.options?.routes) {
                walkRouteTree(router.options.routes, '', addRecord);
            }
        } catch (e) {
            warn('collectRouteRecords options.routes failed:', e);
        }

        return records;
    }

    function patchAllRouteAuth(routeRecords) {
        const modified = [];

        routeRecords.forEach(({ route, fullPath }) => {
            if (!route || typeof route !== 'object' || !route.meta || typeof route.meta !== 'object') {
                return;
            }

            let changed = false;
            Object.keys(route.meta).forEach(key => {
                if (key.toLowerCase().includes('auth') && isAuthTrue(route.meta[key])) {
                    route.meta[key] = false;
                    changed = true;
                }
            });

            if (changed) {
                modified.push({
                    name: route.name || '',
                    path: fullPath || normalizePath(route.path || '')
                });
            }
        });

        return modified;
    }

    function toSerializableRoutes(routeRecords) {
        const seenPath = new Set();
        const result = [];

        routeRecords.forEach(({ route, fullPath }) => {
            const path = fullPath || normalizePath(route?.path || '');
            if (!path || seenPath.has(path)) {
                return;
            }

            seenPath.add(path);
            result.push({
                name: route?.name || '',
                path: path,
                meta: sanitizeMeta(route?.meta)
            });
        });

        result.sort((a, b) => {
            if (a.path === b.path) {
                return String(a.name).localeCompare(String(b.name));
            }
            return String(a.path).localeCompare(String(b.path));
        });

        return result;
    }

    function extractRouterBase(router) {
        try {
            if (router?.options?.base) {
                return router.options.base;
            }
            if (router?.history?.base) {
                return router.history.base;
            }
        } catch (e) {
            warn('extractRouterBase failed:', e);
        }
        return '';
    }

    function buildDetectionResult(vueRoot) {
        const detected = !!vueRoot || !!window.Vue || !!window.__VUE_DEVTOOLS_GLOBAL_HOOK__?.Vue;
        let method = 'none';
        if (vueRoot?.__vue_app__) {
            method = 'vue3_root';
        } else if (vueRoot?.__vue__) {
            method = 'vue2_root';
        } else if (window.Vue) {
            method = 'window_vue';
        } else if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__?.Vue) {
            method = 'devtools_hook';
        }

        return {
            detected,
            method,
            details: {
                vueVersion: getVueVersion(vueRoot),
                rootTag: vueRoot?.tagName || ''
            },
            errorMsg: ''
        };
    }

    function analyzeVueRouter(vueRoot) {
        const router = findVueRouter(vueRoot);
        const result = {
            vueDetected: !!vueRoot || !!window.Vue || !!window.__VUE_DEVTOOLS_GLOBAL_HOOK__?.Vue,
            routerDetected: false,
            vueVersion: getVueVersion(vueRoot),
            routerBase: '',
            modifiedRoutes: [],
            allRoutes: []
        };

        if (!router) {
            return result;
        }

        result.routerDetected = true;
        result.routerBase = extractRouterBase(router);

        patchRouterGuards(router);
        const routeRecords = collectRouteRecords(router);
        result.modifiedRoutes = patchAllRouteAuth(routeRecords);
        result.allRoutes = toSerializableRoutes(routeRecords);

        return result;
    }

    async function bootstrap() {
        const vueRoot = await waitForVueRoot();
        if (!vueRoot) {
            warn('Vue root not found within timeout');
        } else {
            log('Vue root detected');
        }

        const detection = buildDetectionResult(vueRoot);
        sendData({
            type: 'VUE_DETECTION_RESULT',
            result: detection
        });

        const analysis = analyzeVueRouter(vueRoot);
        sendData({
            type: 'VUE_ROUTER_ANALYSIS_RESULT',
            result: analysis
        });
    }

    bootstrap().catch(err => {
        warn('bootstrap failed:', err);
        sendData({
            type: 'VUE_ROUTER_ANALYSIS_ERROR',
            error: String(err)
        });
    });
})();
