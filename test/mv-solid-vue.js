/**
 * MV-Solid-Vue 1.0.0
 * 融合 Solid.js 响应式核心 + Vue3 模板编译语法
 * 单文件可复用版 | 支持多页面/多实例引入
 * @author Custom Framework
 */
((window) => {
    'use strict';

    // ====================== 1. Solid.js 响应式核心 ======================
    const effectStack = [];
    let activeEffect = null;

    /**
     * 创建响应式信号
     * @param {*} initialValue 初始值
     * @returns {[Function, Function]} [getter, setter]
     */
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
                // 批量触发副作用，异常隔离
                subscribers.forEach(eff => {
                    try { eff(); } catch { }
                });
            } catch (e) {
                console.warn('[Signal] 更新失败:', e);
            }
        };
        return [get, set];
    }

    /**
     * 创建副作用函数（依赖自动收集）
     * @param {Function} fn 副作用回调
     */
    function createEffect(fn) {
        try {
            const effect = () => {
                effectStack.push(effect);
                activeEffect = effect;
                try {
                    fn();
                } finally {
                    effectStack.pop();
                    activeEffect = effectStack.at(-1) ?? null;
                }
            };
            effect();
        } catch (e) {
            console.warn('[Effect] 执行失败:', e);
        }
    }

    /**
     * 创建计算属性（依赖响应式自动更新）
     * @param {Function} fn 计算逻辑
     * @returns {Function} 计算值 getter
     */
    function createComputed(fn) {
        const [value, setValue] = createSignal();
        createEffect(() => setValue(fn()));
        return value;
    }

    // ====================== 2. 工具函数集 ======================
    const Utils = {
        /**
         * 解析 Vue3 v-for 语法：item,index in list
         */
        parseVFor(str) {
            const reg = /^\s*([$\w]+)(?:\s*,\s*([$\w]+))?\s+in\s+([$\w]+)\s*$/;
            const match = str.match(reg);
            if (!match) return null;
            return {
                itemKey: match[1],
                indexKey: match[2] || '$index',
                listKey: match[3]
            };
        },

        /**
         * 解析事件指令：@click / v-on:click
         */
        parseEvent(attrName) {
            if (attrName.startsWith('@')) return attrName.slice(1);
            if (attrName.startsWith('v-on:')) return attrName.slice(5);
            return null;
        },

        /**
         * 安全执行表达式，支持响应式 getter 解析
         */
        evalExpr(expr, ctx = {}) {
            if (!expr) return '';
            try {
                const keys = Object.keys(ctx);
                const values = Object.values(ctx);
                const result = new Function(...keys, `return ${expr.trim()}`)(...values);
                // 自动解包响应式 getter
                return typeof result === 'function' ? result() : result ?? '';
            } catch {
                return '';
            }
        },

        /**
         * 安全克隆DOM节点
         */
        cloneNode(el) {
            return el?.cloneNode(true) ?? null;
        }
    };

    // ====================== 3. Vue3 模板编译器 ======================
    const Compiler = {
        /**
         * 渲染插值表达式 {{ expr }}
         */
        renderInterpolation(node, ctx) {
            if (node.nodeType !== Node.TEXT_NODE) return;
            const content = node.textContent;
            if (!content?.includes('{{')) return;

            node.textContent = content.replace(
                /{{\s*([\w\(\).\s]+?)\s*}}/g,
                (_, exp) => Utils.evalExpr(exp, ctx)
            );
        },

        /**
         * 递归编译DOM节点
         * @param {HTMLElement} el 目标节点
         * @param {Object} ctx 上下文
         * @param {Array} watchers 响应式更新队列
         * @param {Boolean} isTemplate 是否为v-for模板节点（禁止提前渲染插值）
         */
        compile(el, ctx, watchers, isTemplate = false) {
            if (!el || el.nodeType !== Node.ELEMENT_NODE) return;

            // 递归处理子节点：模板节点跳过插值渲染
            Array.from(el.childNodes).forEach(node => {
                try {
                    if (node.nodeType === Node.TEXT_NODE && !isTemplate) {
                        this.renderInterpolation(node, ctx);
                    } else if (node.nodeType === Node.ELEMENT_NODE) {
                        this.compile(node, ctx, watchers, isTemplate);
                    }
                } catch { }
            });

            // 处理 v-for 循环指令
            const vForAttr = Array.from(el.attributes).find(attr => attr.name === 'v-for');
            if (vForAttr) {
                const parent = el.parentNode;
                const vForConf = Utils.parseVFor(vForAttr.value);
                if (!vForConf || !parent) return;

                // 生成模板并移除原节点
                const template = Utils.cloneNode(el);
                template?.removeAttribute('v-for');
                el.remove();

                // 列表渲染函数
                const renderList = () => {
                    try {
                        // 清理旧节点
                        parent.querySelectorAll('[data-mv-item]').forEach(n => n.remove());
                        // 获取并格式化列表数据
                        const rawData = Utils.evalExpr(vForConf.listKey, ctx);
                        const listData = Array.isArray(rawData) ? rawData : [];

                        // 渲染每一项
                        listData.forEach((item, index) => {
                            const itemNode = Utils.cloneNode(template);
                            if (!itemNode) return;

                            itemNode.setAttribute('data-mv-item', '');
                            // 注入循环变量上下文
                            const childCtx = { ...ctx, [vForConf.itemKey]: item, [vForConf.indexKey]: index };
                            // 编译节点并渲染插值
                            this.compile(itemNode, childCtx, watchers, false);
                            Array.from(itemNode.childNodes).forEach(n => this.renderInterpolation(n, childCtx));
                            parent.appendChild(itemNode);
                        });
                    } catch (e) {
                        console.error('[Compiler] 列表渲染失败:', e);
                    }
                };

                watchers.push(renderList);
                renderList(); // 初始化渲染
                return;
            }

            // 绑定事件指令 @click / v-on:xxx
            Array.from(el.attributes).forEach(attr => {
                try {
                    const eventName = Utils.parseEvent(attr.name);
                    if (!eventName) return;
                    el.removeAttribute(attr.name);
                    // 事件绑定：执行表达式
                    el.addEventListener(eventName, () => Utils.evalExpr(attr.value, ctx));
                } catch { }
            });
        },

        /**
         * 应用挂载入口
         */
        mount(template, ctx, container) {
            try {
                if (!container || !template) throw new Error('挂载参数缺失');
                const wrapper = document.createElement('div');
                wrapper.innerHTML = template.trim();
                const root = wrapper.firstElementChild;
                if (!root) throw new Error('模板无有效根节点');

                const watchers = [];
                this.compile(root, ctx, watchers, false);
                container.appendChild(root);

                // 响应式更新绑定
                createEffect(() => watchers.forEach(fn => { try { fn(); } catch { } }));
                console.log('✅ MV-Solid-Vue 挂载成功');
            } catch (e) {
                console.error('❌ 挂载失败:', e);
                container.innerHTML = `<div style="color:red;padding:20px">渲染异常：${e.message}</div>`;
            }
        }
    };

    // ====================== 4. Vue3 风格组件API ======================
    const Framework = {
        createSignal,
        createEffect,
        createComputed,
        /**
         * 定义组件
         */
        defineComponent(options) {
            return {
                setup: options.setup || (() => ({})),
                template: (options.template || '').trim()
            };
        },
        /**
         * 创建应用实例
         */
        createApp(component) {
            return {
                mount(selector) {
                    const container = document.querySelector(selector);
                    if (!container) {
                        console.error(`❌ 未找到挂载节点：${selector}`);
                        return;
                    }
                    const ctx = component.setup();
                    Compiler.mount(component.template, ctx, container);
                }
            };
        }
    };

    // 全局导出，支持 ESM / 全局变量 两种引入方式
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = Framework;
    } else {
        window.MVSolidVue = Framework;
    }
})(window);