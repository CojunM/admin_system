/**
 * MiniSolidVue 全边界值最终版
 * 规则：null/undefined/true/false/NaN/Infinity → 空字符串；0/有效字符串 → 原样保留
 */
(function (window) {
    'use strict';
    // ====================== 1. 响应式核心 ======================
    const Reactive = (() => {
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
                if (Object.is(value, newVal)) return;
                value = newVal;
                subscribers.forEach(eff => eff());
            };
            return [get, set];
        };

        const createEffect = (fn) => {
            const effect = () => {
                pushEffect(effect);
                try { fn(); }
                catch (e) { console.error('[Effect Error]', e); }
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

    // ====================== 2. 通用工具：统一取值与全边界值处理 ======================
    function getRealValue(value) {
        // 解析响应式函数
        const realVal = typeof value === 'function' ? value() : value;

        // 处理空值、布尔值
        if ([null, undefined, true, false].includes(realVal)) {
            return '';
        }

        // 处理数值特殊值：NaN 和 Infinity
        if (typeof realVal === 'number') {
            if (Number.isNaN(realVal) || !Number.isFinite(realVal)) {
                return '';
            }
        }

        // 合法值原样返回
        return realVal;
    }

    // ====================== 3. 事件执行工具 ======================
    function execEvent(ctx, expr, $event) {
        try {
            if (/^\w+$/.test(expr)) return ctx[expr]?.($event);
            const funcMatch = expr.match(/^(\w+)\((.*)\)$/);
            if (funcMatch) {
                const [, funcName, argStr] = funcMatch;
                const args = argStr.split(',').map(i => i.trim().replace(/^['"](.*)['"]$/, '$1')).filter(Boolean);
                args.push($event);
                return ctx[funcName]?.(...args);
            }
        } catch (err) {
            console.warn('[事件执行失败]', err);
        }
    }

    // ====================== 4. 模板编译器 ======================
    const Compiler = (() => {
        const INTERPOLATION_REG = /\{\{\s*(\w+)\(\)\s*\}\}/;

        // 文本插值渲染
        function renderInterpolation(node, ctx, watchers) {
            const originText = node.textContent;
            const matchResult = originText.match(INTERPOLATION_REG);
            if (!matchResult) return;

            const [fullMatch, funcName] = matchResult;
            const textPrefix = originText.split(fullMatch)[0];
            const textNode = node;

            watchers.push(() => {
                const value = getRealValue(ctx[funcName]);
                textNode.textContent = `${textPrefix}${value}`;
            });
        }

        function compileNode(el, ctx, watchers) {
            if (!el) return;
            // 处理文本节点
            if (el.nodeType === 3) {
                renderInterpolation(el, ctx, watchers);
                return;
            }
            if (el.nodeType !== 1) return;

            const attrs = Array.from(el.attributes);

            // 1. 事件绑定 @xxx
            attrs.forEach(attr => {
                if (!attr.name.startsWith('@')) return;
                const event = attr.name.slice(1);
                el.addEventListener(event, (e) => execEvent(ctx, attr.value.trim(), e));
                el.removeAttribute(attr.name);
            });

            // 2. v-html 指令渲染原生HTML
            attrs.forEach(attr => {
                if (attr.name !== 'v-html') return;
                const key = attr.value;
                watchers.push(() => {
                    const htmlStr = getRealValue(ctx[key]);
                    el.innerHTML = htmlStr;
                });
                el.removeAttribute(attr.name);
            });

            // 3. 动态属性 :class / :style
            attrs.forEach(attr => {
                if (!attr.name.startsWith(':')) return;
                const prop = attr.name.slice(1);
                const key = attr.value;

                watchers.push(() => {
                    const val = getRealValue(ctx[key]) ?? '';
                    if (prop === 'class') {
                        console.debug('[动态Class更新] 目标类名:', val);
                        el.className = val;
                    }
                    if (prop === 'style') {
                        console.debug('[动态Style更新] 目标样式:', val);
                        el.style.cssText = val;
                    }
                });
                el.removeAttribute(attr.name);
            });

            // 递归编译子节点
            Array.from(el.childNodes).forEach(node => compileNode(node, ctx, watchers));
        }

        function compile(template, ctx) {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = template.trim();
            const root = wrapper.firstElementChild;
            const watchers = [];
            root && compileNode(root, ctx, watchers);
            console.debug('[编译完成] 有效Watcher数量:', watchers.length);
            return { root, watchers };
        }

        return { compile };
    })();

    // ====================== 5. 组件系统 ======================
    const Component = (() => {
        const { createEffect } = Reactive;
        const { compile } = Compiler;
        const componentMap = new Map();

        const defineComponent = (name, options) => {
            componentMap.set(name.toLowerCase(), options);
        };

        const renderComponent = (name, props = {}, container) => {
            if (!container) throw new Error('DOM容器不存在');
            const option = componentMap.get(name.toLowerCase());
            if (!option) throw new Error(`组件 ${name} 未注册`);

            container.innerHTML = '';
            const setupCtx = option.setup({ ...props }) || {};
            const renderCtx = { ...props, ...setupCtx, toast: Utils.toast };
            const { root, watchers } = compile(option.template, renderCtx);
            container.appendChild(root);

            createEffect(() => {
                console.debug('[Effect触发] 执行全部Watcher');
                watchers.forEach(w => w());
            });
        };

        return { defineComponent, renderComponent };
    })();

    // ====================== 6. Toast工具函数 ======================
    const Utils = {
        toast(msg) {
            document.querySelectorAll('.mini-toast').forEach(el => el.remove());
            const tip = document.createElement('div');
            tip.className = 'mini-toast';
            tip.textContent = msg;
            tip.style.cssText = `
        position:fixed;top:20px;right:20px;
        background:#165DFF;color:#fff;
        padding:12px 20px;
        border-radius:6px;
        z-index:9999;
        transition:opacity 0.3s;
      `;
            document.body.appendChild(tip);
            setTimeout(() => {
                tip.style.opacity = '0';
                setTimeout(() => tip.remove(), 300);
            }, 1500);
        }
    };

    // 全局挂载API
    window.MiniSolidVue = {
        ...Reactive,
        ...Component,
        utils: Utils
    };
})(window)