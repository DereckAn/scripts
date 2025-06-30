import { renderers } from './renderers.mjs';
import { c as createExports } from './chunks/entrypoint_Dnb6OE1e.mjs';
import { manifest } from './manifest_BcL7TszL.mjs';

const serverIslandMap = new Map();;

const _page0 = () => import('./pages/_image.astro.mjs');
const _page1 = () => import('./pages/api/generate.astro.mjs');
const _page2 = () => import('./pages/api/generate-script.astro.mjs');
const _page3 = () => import('./pages/api/script/_id_.astro.mjs');
const _page4 = () => import('./pages/api/scripts/_id_.astro.mjs');
const _page5 = () => import('./pages/api-examples.astro.mjs');
const _page6 = () => import('./pages/index.astro.mjs');
const pageMap = new Map([
    ["node_modules/astro/dist/assets/endpoint/generic.js", _page0],
    ["src/pages/api/generate.ts", _page1],
    ["src/pages/api/generate-script.ts", _page2],
    ["src/pages/api/script/[id].ts", _page3],
    ["src/pages/api/scripts/[id].ts", _page4],
    ["src/pages/api-examples.astro", _page5],
    ["src/pages/index.astro", _page6]
]);

const _manifest = Object.assign(manifest, {
    pageMap,
    serverIslandMap,
    renderers,
    actions: () => import('./_noop-actions.mjs'),
    middleware: () => import('./_noop-middleware.mjs')
});
const _args = {
    "middlewareSecret": "2340f499-8eee-4d5f-8d35-2fc24524ca1a",
    "skewProtection": false
};
const _exports = createExports(_manifest, _args);
const __astrojsSsrVirtualEntry = _exports.default;

export { __astrojsSsrVirtualEntry as default, pageMap };
