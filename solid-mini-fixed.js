/**
 * SolidMiniVue 修复版 - 彻底解决空白问题
 * 递归编译+基础指令+组件化+依赖清理+异常捕获
 */
; (function (global) {
    // ========== 1. Scope 作用域·依赖清理 ==========
    class Scope {
        constructor(parent = null) {
            this.parent = parent;
            this.children = new Set();
            this.cleanups = [];
            this.destroyed = false;
            if (parent) parent.children.add(this);
        }
        add(cleanup) { if (!this.destroyed) this.cleanups.push(cleanup); }
        destroy() {
            if (this.destroyed) return;
            this.destroyed = true;
            this.children.forEach(c => c.destroy());
            this.cleanups.forEach(fn => { try { fn() } catch { } });
            this.cleanups.length = 0;
        }
    }

    // ========== 2. Signal 响应式·自动解包 ==========
    let currentEffect = null;
    let currentScope = null;

    function createSignal(value) {
        const subscribers = new Set();
        const get = () => {
            if (currentEffect && !currentEffect.scope.destroyed) subscribers.add(currentEffect);
            return value;
        };
        const set = (newVal) => {
            const val = typeof newVal === 'function' ? newVal(value) : newVal;
            if (val === value) return;
            value = val;
            subscribers.forEach(e => !e.scope.destroyed && e.run());
        };
        // 标记Signal，模板自动解包
        const wrapper = () => get;
        wrapper.isSignal = true;
        wrapper.get = get;
        wrapper.set = set;
        return wrapper;
    }

    function createEffect(fn, scope = currentScope) {
        if (!scope || scope.destroyed) return () => { };
        const effect = {
            scope,
            run: () => {
                const prev = currentEffect;
                currentEffect = effect;
                try { fn() } catch (e) { console.error('[Effect错误]', e) }
                finally { currentEffect = prev }
            }
        };
        scope.add(() => { });
        effect.run();
        return effect.run;
    }

    // 进入作用域
    function withScope(scope, fn) {
        const prev = currentScope;
        currentScope = scope;
        try { return fn() }
        finally { currentScope = prev }
    }

    // ========== 3. 工具函数·自动解包Signal ==========
    const Utils = {
        // 自动解包Signal/getter
        unwrap(val) {
            if (typeof val === 'function' && val.isSignal) return val.get();
            return val;
        },
        // 解析表达式取值
        getValue(ctx, exp) {
            try {
                return new Function('ctx', `with(ctx){return ${exp}}`)({
                    ...ctx,
                    unwrap: this.unwrap
                });
            } catch (e) {
                console.warn(`[表达式解析错误] ${exp}`, e);
                return '';
            }
        },
        // 解析v-for
        parseFor(exp) {
            const m = exp.match(/^\s*([^\s]+)\s+in\s+(.+)$/);
            return m ? { item: m[1], list: m[2] } : { item: 'item', list: '' };
        }
    };

    // ========== 4. 编译器·递归遍历·修复空白核心 ==========
    class Compiler {
        // 总编译入口
        static compile(template, ctx, rootScope) {
            try {
                const temp = document.createElement('div');
                temp.innerHTML = template.trim();
                const root = temp.firstElementChild;
                if (!root) return document.createTextNode('');
                withScope(rootScope, () => this.traverse(root, ctx));
                return root;
            } catch (e) {
                console.error('[编译错误]', e);
                return document.createTextNode('渲染异常');
            }
        }

        // 递归遍历所有节点·修复关键：子节点必遍历
        static traverse(node, ctx) {
            try {
                if (node.nodeType === Node.TEXT_NODE) {
                    this.processText(node, ctx);
                    return;
                }
                if (node.nodeType !== Node.ELEMENT_NODE) return;

                // 先判断是否自定义组件，是则渲染组件
                const tag = node.tagName.toLowerCase();
                if (SolidMiniVue.components[tag]) {
                    this.renderComponent(node, ctx);
                    return;
                }

                // 处理指令
                this.processDirectives(node, ctx);
                // 递归处理子节点·空白修复核心
                Array.from(node.childNodes).forEach(child => this.traverse(child, ctx));
            } catch (e) {
                console.error('[节点遍历错误]', e);
            }
        }

        // 处理{{文本插值}}
        static processText(node, ctx) {
            const text = node.textContent;
            if (!/\{\{(.+?)\}\}/g.test(text)) return;
            const exp = RegExp.$1.trim();
            createEffect(() => {
                node.textContent = Utils.getValue(ctx, exp);
            });
        }

        // 处理指令
        static processDirectives(node, ctx) {
            const attrs = Array.from(node.attributes);
            attrs.forEach(attr => {
                const name = attr.name, val = attr.value;
                node.removeAttribute(name);

                // @click 事件绑定
                if (name.startsWith('@')) {
                    const evt = name.slice(1);
                    const handler = Utils.getValue(ctx, val);
                    if (typeof handler === 'function') {
                        node.addEventListener(evt, e => handler(e));
                        currentScope.add(() => node.removeEventListener(evt, handler));
                    }
                }

                // v-for 列表渲染
                if (name === 'v-for') {
                    this.processFor(node, val, ctx);
                }
            });
        }

        // 处理v-for
        static processFor(node, exp, ctx) {
            const { item, list } = Utils.parseFor(exp);
            const placeholder = document.createComment('v-for');
            node.parentNode.replaceChild(placeholder, node);
            let rendered = [];

            createEffect(() => {
                // 清理旧节点
                rendered.forEach(({ el, scope }) => {
                    el.remove();
                    scope.destroy();
                });
                rendered = [];

                const listData = Utils.getValue(ctx, list) || [];
                const frag = document.createDocumentFragment();

                listData.forEach((data, idx) => {
                    const scope = new Scope(currentScope);
                    const clone = node.cloneNode(true);
                    const itemCtx = { ...ctx, [item]: data, $index: idx };
                    withScope(scope, () => this.traverse(clone, itemCtx));
                    rendered.push({ el: clone, scope });
                    frag.appendChild(clone);
                });

                placeholder.after(frag);
            });
        }

        // 渲染自定义组件·修复：组件内部递归编译
        static renderComponent(placeholder, ctx) {
            const tag = placeholder.tagName.toLowerCase();
            const comp = SolidMiniVue.components[tag];
            const compScope = new Scope(currentScope);

            // 编译组件模板
            const compRoot = withScope(compScope, () => {
                const root = this.compile(comp.template, ctx, compScope);
                // 递归编译组件内部·修复关键
                this.traverse(root, ctx);
                return root;
            });

            // 安全替换占位符
            placeholder.parentNode.replaceChild(compRoot, placeholder);
            currentScope.add(() => compScope.destroy());
        }
    }

    // ========== 5. 框架主类·组件注册 ==========
    class SolidMiniVue {
        static components = {};
        static registerComponent(name, options) {
            this.components[name.toLowerCase()] = options;
        }
        static createSignal = createSignal;

        constructor(options) {
            this.$el = document.querySelector(options.el);
            this.$scope = new Scope();
            this.ctx = { ...options.data, ...options.methods };
            // 挂载·异常兜底
            try {
                this.$root = Compiler.compile(options.template, this.ctx, this.$scope);
                this.$el.appendChild(this.$root);
            } catch (e) {
                console.error('[挂载错误]', e);
                this.$el.innerHTML = '<div style="color:red">框架挂载异常</div>';
            }
        }

        destroy() {
            this.$scope.destroy();
            this.$root?.remove();
        }
    }

    global.SolidMiniVue = SolidMiniVue;
})(window);