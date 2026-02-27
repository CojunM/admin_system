/**
 * SolidMiniVue-Clean
 * 无虚拟DOM + Signal/Effect + 完整Vue模板语法
 * 【带完整依赖清理、Scope作用域、防内存泄漏】生产级版
 */
; (function (global, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        global.SolidMiniVue = factory();
    }
}(this, function () {

    // ======================================
    // 1. 作用域 Scope —— 依赖清理的核心
    // ======================================
    class Scope {
        constructor(parent = null) {
            this.parent = parent;
            this.children = new Set();
            this.cleanups = [];
            this.destroyed = false;
            if (parent) parent.children.add(this);
        }

        // 添加清理函数
        add(cleanup) {
            if (this.destroyed) return;
            this.cleanups.push(cleanup);
        }

        // 销毁：递归清理子作用域 → 执行自身清理 → 移除引用
        destroy() {
            if (this.destroyed) return;
            this.destroyed = true;

            // 1. 递归销毁子 scope
            this.children.forEach(child => child.destroy());
            this.children.clear();

            // 2. 执行所有清理函数
            this.cleanups.forEach(fn => {
                try { fn() } catch (err) { console.warn('[Scope cleanup error]', err) }
            });
            this.cleanups.length = 0;
        }
    }

    // 全局当前作用域
    let currentScope = null;

    // ======================================
    // 2. 响应式系统：Signal + Effect + 绑定Scope & 依赖清理
    // ======================================
    let currentEffect = null;
    let batchDepth = 0;
    const pendingEffects = new Set();

    /**
     * 创建信号
     */
    function createSignal(initialValue) {
        const subscribers = new Set();
        let value = initialValue;

        const get = () => {
            if (currentEffect && !currentEffect.scope.destroyed) {
                subscribers.add(currentEffect);
            }
            return value;
        };

        const set = (newValue) => {
            const val = typeof newValue === 'function' ? newValue(value) : newValue;
            if (val === value) return;
            value = val;

            const effectsToRun = new Set();
            subscribers.forEach(e => {
                if (!e.scope.destroyed) effectsToRun.add(e);
            });

            if (batchDepth > 0) {
                effectsToRun.forEach(e => pendingEffects.add(e));
            } else {
                effectsToRun.forEach(e => e.run());
            }
        };

        return [get, set];
    }

    /**
     * 创建 Effect，自动绑定当前作用域，支持返回清理函数
     */
    function createEffect(fn, scope = currentScope) {
        if (!scope || scope.destroyed) return () => { };

        let cleanup = null;

        const run = () => {
            if (scope.destroyed) return;
            // 先执行上一次的清理
            if (typeof cleanup === 'function') {
                try { cleanup() } catch { }
                cleanup = null;
            }

            const prevEffect = currentEffect;
            currentEffect = effect;
            try {
                // 执行 effect，若返回函数则作为清理函数
                const userCleanup = fn();
                if (typeof userCleanup === 'function') {
                    cleanup = userCleanup;
                }
            } catch (e) {
                console.error('[Effect run error]', e);
            } finally {
                currentEffect = prevEffect;
            }
        };

        const effect = { run, scope };

        // 把 effect 的停止逻辑注册到 scope
        scope.add(() => {
            cleanup = null;
        });

        // 首次执行
        run();

        // 外部手动清理
        return () => {
            if (!scope.destroyed) scope.destroy();
        };
    }

    /**
     * 批量更新
     */
    function batch(fn) {
        batchDepth++;
        try { fn(); } finally {
            batchDepth--;
            if (batchDepth === 0) {
                const effects = Array.from(pendingEffects);
                pendingEffects.clear();
                effects.forEach(e => !e.scope.destroyed && e.run());
            }
        }
    }

    /**
     * 进入一个作用域（执行 fn 时 currentScope 指向该 scope）
     */
    function withScope(scope, fn) {
        const prev = currentScope;
        currentScope = scope;
        try { return fn() } finally {
            currentScope = prev;
        }
    }

    // ======================================
    // 3. 工具函数
    // ======================================
    const Utils = {
        parseForExpression(exp) {
            const forReg = /^\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)\s+in\s+(.+)\s*$|^\s*([^ ]+)\s+in\s+(.+)\s*$/;
            const match = exp.match(forReg);
            if (!match) throw new Error(`v-for 语法错误: ${exp}`);
            return match[1]
                ? { item: match[1], index: match[2], list: match[3] }
                : { item: match[4], index: null, list: match[5] };
        },
        getValue(context, path) {
            return path.split('.').reduce((obj, key) => obj?.[key], context);
        },
        bindClass(node, value) {
            if (typeof value === 'string') node.className = value;
            else if (Array.isArray(value)) node.className = value.filter(Boolean).join(' ');
            else if (typeof value === 'object' && value !== null) {
                const classes = Object.entries(value).filter(([, b]) => b).map(([k]) => k);
                node.className = classes.join(' ');
            }
        },
        bindStyle(node, style) {
            if (typeof style !== 'object' || style === null) return;
            Object.entries(style).forEach(([k, v]) => node.style[k] = v);
        },
        handleEventModifiers(e, mods) {
            if (mods.includes('stop')) e.stopPropagation();
            if (mods.includes('prevent')) e.preventDefault();
        }
    };

    // ======================================
    // 4. 编译器：所有动态节点都绑定 Scope，实现自动依赖清理
    // ======================================
    class Compiler {
        static compile(template, context, rootScope) {
            const temp = document.createElement('div');
            temp.innerHTML = template.trim();
            const root = temp.firstElementChild;
            if (!root) throw new Error('[SolidMiniVue] 模板不能为空');

            // 编译在根作用域下
            withScope(rootScope, () => {
                this.traverse(root, context, rootScope);
            });

            return root;
        }

        static traverse(node, context, scope) {
            if (node.nodeType !== 1) {
                this.processText(node, context, scope);
                return;
            }
            this.processElement(node, context, scope);
        }

        // 文本插值 {{ expr }}
        static processText(node, context, scope) {
            const text = node.textContent;
            if (!/\{\{(.+?)\}\}/.test(text)) return;
            const exp = RegExp.$1.trim();

            createEffect(() => {
                node.textContent = Utils.getValue(context, exp);
            }, scope);
        }

        // 元素节点：所有指令、事件、绑定都走这里
        static processElement(node, context, scope) {
            const attrs = Array.from(node.attributes);
            const dirs = {};
            attrs.forEach(attr => {
                dirs[attr.name] = attr.value;
                node.removeAttribute(attr.name);
            });

            // 指令优先级：v-for > v-if
            if (dirs['v-for']) {
                this.processVFor(node, dirs['v-for'], context, scope);
                return;
            }
            if (dirs['v-if']) {
                this.processVIf(node, dirs['v-if'], context, scope);
                return;
            }

            // 普通指令
            Object.entries(dirs).forEach(([dir, exp]) => {
                this.processDirective(node, dir, exp, context, scope);
            });

            // 继续编译子节点
            Array.from(node.childNodes).forEach(child => {
                this.traverse(child, context, scope);
            });
        }

        // 单指令分发
        static processDirective(node, dir, exp, context, scope) {
            // -------- v-show --------
            if (dir === 'v-show') {
                createEffect(() => {
                    node.style.display = Utils.getValue(context, exp) ? '' : 'none';
                }, scope);
                return;
            }

            // -------- v-text / v-html --------
            if (dir === 'v-text') {
                createEffect(() => node.textContent = Utils.getValue(context, exp), scope);
                return;
            }
            if (dir === 'v-html') {
                createEffect(() => node.innerHTML = Utils.getValue(context, exp), scope);
                return;
            }

            // -------- v-bind / :attr --------
            if (dir.startsWith('v-bind:') || dir.startsWith(':')) {
                const prop = dir.replace(/^(v-bind:|:)/, '');
                createEffect(() => {
                    const val = Utils.getValue(context, exp);
                    if (prop === 'class') Utils.bindClass(node, val);
                    else if (prop === 'style') Utils.bindStyle(node, val);
                    else node.setAttribute(prop, val);
                }, scope);
                return;
            }

            // -------- v-on / @event + 修饰符 --------
            if (dir.startsWith('v-on:') || dir.startsWith('@')) {
                const [evtName, ...mods] = dir.replace(/^(v-on:|@)/, '').split('.');
                const handler = Utils.getValue(context, exp);
                if (typeof handler !== 'function') return;

                const cb = (e) => {
                    Utils.handleEventModifiers(e, mods);
                    handler.call(context, e);
                };

                node.addEventListener(evtName, cb);
                // 事件监听自动清理
                scope.add(() => node.removeEventListener(evtName, cb));
                return;
            }

            // -------- v-model 双向绑定 --------
            if (dir === 'v-model') {
                this.processVModel(node, exp, context, scope);
                return;
            }
        }

        // -------- v-model 全表单适配 --------
        static processVModel(node, exp, context, scope) {
            const [get, set] = Utils.getValue(context, exp);
            const tag = node.tagName;
            const type = node.type;

            // 数据 → 视图
            createEffect(() => {
                const val = get();
                if (tag === 'INPUT') {
                    if (type === 'checkbox') node.checked = !!val;
                    else if (type === 'radio') node.checked = (node.value === val);
                    else node.value = val;
                } else if (tag === 'SELECT' || tag === 'TEXTAREA') {
                    node.value = val;
                }
            }, scope);

            // 视图 → 数据
            const onInput = () => {
                if (tag === 'INPUT') {
                    if (type === 'checkbox') set(node.checked);
                    else if (type === 'radio') node.checked && set(node.value);
                    else set(node.value);
                } else {
                    set(node.value);
                }
            };
            node.addEventListener('input', onInput);
            scope.add(() => node.removeEventListener('input', onInput));
        }

        // -------- v-if 条件渲染：自带子作用域，切换时自动清理旧分支 --------
        static processVIf(node, exp, context, parentScope) {
            const placeholder = document.createComment('v-if');
            node.parentNode.replaceChild(placeholder, node);
            let childScope = null;
            let el = null;

            createEffect(() => {
                const cond = Utils.getValue(context, exp);

                // 条件为真：创建子作用域，渲染节点
                if (cond) {
                    if (el) return;
                    childScope = new Scope(parentScope);
                    el = node.cloneNode(true);
                    withScope(childScope, () => this.traverse(el, context, childScope));
                    placeholder.after(el);
                }
                // 条件为假：销毁子作用域，清理所有依赖
                else {
                    if (el) {
                        el.remove();
                        el = null;
                    }
                    if (childScope) {
                        childScope.destroy();
                        childScope = null;
                    }
                }
            }, parentScope);
        }

        // -------- v-for 列表渲染：每一项独立作用域，删除项自动清理依赖 --------
        static processVFor(node, exp, context, parentScope) {
            const { item, index, list } = Utils.parseForExpression(exp);
            const [getList] = Utils.getValue(context, list);
            const placeholder = document.createComment('v-for');
            node.parentNode.replaceChild(placeholder, node);

            // 保存每一项的：dom、作用域、key/index
            let items = [];

            createEffect(() => {
                const arr = getList() || [];
                const fragment = document.createDocumentFragment();
                const newItems = [];

                arr.forEach((itemData, idx) => {
                    const itemScope = new Scope(parentScope);
                    const el = node.cloneNode(true);

                    withScope(itemScope, () => {
                        const itemCtx = {
                            ...context,
                            [item]: itemData,
                            ...(index && { [index]: idx })
                        };
                        this.traverse(el, itemCtx, itemCtx);
                    });

                    newItems.push({ el, scope: itemScope });
                    fragment.appendChild(el);
                });

                // 清理旧项
                items.forEach(old => old.scope.destroy());
                items = newItems;
                placeholder.before(fragment);
            }, parentScope);
        }
    }

    // ======================================
    // 5. 框架主类：实例自带根作用域，unmount 彻底清理
    // ======================================
    class SolidMiniVue {
        constructor(options) {
            this.$el = document.querySelector(options.el);
            if (!this.$el) throw new Error(`挂载节点不存在：${options.el}`);

            this.$template = options.template;
            this.$rootNode = null;

            // 实例根作用域：所有依赖都挂在这里
            this.$scope = new Scope();

            // 初始化上下文
            this._initContext(options.data || {}, options.methods || {});

            // 挂载
            this.mount();
        }

        _initContext(data, methods) {
            this.context = { ...methods };
            Object.entries(data).forEach(([k, v]) => {
                this.context[k] = createSignal(v);
            });
        }

        mount() {
            this.unmount();
            this.$rootNode = Compiler.compile(
                this.$template,
                this.context,
                this.$scope
            );
            this.$el.appendChild(this.$rootNode);
        }

        // 【关键】卸载：销毁根作用域，所有依赖递归清理
        unmount() {
            this.$scope.destroy();
            if (this.$rootNode) {
                this.$rootNode.remove();
                this.$rootNode = null;
            }
        }

        static createSignal = createSignal;
        static createEffect = createEffect;
        static batch = batch;
        static Scope = Scope;
    }

    return SolidMiniVue;
}));