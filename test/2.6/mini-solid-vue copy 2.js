(function (window) {
    'use strict';

    // ====================== 1. 响应式核心模块 ======================
    const ReactiveModule = (() => {
        let activeEffect = null;
        const effectStack = [];

        const pushEffect = (eff) => {
            effectStack.push(eff);
            activeEffect = eff;
        };
        const popEffect = () => {
            effectStack.pop();
            activeEffect = effectStack.at(-1) || null;
        };

        const createSignal = (initialValue) => {
            let value = initialValue;
            const subscribers = new Set();
            const get = () => {
                if (activeEffect) subscribers.add(activeEffect);
                return value;
            };
            const set = (newVal) => {
                const nextValue = typeof newVal === 'function' ? newVal(value) : newVal;
                if (Object.is(value, nextValue)) return;
                value = nextValue;
                subscribers.forEach(eff => eff());
            };
            return [get, set];
        };

        const createEffect = (fn) => {
            const effect = () => {
                pushEffect(effect);
                try { fn(); } catch (e) { console.error('[Effect Error]', e); } finally { popEffect(); }
            };
            effect._name = `effect_${Date.now()}`;
            effect();
            return effect;
        };

        const createMemo = (fn) => {
            const [get, set] = createSignal();
            createEffect(() => set(fn()));
            return get;
        };

        return { createSignal, createEffect, createMemo };
    })();

    // ====================== 2. 工具模块 ======================
    const UtilsModule = (() => {
        const getRealValue = (value) => {
            const realVal = typeof value === 'function' ? value() : value;
            if ([null, undefined, true, false].includes(realVal)) return '';
            if (typeof realVal === 'number' && (Number.isNaN(realVal) || !Number.isFinite(realVal))) return '';
            return realVal;
        };

        const execEvent = (ctx, expr, $event) => {
            try {
                if (!expr) return;
                const keys = [...Object.keys(ctx), '$event'];
                const values = [...Object.values(ctx), $event];
                const result = new Function(...keys, `return ${expr}`)(...values);
                if (typeof result === 'function') result(); // 自动执行函数
            } catch (err) {
                console.warn('[Event Error]', err, 'Expr:', expr);
            }
        };

        const toast = (msg) => {
            document.querySelectorAll('.mini-toast').forEach(el => el.remove());
            const tip = document.createElement('div');
            tip.className = 'mini-toast';
            tip.textContent = msg;
            tip.style.cssText = `position:fixed;top:20px;right:20px;background:#165DFF;color:#fff;padding:12px 20px;border-radius:6px;z-index:9999;transition:opacity 0.3s;`;
            document.body.appendChild(tip);
            setTimeout(() => { tip.style.opacity = '0'; setTimeout(() => tip.remove(), 300); }, 1500);
        };

        const cloneNode = (el) => el?.cloneNode(true) || null;
        const parseVFor = (str) => {
            const reg = /^\s*([$\w]+)(?:\s*,\s*([$\w]+))?\s+in\s+([$\w]+)\s*$/;
            const match = str.match(reg);
            if (!match) return null;
            return { itemKey: match[1], indexKey: match[2] || '$index', listKey: match[3] };
        };

        return { getRealValue, execEvent, toast, cloneNode, parseVFor };
    })();

    // ====================== 3. 模板编译器 ======================
    const CompilerModule = (() => {
        const { getRealValue, execEvent, cloneNode, parseVFor } = UtilsModule;
        const INTERPOLATION_REG = /{{([\s\S]+?)}}/g;

        const renderInterpolation = (node, ctx, watchers) => {
            if (node.nodeType !== Node.TEXT_NODE) return;
            const originText = node.textContent;
            if (!originText.includes('{{')) return;

            const updateText = () => {
                node.textContent = originText.replace(INTERPOLATION_REG, (_, exp) => {
                    try {
                        const expression = exp.trim();
                        const keys = Object.keys(ctx);
                        const values = Object.values(ctx);
                        const res = new Function(...keys, `return ${expression}`)(...values);
                        return getRealValue(res);
                    } catch (err) {
                        console.warn('[Interpolation Error]', err, 'Expr:', exp);
                        return '';
                    }
                });
            };
            updateText();
            watchers.push(updateText);
        };

        const compileNode = (el, ctx, watchers) => {
            if (!el) return;
            if (el.nodeType === Node.TEXT_NODE) {
                renderInterpolation(el, ctx, watchers);
                return;
            }
            if (el.nodeType !== Node.ELEMENT_NODE) return;

            // 事件绑定
            const eventAttrs = [];
            Array.from(el.attributes).forEach(attr => {
                if (attr.name.startsWith('@')) {
                    eventAttrs.push({ name: attr.name, value: attr.value });
                    el.removeAttribute(attr.name);
                }
            });
            eventAttrs.forEach(attr => {
                const eventType = attr.name.slice(1);
                el.addEventListener(eventType, (e) => execEvent(ctx, attr.value.trim(), e));
            });

            // v-html
            const vHtmlAttr = el.getAttribute('v-html');
            if (vHtmlAttr) {
                const updateHtml = () => { el.innerHTML = getRealValue(ctx[vHtmlAttr]); };
                updateHtml();
                watchers.push(updateHtml);
                el.removeAttribute('v-html');
            }

            // :class/:style
            const bindAttrs = [];
            Array.from(el.attributes).forEach(attr => {
                if (attr.name.startsWith(':')) {
                    bindAttrs.push({ name: attr.name, value: attr.value });
                    el.removeAttribute(attr.name);
                }
            });
            bindAttrs.forEach(attr => {
                const prop = attr.name.slice(1);
                const key = attr.value;
                const updateBind = () => {
                    const val = getRealValue(ctx[key]) ?? '';
                    if (prop === 'class') el.className = val;
                    if (prop === 'style') el.style.cssText = val;
                };
                updateBind();
                watchers.push(updateBind);
            });

            // v-for
            const vForAttr = el.getAttribute('v-for');
            if (vForAttr) {
                const parent = el.parentNode;
                const vForConf = parseVFor(vForAttr);
                if (vForConf && parent) {
                    const tpl = cloneNode(el);
                    tpl?.removeAttribute('v-for');
                    el.remove();

                    const renderList = () => {
                        try {
                            parent.querySelectorAll('[data-msv-item]').forEach(n => n.remove());
                            const listData = Array.isArray(ctx[vForConf.listKey]()) ? ctx[vForConf.listKey]() : [];
                            listData.forEach((item, index) => {
                                const node = cloneNode(tpl);
                                if (node) {
                                    node.setAttribute('data-msv-item', '');
                                    const childCtx = { ...ctx, [vForConf.itemKey]: item, [vForConf.indexKey]: index };
                                    const childWatchers = [];
                                    compileNode(node, childCtx, childWatchers);
                                    parent.appendChild(node);
                                }
                            });
                        } catch (e) { console.error('[VFor Error]', e); }
                    };
                    renderList();
                    watchers.push(renderList);
                    return;
                }
            }

            Array.from(el.childNodes).forEach(child => compileNode(child, ctx, watchers));
        };

        const compile = (template, ctx) => {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = template.trim();
            const root = wrapper.firstElementChild;
            const watchers = [];
            if (root) compileNode(root, ctx, watchers);
            console.debug('[MiniSolidVue] Compile Success, Watchers Count:', watchers.length);
            return { root, watchers };
        };

        return { compile };
    })();

    // ====================== 4. 组件系统 ======================
    const ComponentModule = (() => {
        const { createEffect } = ReactiveModule;
        const { compile } = CompilerModule;
        const componentMap = new Map();

        const defineComponent = (name, options) => {
            componentMap.set(name.toLowerCase(), options);
        };

        const renderComponent = (name, props = {}, container) => {
            if (!container) throw new Error('Container not found');
            const option = componentMap.get(name.toLowerCase());
            if (!option) throw new Error(`Component ${name} not registered`);

            container.innerHTML = '';
            const setupCtx = option.setup({ ...props }) || {};
            const renderCtx = { ...props, ...setupCtx };
            const { root, watchers } = compile(option.template, renderCtx);
            container.appendChild(root);

            createEffect(() => {
                watchers.forEach(w => { try { w(); } catch (e) { console.error('Watcher Error:', e); } });
            });
        };

        const createApp = (componentOptions) => {
            const tempName = `app_${Date.now()}`;
            defineComponent(tempName, componentOptions);
            return {
                mount(selector) {
                    const container = document.querySelector(selector);
                    if (!container) {
                        console.error('Mount container not found:', selector);
                        return;
                    }
                    renderComponent(tempName, {}, container);
                }
            };
        };

        return { defineComponent, renderComponent, createApp };
    })();

    // 全局挂载
    const Framework = {
        ...ReactiveModule,
        ...ComponentModule,
        utils: UtilsModule
    };
    if (typeof window !== 'undefined') window.MiniSolidVue = Framework;
    if (typeof module !== 'undefined' && module.exports) module.exports = Framework;
})(window);