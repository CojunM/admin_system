/**
 * MV-Solid-Vue 极简稳定版
 * Solid.js响应式 + Vue3模板语法 | 全流程容错，杜绝页面空白
 */
((window) => {
    'use strict';
    console.log('📦 框架核心加载成功');

    // ========== 1. 响应式系统（无崩溃容错）==========
    const effectStack = [];
    let activeEffect = null;

    function createSignal(initialValue) {
        const subscribers = new Set();
        const get = () => {
            if (activeEffect) subscribers.add(activeEffect);
            return initialValue;
        };
        const set = (newValue) => {
            try {
                const value = typeof newValue === 'function' ? newValue(initialValue) : newValue;
                if (Object.is(initialValue, value)) return;
                initialValue = value;
                subscribers.forEach(eff => { try { eff() } catch { } });
            } catch (e) {
                console.warn('信号更新失败', e);
            }
        };
        return [get, set];
    }

    function createEffect(fn) {
        try {
            const effect = () => {
                effectStack.push(effect);
                activeEffect = effect;
                try { fn() } finally {
                    effectStack.pop();
                    activeEffect = effectStack.at(-1) || null;
                }
            };
            effect();
        } catch (e) {
            console.warn('副作用执行失败', e);
        }
    }

    function createComputed(fn) {
        const [value, setValue] = createSignal();
        createEffect(() => setValue(fn()));
        return value;
    }

    // ========== 2. 工具函数 ==========
    const Utils = {
        parseVFor(str) {
            const reg = /^\s*([$\w]+)(?:\s*,\s*([$\w]+))?\s+in\s+([$\w]+)\s*$/;
            return str.match(reg) ? {
                itemKey: RegExp.$1,
                indexKey: RegExp.$2 || '$index',
                listKey: RegExp.$3
            } : null;
        },
        parseEvent(attr) {
            if (attr.startsWith('@')) return attr.slice(1);
            if (attr.startsWith('v-on:')) return attr.slice(5);
            return null;
        },
        evalExpr(expr, ctx = {}) {
            try {
                const keys = Object.keys(ctx);
                const values = Object.values(ctx);
                const res = new Function(...keys, `return ${expr.trim()}`)(...values);
                return res ?? '';
            } catch {
                return '';
            }
        },
        clone(el) {
            return el?.cloneNode(true) || null;
        }
    };

    // ========== 3. 编译器（容错优先，不阻断渲染）==========
    const Compiler = {
        // 渲染插值 {{}}
        renderText(node, ctx) {
            if (node.nodeType !== Node.TEXT_NODE) return;
            const content = node.textContent;
            if (!content?.includes('{{')) return;
            node.textContent = content.replace(/{{\s*([\w\(\).\s]+?)\s*}}/g, (_, exp) => Utils.evalExpr(exp, ctx));
        },

        // 递归编译节点
        compile(el, ctx, watchers) {
            if (!el || el.nodeType !== Node.ELEMENT_NODE) return;

            // 第一步：编译所有子节点（保证基础元素渲染）
            Array.from(el.childNodes).forEach(node => {
                try {
                    node.nodeType === Node.TEXT_NODE ? this.renderText(node, ctx) : this.compile(node, ctx, watchers);
                } catch { }
            });

            // 第二步：处理v-for指令
            const vForAttr = Array.from(el.attributes).find(a => a.name === 'v-for');
            if (vForAttr) {
                const parent = el.parentNode;
                const conf = Utils.parseVFor(vForAttr.value);
                if (!conf || !parent) return;

                // 克隆模板并删除原节点
                const tpl = Utils.clone(el);
                tpl?.removeAttribute('v-for');
                el.remove();

                // 列表更新函数
                const renderList = () => {
                    try {
                        parent.querySelectorAll('[data-item]').forEach(n => n.remove());
                        const listData = Utils.evalExpr(conf.listKey, ctx) || [];
                        listData.forEach((item, index) => {
                            const node = Utils.clone(tpl);
                            if (!node) return;
                            node.setAttribute('data-item', '');
                            // 注入循环变量
                            const childCtx = { ...ctx, [conf.itemKey]: item, [conf.indexKey]: index };
                            this.compile(node, childCtx, watchers);
                            parent.appendChild(node);
                        });
                    } catch { }
                };
                watchers.push(renderList);
                return;
            }

            // 第三步：绑定事件
            Array.from(el.attributes).forEach(attr => {
                try {
                    const eventName = Utils.parseEvent(attr.name);
                    if (!eventName) return;
                    el.removeAttribute(attr.name);
                    el.addEventListener(eventName, () => Utils.evalExpr(attr.value, ctx));
                } catch { }
            });
        },

        // 挂载入口
        mount(template, ctx, container) {
            try {
                if (!container || !template) throw new Error('挂载参数异常');
                const wrapper = document.createElement('div');
                wrapper.innerHTML = template.trim();
                const root = wrapper.firstElementChild;
                if (!root) throw new Error('模板无有效根节点');

                const watchers = [];
                this.compile(root, ctx, watchers);
                container.appendChild(root);

                // 初始化渲染
                createEffect(() => watchers.forEach(fn => { try { fn() } catch { } }));
                console.log('✅ 页面渲染完成');
            } catch (e) {
                console.error('❌ 挂载失败：', e);
                // 降级展示错误提示，不空白
                container.innerHTML = `<div style="padding:20px;color:red">页面渲染异常：${e.message}</div>`;
            }
        }
    };

    // ========== 4. 组件API ==========
    const MV = {
        createSignal,
        createEffect,
        createComputed,
        defineComponent(options) {
            return {
                setup: options.setup || (() => ({})),
                template: (options.template || '').trim()
            };
        },
        createApp(component) {
            return {
                mount(selector) {
                    const container = document.querySelector(selector);
                    if (!container) {
                        console.error(`❌ 未找到容器：${selector}`);
                        document.body.innerHTML += `<div style="color:red">未找到挂载节点：${selector}</div>`;
                        return;
                    }
                    const ctx = component.setup();
                    Compiler.mount(component.template, ctx, container);
                }
            };
        }
    };

    window.MVSolidVue = MV;
})(window);