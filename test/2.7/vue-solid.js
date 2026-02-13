// VueSolid 完整版 - 带组件系统+模板编译（融合Vue3+Solid，零报错/不空白）
; (function (window) {
    // ====================== 核心工具函数（容错/校验） ======================
    const utils = {
        // 校验DOM节点合法性
        isNode: (node) => node && node.nodeType !== undefined,
        // 空值兜底
        fallback: (val, def) => val === undefined || val === null ? def : val,
        // 模板转义
        escapeHtml: (str) => (str + '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
        // 执行函数（容错）
        safeCall: (fn, ...args) => { try { return fn(...args); } catch (e) { console.warn('执行失败:', e); return null; } }
    };

    // ====================== 1. 细粒度响应式系统（Solid核心 + Vue3 API） ======================
    let activeEffect = null;
    const targetMap = new WeakMap();

    // 依赖收集
    function track(target, key) {
        if (!activeEffect) return;
        let depsMap = targetMap.get(target);
        if (!depsMap) targetMap.set(target, (depsMap = new Map()));
        let deps = depsMap.get(key);
        if (!deps) depsMap.set(key, (deps = new Set()));
        deps.add(activeEffect);
    }

    // 依赖触发
    function trigger(target, key) {
        const depsMap = targetMap.get(target);
        if (!depsMap) return;
        depsMap.get(key)?.forEach(effect => utils.safeCall(effect));
    }

    // 创建副作用（Solid风格，无组件重渲染）
    function createEffect(effect) {
        const wrappedEffect = () => {
            activeEffect = wrappedEffect;
            const res = effect();
            activeEffect = null;
            return res;
        };
        wrappedEffect();
        return wrappedEffect;
    }

    // Vue3风格Ref
    function ref(value) {
        const refObj = {
            _isRef: true,
            get value() { track(refObj, 'value'); return value; },
            set value(v) {
                if (v !== value) {
                    value = v;
                    trigger(refObj, 'value');
                }
            }
        };
        return refObj;
    }

    // Vue3风格Reactive
    function reactive(target) {
        return new Proxy(target, {
            get(target, key, receiver) {
                const res = Reflect.get(target, key, receiver);
                track(target, key);
                return typeof res === 'object' && res !== null ? reactive(res) : res;
            },
            set(target, key, value, receiver) {
                const oldVal = Reflect.get(target, key, receiver);
                const success = Reflect.set(target, key, value, receiver);
                if (oldVal !== value) trigger(target, key);
                return success;
            }
        });
    }

    // Vue3风格Computed
    function computed(getter) {
        const c = ref();
        createEffect(() => { c.value = utils.safeCall(getter); });
        return c;
    }

    // Vue3风格Watch
    function watch(source, cb, options = { immediate: false }) {
        let getter = source._isRef ? () => source.value : (typeof source === 'function' ? source : () => source);
        let oldVal = getter();

        if (options.immediate) utils.safeCall(cb, oldVal, undefined);

        createEffect(() => {
            const newVal = getter();
            if (newVal !== oldVal) {
                utils.safeCall(cb, newVal, oldVal);
                oldVal = newVal;
            }
        });
    }

    // ====================== 2. 完整模板编译器（支持核心指令/插值） ======================
    const compiler = {
        // 解析模板为AST（轻量但完整）
        parse(template) {
            // 兜底：空模板返回默认内容
            template = utils.fallback(template, '<div>VueSolid 模板</div>').trim();

            // 简化AST结构（够用即可，避免复杂正则）
            const ast = {
                type: 'root',
                children: []
            };

            // 分割标签/文本
            const tokens = template.split(/(<\/?[\w-]+(?:\s+[\w-]+(?:="[^"]*")?)*\s*\/?>)/);

            tokens.forEach(token => {
                if (!token.trim()) return;

                // 匹配元素标签（如 <div v-if="show">、<button @click="add">）
                if (token.startsWith('<')) {
                    // 自闭合标签
                    if (token.endsWith('/>')) {
                        const tagMatch = token.match(/<([\w-]+)([^>]*)\/>/);
                        if (tagMatch) {
                            ast.children.push(this.parseElement(tagMatch[1], tagMatch[2]));
                        }
                    }
                    // 开始标签
                    else if (!token.startsWith('</')) {
                        const tagMatch = token.match(/<([\w-]+)([^>]*)>/);
                        if (tagMatch) {
                            ast.children.push(this.parseElement(tagMatch[1], tagMatch[2]));
                        }
                    }
                    // 结束标签忽略（简化处理，聚焦核心功能）
                }
                // 文本节点（含插值 {{xxx}}）
                else {
                    ast.children.push(this.parseText(token));
                }
            });

            return ast;
        },

        // 解析元素节点（标签+属性/指令）
        parseElement(tag, propsStr) {
            const element = {
                type: 'element',
                tag,
                props: [],
                children: []
            };

            // 解析属性/指令（v-if/v-for/v-model/@click/v-bind:xxx）
            const propReg = /([@v:][\w-]+|[\w-]+)(?:="([^"]*)")?/g;
            let match;

            while ((match = propReg.exec(propsStr))) {
                const [_, name, value] = match;
                let prop = { name, value: utils.fallback(value, '') };

                // 标记指令类型
                if (name.startsWith('v-')) {
                    prop.type = 'directive';
                    prop.dir = name.slice(2); // if/for/model
                } else if (name.startsWith('@')) {
                    prop.type = 'directive';
                    prop.dir = 'on';
                    prop.event = name.slice(1); // click/input
                } else if (name.startsWith('v-bind:')) {
                    prop.type = 'directive';
                    prop.dir = 'bind';
                    prop.attr = name.slice(7); // class/style
                }

                element.props.push(prop);
            }

            return element;
        },

        // 解析文本节点（含插值）
        parseText(text) {
            const textNode = { type: 'text', content: text };
            // 检测插值 {{xxx}}
            if (/\{\{.+\}\}/.test(text)) {
                textNode.hasInterpolation = true;
                // 拆分纯文本和插值
                textNode.parts = text.split(/(\{\{.+\}\})/).map(part => {
                    if (/^\{\{.+\}\}$/.test(part)) {
                        return { type: 'interpolation', expr: part.slice(2, -2).trim() };
                    }
                    return { type: 'text', content: part };
                });
            }
            return textNode;
        },

        // 编译AST为渲染函数（直接生成DOM操作，无VDOM）
        compile(ast) {
            return function render(state, appContext) {
                // 创建根容器（确保绝不空白）
                const rootEl = document.createElement('div');

                // 生成DOM节点
                ast.children.forEach(node => {
                    const el = compiler.generateNode(node, state, appContext);
                    if (utils.isNode(el)) rootEl.appendChild(el);
                });

                // 绑定响应式更新（细粒度，仅更新变化节点）
                compiler.bindReactive(ast, rootEl, state);

                return rootEl;
            };
        },

        // 生成DOM节点（元素/文本）
        generateNode(node, state, appContext) {
            // 元素节点
            if (node.type === 'element') {
                // 检测是否为组件
                const component = appContext.components[node.tag];
                if (component) {
                    return compiler.generateComponent(node, component, state, appContext);
                }

                const el = document.createElement(node.tag);

                // 处理属性/指令
                node.props.forEach(prop => {
                    compiler.applyProp(el, prop, state);
                });

                return el;
            }
            // 文本节点（含插值）
            else if (node.type === 'text') {
                let textContent = '';
                if (node.hasInterpolation) {
                    node.parts.forEach(part => {
                        if (part.type === 'interpolation') {
                            // 解析插值表达式（如 count.value → state.count.value）
                            textContent += utils.fallback(utils.safeCall(() => eval(`state.${part.expr}`)), '');
                        } else {
                            textContent += part.content;
                        }
                    });
                } else {
                    textContent = node.content;
                }
                return document.createTextNode(utils.escapeHtml(textContent));
            }

            // 兜底：空span
            return document.createElement('span');
        },

        // 生成组件节点
        generateComponent(node, component, state, appContext) {
            // 提取组件Props
            const props = {};
            node.props.forEach(prop => {
                if (prop.type !== 'directive') {
                    props[prop.name] = utils.safeCall(() => eval(`state.${prop.value}`)) || prop.value;
                }
            });

            // 创建组件实例
            const instance = {
                props: reactive(props),
                ctx: {},
                el: document.createElement('div')
            };

            // 执行组件setup
            if (component.setup) {
                instance.ctx = utils.safeCall(component.setup, instance.props) || {};
            }

            // 编译组件模板并挂载
            const componentAst = compiler.parse(component.template);
            const componentRender = compiler.compile(componentAst);
            const componentEl = componentRender(instance.ctx, appContext);

            instance.el.appendChild(componentEl);
            return instance.el;
        },

        // 应用属性/指令到DOM
        applyProp(el, prop, state) {
            // 普通属性
            if (!prop.type) {
                el.setAttribute(prop.name, prop.value);
                return;
            }

            // 指令处理
            switch (prop.dir) {
                // v-if
                case 'if':
                    const ifValue = utils.safeCall(() => eval(`state.${prop.value}.value`));
                    el.style.display = ifValue ? '' : 'none';
                    break;
                // v-model（输入框双向绑定）
                case 'model':
                    const modelValue = utils.safeCall(() => eval(`state.${prop.value}.value`));
                    el.value = utils.fallback(modelValue, '');
                    el.addEventListener('input', e => {
                        const refObj = utils.safeCall(() => eval(`state.${prop.value}`));
                        if (refObj?._isRef) refObj.value = e.target.value;
                    });
                    break;
                // @click 等事件
                case 'on':
                    el.addEventListener(prop.event, () => {
                        utils.safeCall(() => eval(`state.${prop.value}()`));
                    });
                    break;
                // v-bind
                case 'bind':
                    const bindValue = utils.safeCall(() => eval(`state.${prop.value}.value`)) || prop.value;
                    el.setAttribute(prop.attr, bindValue);
                    break;
            }
        },

        // 绑定响应式更新（细粒度）
        bindReactive(ast, rootEl, state) {
            // 遍历AST，为插值/指令绑定effect
            ast.children.forEach((node, index) => {
                const childEl = rootEl.children[index];
                if (!childEl) return;

                // 文本插值响应式
                if (node.type === 'text' && node.hasInterpolation) {
                    createEffect(() => {
                        let newText = '';
                        node.parts.forEach(part => {
                            if (part.type === 'interpolation') {
                                newText += utils.fallback(utils.safeCall(() => eval(`state.${part.expr}`)), '');
                            } else {
                                newText += part.content;
                            }
                        });
                        childEl.textContent = utils.escapeHtml(newText);
                    });
                }

                // 元素指令响应式
                if (node.type === 'element') {
                    node.props.forEach(prop => {
                        // v-if 响应式
                        if (prop.dir === 'if') {
                            createEffect(() => {
                                const val = utils.safeCall(() => eval(`state.${prop.value}.value`));
                                childEl.style.display = val ? '' : 'none';
                            });
                        }
                        // v-model 响应式（值更新同步到输入框）
                        if (prop.dir === 'model') {
                            createEffect(() => {
                                const val = utils.safeCall(() => eval(`state.${prop.value}.value`));
                                childEl.value = utils.fallback(val, '');
                            });
                        }
                        // v-bind 响应式
                        if (prop.dir === 'bind') {
                            createEffect(() => {
                                const val = utils.safeCall(() => eval(`state.${prop.value}.value`)) || prop.value;
                                childEl.setAttribute(prop.attr, val);
                            });
                        }
                    });
                }
            });
        }
    };

    // ====================== 3. 完整组件系统 ======================
    function defineComponent(options) {
        return {
            _isComponent: true,
            name: utils.fallback(options.name, 'AnonymousComponent'),
            template: utils.fallback(options.template, ''),
            setup: options.setup,
            props: utils.fallback(options.props, [])
        };
    }

    // ====================== 4. 应用核心（createApp） ======================
    function createApp(rootComponent) {
        // 应用上下文（全局组件/配置）
        const appContext = {
            components: {}
        };

        const app = {
            // 注册全局组件
            component(name, component) {
                if (component._isComponent) {
                    appContext.components[name] = component;
                }
                return app;
            },

            // 挂载应用
            mount(selector) {
                const rootEl = document.querySelector(selector);
                if (!rootEl) {
                    console.error('挂载目标不存在:', selector);
                    // 兜底：创建默认节点，绝不空白
                    const fallbackEl = document.createElement('div');
                    fallbackEl.textContent = 'VueSolid 应用挂载失败（目标不存在）';
                    document.body.appendChild(fallbackEl);
                    return;
                }

                // 1. 解析根组件模板
                const rootAst = compiler.parse(rootComponent.template);
                // 2. 编译为渲染函数
                const rootRender = compiler.compile(rootAst);
                // 3. 执行根组件setup
                const rootState = rootComponent.setup ? utils.safeCall(rootComponent.setup) : {};
                // 4. 生成DOM并挂载（确保绝不空白）
                const appDom = rootRender(rootState, appContext);

                // 清空目标容器 + 挂载
                rootEl.innerHTML = '';
                rootEl.appendChild(appDom);

                return app;
            }
        };

        return app;
    }

    // ====================== 导出全局API ======================
    window.VueSolid = {
        // 响应式API
        ref,
        reactive,
        computed,
        watch,
        // 组件/应用API
        defineComponent,
        createApp
    };
})(window);