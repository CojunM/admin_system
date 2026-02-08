/**
 * SolidMiniVue - 组件化增强版
 * Signal响应式 + Scope依赖清理 + 完整Vue语法 + 组件化系统
 */
; (function (global, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        global.SolidMiniVue = factory();
    }
}(this, function () {
    // ========== 1. Scope 作用域：依赖清理核心 ==========
    class Scope {
        constructor(parent = null) {
            this.parent = parent;
            this.children = new Set();
            this.cleanups = [];
            this.destroyed = false;
            if (parent) parent.children.add(this);
        }
        add(cleanup) {
            if (this.destroyed) return;
            this.cleanups.push(cleanup);
        }
        destroy() {
            if (this.destroyed) return;
            this.destroyed = true;
            this.children.forEach(child => child.destroy());
            this.children.clear();
            this.cleanups.forEach(fn => { try { fn() } catch { } });
            this.cleanups.length = 0;
        }
    }
    let currentScope = null;
    let currentEffect = null;
    let batchDepth = 0;
    const pendingEffects = new Set();

    // ========== 2. 响应式核心 ==========
    function createSignal(initialValue) {
        const subscribers = new Set();
        let value = initialValue;
        const get = () => {
            if (currentEffect && !currentEffect.scope.destroyed) subscribers.add(currentEffect);
            return value;
        };
        const set = (newValue) => {
            const val = typeof newValue === 'function' ? newValue(value) : newValue;
            if (val === value) return;
            value = val;
            const effects = Array.from(subscribers).filter(e => !e.scope.destroyed);
            batchDepth > 0 ? effects.forEach(e => pendingEffects.add(e)) : effects.forEach(e => e.run());
        };
        return [get, set];
    }

    function createEffect(fn, scope = currentScope) {
        if (!scope || scope.destroyed) return () => { };
        let cleanupFn = null;
        const run = () => {
            if (scope.destroyed) return;
            cleanupFn?.(); cleanupFn = null;
            const prev = currentEffect;
            currentEffect = { run, scope };
            try {
                const res = fn();
                if (typeof res === 'function') cleanupFn = res;
            } catch (e) { console.error('[Effect Error]', e) }
            finally { currentEffect = prev; }
        };
        const effect = { run, scope };
        scope.add(() => { cleanupFn?.(); });
        run();
        return () => scope.destroy();
    }

    function batch(fn) {
        batchDepth++;
        try { fn() } finally {
            batchDepth--;
            if (batchDepth === 0) {
                const arr = Array.from(pendingEffects);
                pendingEffects.clear();
                arr.forEach(e => !e.scope.destroyed && e.run());
            }
        }
    }

    function withScope(scope, fn) {
        const prev = currentScope;
        currentScope = scope;
        try { return fn() } finally { currentScope = prev; }
    }

    // ========== 3. 工具函数 ==========
    const Utils = {
        getValue(ctx, path) {
            return path?.split('.').reduce((o, k) => o?.[k], ctx);
        },
        parseFor(exp) {
            const reg = /^\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)\s+in\s+(.+)\s*$|^\s*([^ ]+)\s+in\s+(.+)\s*$/;
            const m = exp.match(reg);
            return m[1] ? { item: m[1], index: m[2], list: m[3] } : { item: m[4], index: null, list: m[5] };
        },
        bindClass(node, val) {
            if (typeof val === 'string') node.className = val;
            else if (Array.isArray(val)) node.className = val.filter(Boolean).join(' ');
            else if (val && typeof val === 'object') {
                node.className = Object.entries(val).filter(([, b]) => b).map(([k]) => k).join(' ');
            }
        },
        bindStyle(node, style) {
            if (!style || typeof style !== 'object') return;
            Object.entries(style).forEach(([k, v]) => node.style[k] = v);
        },
        handleModifiers(e, mods) {
            mods.includes('stop') && e.stopPropagation();
            mods.includes('prevent') && e.preventDefault();
        }
    };

    // ========== 4. 编译器 + 组件渲染 ==========
    class Compiler {
        static compile(tpl, ctx, scope) {
            const temp = document.createElement('div');
            temp.innerHTML = tpl.trim();
            const root = temp.firstElementChild;
            if (!root) throw new Error('模板为空');
            withScope(scope, () => this.traverse(root, ctx, scope));
            return root;
        }

        static traverse(node, ctx, scope) {
            if (node.nodeType !== 1) {
                this.processText(node, ctx, scope);
                return;
            }
            const tag = node.tagName.toLowerCase();
            if (SolidMiniVue.globalComponents[tag]) {
                this.renderComponent(node, ctx, scope);
                return;
            }
            this.processElement(node, ctx, scope);
        }

        static processText(node, ctx, scope) {
            if (!/\{\{(.+?)\}\}/.test(node.textContent)) return;
            const exp = RegExp.$1.trim();
            createEffect(() => node.textContent = Utils.getValue(ctx, exp), scope);
        }

        static processElement(node, ctx, scope) {
            const attrs = Array.from(node.attributes);
            const dirs = {};
            attrs.forEach(a => { dirs[a.name] = a.value; node.removeAttribute(a.name); });

            if (dirs['v-for']) { this.processVFor(node, dirs['v-for'], ctx, scope); return; }
            if (dirs['v-if']) { this.processVIf(node, dirs['v-if'], ctx, scope); return; }

            Object.entries(dirs).forEach(([d, exp]) => this.execDirective(node, d, exp, ctx, scope));
            Array.from(node.childNodes).forEach(c => this.traverse(c, ctx, scope));
        }

        static execDirective(node, dir, exp, ctx, scope) {
            if (dir === 'v-show') {
                createEffect(() => node.style.display = Utils.getValue(ctx, exp) ? '' : 'none', scope);
            } else if (dir === 'v-text') {
                createEffect(() => node.textContent = Utils.getValue(ctx, exp), scope);
            } else if (dir === 'v-html') {
                createEffect(() => node.innerHTML = Utils.getValue(ctx, exp), scope);
            } else if (dir.startsWith(':') || dir.startsWith('v-bind:')) {
                const k = dir.replace(/^(:|v-bind:)/, '');
                createEffect(() => {
                    const v = Utils.getValue(ctx, exp);
                    k === 'class' ? Utils.bindClass(node, v) :
                        k === 'style' ? Utils.bindStyle(node, v) : node.setAttribute(k, v);
                }, scope);
            } else if (dir.startsWith('@') || dir.startsWith('v-on:')) {
                const [evt, ...mods] = dir.replace(/^(@|v-on:)/, '').split('.');
                const handler = Utils.getValue(ctx, exp);
                if (!handler) return;
                const cb = e => { Utils.handleModifiers(e, mods); handler.call(ctx, e); };
                node.addEventListener(evt, cb);
                scope.add(() => node.removeEventListener(evt, cb));
            } else if (dir === 'v-model') {
                this.processModel(node, exp, ctx, scope);
            }
        }

        static processModel(node, exp, ctx, scope) {
            const [get, set] = Utils.getValue(ctx, exp);
            const tag = node.tagName;
            const type = node.type;
            createEffect(() => {
                const v = get();
                if (tag === 'INPUT') {
                    type === 'checkbox' ? node.checked = !!v :
                        type === 'radio' ? node.checked = node.value === v : node.value = v;
                } else node.value = v;
            }, scope);
            const cb = () => {
                tag === 'INPUT' && type === 'checkbox' ? set(node.checked) :
                    tag === 'INPUT' && type === 'radio' && node.checked ? set(node.value) : set(node.value);
            };
            node.addEventListener('input', cb);
            scope.add(() => node.removeEventListener('input', cb));
        }

        static processVFor(node, exp, ctx, pScope) {
            const { item, index, list } = Utils.parseFor(exp);
            const [getList] = Utils.getValue(ctx, list);
            const placeholder = document.createComment('vfor');
            node.parentNode.replaceChild(placeholder, node);
            let items = [];
            createEffect(() => {
                const arr = getList() || [];
                items.forEach(i => i.scope.destroy());
                items = [];
                const frag = document.createDocumentFragment();
                arr.forEach((d, i) => {
                    const s = new Scope(pScope);
                    const el = node.cloneNode(true);
                    const cCtx = { ...ctx, [item]: d, ...(index && { [index]: i }) };
                    withScope(s, () => this.traverse(el, cCtx, s));
                    items.push({ el, scope: s });
                    frag.appendChild(el);
                });
                placeholder.before(frag);
            }, pScope);
        }

        static processVIf(node, exp, ctx, pScope) {
            const placeholder = document.createComment('vif');
            node.parentNode.replaceChild(placeholder, node);
            let s = null, el = null;
            createEffect(() => {
                const cond = Utils.getValue(ctx, exp);
                if (cond && !el) {
                    s = new Scope(pScope);
                    el = node.cloneNode(true);
                    withScope(s, () => this.traverse(el, ctx, s));
                    placeholder.after(el);
                } else if (!cond && el) {
                    el.remove(); el = null; s.destroy(); s = null;
                }
            }, pScope);
        }

        static renderComponent(placeholder, pCtx, pScope) {
            const tag = placeholder.tagName.toLowerCase();
            const Comp = SolidMiniVue.globalComponents[tag];
            const cScope = new Scope(pScope);
            const attrs = Array.from(placeholder.attributes);
            const propsData = {};
            const events = {};
            attrs.forEach(a => {
                const n = a.name, v = a.value;
                if (n.startsWith(':')) propsData[n.slice(1)] = v;
                else if (n.startsWith('@')) events[n.slice(1)] = v;
                placeholder.removeAttribute(n);
            });

            const emit = (evt, ...args) => {
                const handler = Utils.getValue(pCtx, events[evt]);
                handler && handler(...args);
            };

            const props = {};
            Object.entries(Comp.props || {}).forEach(([k, opt]) => {
                const path = propsData[k];
                const [val, setVal] = createSignal(opt.default);
                props[k] = val;
                if (path) createEffect(() => setVal(Utils.getValue(pCtx, path)), cScope);
            });

            const exports = Comp.setup(props, { emit, scope: cScope }) || {};
            const cCtx = { ...props, ...exports };
            const root = this.compile(Comp.template, cCtx, cScope);
            placeholder.parentNode.replaceChild(root, placeholder);
            pScope.add(() => cScope.destroy());
        }
    }

    // ========== 5. 框架主类 ==========
    class SolidMiniVue {
        static globalComponents = {};
        static registerComponent(name, opt) {
            if (!opt.template) throw new Error(`组件${name}缺少template`);
            this.globalComponents[name.toLowerCase()] = opt;
        }
        static createSignal = createSignal;
        static createEffect = createEffect;
        static batch = batch;

        constructor(opt) {
            this.$el = document.querySelector(opt.el);
            if (!this.$el) throw new Error('挂载节点不存在');
            this.$tpl = opt.template;
            this.$scope = new Scope();
            this._initCtx(opt.data || {}, opt.methods || {});
            this.mount();
        }
        _initCtx(data, methods) {
            this.ctx = { ...methods };
            Object.entries(data).forEach(([k, v]) => this.ctx[k] = createSignal(v));
        }
        mount() {
            this.unmount();
            this.$root = Compiler.compile(this.$tpl, this.ctx, this.$scope);
            this.$el.appendChild(this.$root);
        }
        unmount() {
            this.$scope.destroy();
            this.$root?.remove();
            this.$root = null;
        }
    }
    return SolidMiniVue;
}));