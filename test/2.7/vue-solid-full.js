// VueSolid 修复选择器错误版 - 解决[@click]无效选择器问题
; (function (window) {
    // ====================== 极简核心工具函数 ======================
    const utils = {
        // 直接获取ref对象/值（极简逻辑，避免解析错误）
        getRef: (state, key) => {
            const refObj = state[key];
            // 确保是ref对象，否则返回空ref
            if (refObj && refObj._isRef) return refObj;
            // 兜底：创建临时ref（避免报错）
            const emptyRef = ref(0);
            return emptyRef;
        },
        getRefValue: (state, key) => utils.getRef(state, key).value,
        setRefValue: (state, key, val) => {
            const numVal = Number(val);
            if (!isNaN(numVal)) utils.getRef(state, key).value = numVal;
        },
        escapeHtml: (str) => typeof str === 'string'
            ? str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            : str,
        removeComments: (tpl) => tpl.replace(/<!--[\s\S]*?-->/g, '').trim(),
        // 新增：替换@click为v-on:click（合法属性名）
        normalizeDirectives: (tpl) => {
            return tpl.replace(/@(\w+)="([^"]*)"/g, 'v-on:$1="$2"');
        }
    };

    // ====================== 1. 极简响应式（核心） ======================
    let activeEffect = null;
    const targetMap = new WeakMap();

    function track(target) {
        if (activeEffect && target) {
            let deps = targetMap.get(target);
            if (!deps) targetMap.set(target, (deps = new Set()));
            deps.add(activeEffect);
        }
    }

    function trigger(target) {
        targetMap.get(target)?.forEach(effect => effect());
    }

    function effect(fn) {
        activeEffect = fn;
        fn();
        activeEffect = null;
        return fn;
    }

    function ref(initValue = 0) {
        const numInit = Number(initValue) || 0;
        const refObj = {
            _isRef: true,
            _value: numInit, // 真实存储值
            get value() {
                track(refObj); // 收集依赖
                return this._value;
            },
            set value(newVal) {
                const numNew = Number(newVal) || 0;
                if (numNew !== this._value) {
                    this._value = numNew;
                    trigger(refObj); // 触发更新
                }
            }
        };
        return refObj;
    }

    function computed(getter) {
        const c = ref();
        effect(() => { c.value = getter(); });
        return c;
    }

    function watch(refObj, cb) {
        let oldVal = refObj.value;
        effect(() => {
            const newVal = refObj.value;
            if (newVal !== oldVal) {
                cb(newVal, oldVal);
                oldVal = newVal;
            }
        });
    }

    // ====================== 2. 极简模板渲染（核心修复选择器） ======================
    function renderTemplate(tpl, state, el) {
        // 1. 清理注释 + 标准化指令（@click → v-on:click）
        tpl = utils.removeComments(tpl);
        tpl = utils.normalizeDirectives(tpl);
        el.innerHTML = tpl;

        // 2. 处理v-model（输入框双向绑定）
        el.querySelectorAll('[v-model]').forEach(input => {
            const key = input.getAttribute('v-model');
            const refObj = utils.getRef(state, key);

            // 初始值同步
            input.value = refObj.value;

            // 输入 → 更新ref
            input.addEventListener('input', () => {
                refObj.value = input.value;
            });

            // ref变化 → 更新输入框
            effect(() => {
                input.value = refObj.value;
            });
        });

        // 3. 处理v-on:click事件（修复选择器：用合法的[v-on:click]）
        el.querySelectorAll('[v-on:click]').forEach(btn => {
            const fnName = btn.getAttribute('v-on:click');
            btn.removeAttribute('v-on:click');
            btn.addEventListener('click', () => {
                if (typeof state[fnName] === 'function') state[fnName]();
            });
        });

        // 4. 处理v-if
        el.querySelectorAll('[v-if]').forEach(node => {
            const key = node.getAttribute('v-if');
            const refObj = utils.getRef(state, key);
            effect(() => {
                node.style.display = refObj.value ? '' : 'none';
            });
        });

        // 5. 处理v-bind:class
        el.querySelectorAll('[v-bind:class]').forEach(node => {
            const key = node.getAttribute('v-bind:class');
            const refObj = utils.getRef(state, key);
            effect(() => {
                node.className = refObj.value;
            });
        });

        // 6. 处理插值 {{xxx}}
        const interpolate = (node) => {
            if (node.nodeType === 3) { // 文本节点
                const text = node.textContent;
                if (/\{\{(.+?)\}\}/.test(text)) {
                    const expr = text.match(/\{\{(.+?)\}\}/)[1].trim();
                    // 解析count.value → [count, value]
                    const [refKey, prop] = expr.split('.');
                    effect(() => {
                        let val = '';
                        if (prop === 'value') {
                            val = utils.getRefValue(state, refKey);
                        } else {
                            val = state[expr]?.value || state[expr] || '';
                        }
                        node.textContent = text.replace(/\{\{(.+?)\}\}/, utils.escapeHtml(val));
                    });
                }
            }
            // 递归处理子节点
            if (node.childNodes) {
                node.childNodes.forEach(child => interpolate(child));
            }
        };
        interpolate(el);

        // 7. 处理组件（极简版）
        el.querySelectorAll('[is-component]').forEach(compEl => {
            const compName = compEl.getAttribute('is-component');
            const comp = state.$components[compName];
            if (!comp) return;

            // 提取Props
            const props = {};
            Array.from(compEl.attributes).forEach(attr => {
                if (attr.name !== 'is-component') {
                    const [refKey, prop] = attr.value.split('.');
                    props[attr.name] = prop === 'value'
                        ? utils.getRefValue(state, refKey)
                        : state[attr.value];
                }
            });

            // 组件setup
            const compState = comp.setup(props);
            compState.$components = state.$components;

            // 渲染组件
            const compRoot = document.createElement('div');
            renderTemplate(comp.template, compState, compRoot);

            // 替换组件节点
            compEl.parentNode.replaceChild(compRoot.firstChild, compEl);

            // Props同步更新
            Object.keys(props).forEach(prop => {
                const [refKey, propKey] = compEl.getAttribute(prop).split('.');
                const refObj = utils.getRef(state, refKey);
                effect(() => {
                    compState.props[prop] = propKey === 'value' ? refObj.value : refObj;
                    // 重新渲染组件
                    renderTemplate(comp.template, compState, compRoot);
                    compEl.parentNode.replaceChild(compRoot.firstChild, compEl.previousSibling);
                });
            });
        });
    }

    // ====================== 3. 组件/应用核心 ======================
    function defineComponent(options) {
        return {
            template: options.template,
            setup: options.setup
        };
    }

    function createApp(rootComp) {
        return {
            components: {},
            component(name, comp) {
                this.components[name] = comp;
                return this;
            },
            mount(selector) {
                const el = document.querySelector(selector);
                if (!el) return;

                // 根组件state
                const rootState = rootComp.setup();
                rootState.$components = this.components;

                // 渲染根组件
                renderTemplate(rootComp.template, rootState, el);
            }
        };
    }

    // ====================== 导出API ======================
    window.VueSolid = {
        ref, computed, watch,
        defineComponent, createApp
    };
})(window);