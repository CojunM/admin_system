(function (window) {
    'use strict';

    // ====================== 1. Solid.js 响应式核心模块 ======================
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
            // ========== 核心修复：修正set方法语法错误，支持函数式更新 ==========
            const set = (newVal) => {
                // 1. 处理函数式更新：传入旧值，计算新值
                const nextValue = typeof newVal === 'function' ? newVal(value) : newVal;
                // 2. 新旧值一致，跳过更新（Object.is 处理 NaN/+-0 特殊场景）
                if (Object.is(value, nextValue)) return;
                // 3. 更新值
                value = nextValue;
                // 4. 触发订阅，异常隔离
                subscribers.forEach(eff => {
                    try { eff(); } catch (e) { console.error('[Signal Update Error]', e); }
                });
            };
            return [get, set];
        };

        const createEffect = (fn) => {
            const effect = () => {
                pushEffect(effect);
                try { fn(); }
                catch (e) { console.error('[Effect Execution Error]', e); }
                finally { popEffect(); }
            };
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
                if (/^\w+$/.test(expr)) { ctx[expr]?.($event); return; }
                const funcMatch = expr.match(/^(\w+)\((.*)\)$/);
                if (funcMatch) {
                    const [, funcName, argStr] = funcMatch;
                    const args = argStr.split(',')
                        .map(i => i.trim().replace(/^['"](.*)['"]$/, '$1'))
                        .filter(Boolean);
                    args.push($event);
                    ctx[funcName]?.(...args);
                }
            } catch (err) { console.warn('[Event Execution Failed]', err); }
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
        const INTERPOLATION_REG = /{{\s*([\w\(\).]+?)\s*}}/g;

        const renderInterpolation = (node, ctx, watchers) => {
            if (node.nodeType !== Node.TEXT_NODE) return;
            const originText = node.textContent;
            if (!originText.includes('{{')) return;
            watchers.push(() => {
                node.textContent = originText.replace(INTERPOLATION_REG, (_, exp) => {
                    try {
                        const keys = Object.keys(ctx);
                        const values = Object.values(ctx);
                        const res = new Function(...keys, `return ${exp}`)(...values);
                        return getRealValue(res);
                    } catch { return ''; }
                });
            });
        };

        const compileNode = (el, ctx, watchers) => {
            if (!el) return;
            if (el.nodeType === Node.TEXT_NODE) { renderInterpolation(el, ctx, watchers); return; }
            if (el.nodeType !== Node.ELEMENT_NODE) return;

            const attrs = Array.from(el.attributes);

            // 事件绑定
            attrs.forEach(attr => {
                if (!attr.name.startsWith('@')) return;
                const event = attr.name.slice(1);
                el.addEventListener(event, (e) => execEvent(ctx, attr.value.trim(), e));
                el.removeAttribute(attr.name);
            });

            // v-html 指令
            attrs.forEach(attr => {
                if (attr.name !== 'v-html') return;
                const key = attr.value;
                watchers.push(() => { el.innerHTML = getRealValue(ctx[key]); });
                el.removeAttribute(attr.name);
            });

            // 动态绑定 :class/:style
            attrs.forEach(attr => {
                if (!attr.name.startsWith(':')) return;
                const prop = attr.name.slice(1);
                const key = attr.value;
                watchers.push(() => {
                    const val = getRealValue(ctx[key]) ?? '';
                    if (prop === 'class') el.className = val;
                    if (prop === 'style') el.style.cssText = val;
                });
                el.removeAttribute(attr.name);
            });

            // v-for 渲染逻辑（已正常，无需修改）
            const vForAttr = attrs.find(attr => attr.name === 'v-for');
            if (vForAttr) {
                const parent = el.parentNode;
                const vForConf = parseVFor(vForAttr.value);
                if (!vForConf || !parent) return;

                const tpl = cloneNode(el);
                tpl?.removeAttribute('v-for');
                el.remove();

                const renderList = () => {
                    try {
                        parent.querySelectorAll('[data-msv-item]').forEach(n => n.remove());
                        const signalGetter = ctx[vForConf.listKey];
                        const listData = Array.isArray(signalGetter()) ? signalGetter() : [];
                        console.debug('[v-for] 渲染列表数据:', listData);

                        listData.forEach((item, index) => {
                            const node = cloneNode(tpl);
                            if (!node) return;
                            node.setAttribute('data-msv-item', '');
                            const childCtx = { ...ctx, [vForConf.itemKey]: item, [vForConf.indexKey]: index };
                            const childWatchers = [];
                            compileNode(node, childCtx, childWatchers);
                            childWatchers.forEach(w => w());
                            parent.appendChild(node);
                        });
                    } catch (e) { console.error('[v-for Render Error]', e); }
                };

                watchers.push(renderList);
                renderList();
                return;
            }

            Array.from(el.childNodes).forEach(node => compileNode(node, ctx, watchers));
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
            if (!container) throw new Error('Container DOM not found');
            const option = componentMap.get(name.toLowerCase());
            if (!option) throw new Error(`Component [${name}] is not registered`);

            container.innerHTML = '';
            const setupCtx = option.setup({ ...props }) || {};
            const renderCtx = { ...props, ...setupCtx };
            const { root, watchers } = compile(option.template, renderCtx);
            container.appendChild(root);

            createEffect(() => { watchers.forEach(w => { try { w(); } catch { } }); });
        };

        const createApp = (componentOptions) => {
            const tempName = `app_${Date.now()}`;
            defineComponent(tempName, componentOptions);
            return {
                mount(selector) {
                    const container = document.querySelector(selector);
                    renderComponent(tempName, {}, container);
                }
            };
        };

        return { defineComponent, renderComponent, createApp };
    })();

    // 全局导出
    const Framework = { ...ReactiveModule, ...ComponentModule, utils: UtilsModule };
    if (typeof window !== 'undefined') window.MiniSolidVue = Framework;
    if (typeof module !== 'undefined' && module.exports) module.exports = Framework;
})(window);