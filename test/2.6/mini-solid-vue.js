(function (window) {
    'use strict';

    // ====================== 1. 响应式核心模块（扩展） ======================
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

        // 原有核心：createSignal（保留）
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

        // 原有核心：createEffect（保留）
        const createEffect = (fn) => {
            const effect = () => {
                pushEffect(effect);
                try { fn(); } catch (e) { console.error('[Effect Error]', e); } finally { popEffect(); }
            };
            effect._name = `effect_${Date.now()}`;
            effect();
            return effect;
        };

        // 原有核心：createMemo（保留）
        const createMemo = (fn) => {
            const [get, set] = createSignal();
            createEffect(() => set(fn()));
            return get;
        };

        // ====================== 新增响应式功能（Vue3 风格） ======================
        // 1.1 ref：基于 createSignal 封装，支持 .value 访问
        const ref = (initialValue) => {
            const [get, set] = createSignal(initialValue);
            const refObj = {
                get value() { return get(); },
                set value(v) { set(v); },
                __v_isRef: true // 标记为 ref 类型
            };
            // 兼容原有 createSignal 写法
            refObj[Symbol('raw')] = [get, set];
            return refObj;
        };

        // 1.2 reactive：对象响应式（递归监听属性）
        const reactive = (obj) => {
            if (typeof obj !== 'object' || obj === null) return obj;

            // 递归处理对象属性
            const proxy = new Proxy(obj, {
                get(target, key, receiver) {
                    const res = Reflect.get(target, key, receiver);
                    // 收集依赖（复用 createSignal 的依赖收集逻辑）
                    if (activeEffect) {
                        // 为每个属性创建独立的 signal（懒创建）
                        if (!target[`__signal_${key}`]) {
                            const [get, set] = createSignal(res);
                            target[`__signal_${key}`] = { get, set };
                        }
                        target[`__signal_${key}`].get(); // 触发依赖收集
                    }
                    // 深层响应式
                    return typeof res === 'object' && res !== null ? reactive(res) : res;
                },
                set(target, key, value, receiver) {
                    const oldVal = Reflect.get(target, key, receiver);
                    if (Object.is(oldVal, value)) return true;

                    // 更新 signal 并触发依赖
                    if (target[`__signal_${key}`]) {
                        target[`__signal_${key}`].set(value);
                    } else {
                        const [get, set] = createSignal(value);
                        target[`__signal_${key}`] = { get, set };
                    }
                    return Reflect.set(target, key, value, receiver);
                }
            });
            proxy.__v_isReactive = true;
            return proxy;
        };

        // 1.3 computed：基于 createMemo 封装，支持 .value 访问
        const computed = (getter) => {
            const get = createMemo(getter);
            return {
                get value() { return get(); },
                __v_isReadonly: true,
                __v_isRef: true
            };
        };

        // 1.4 watch：监听响应式数据变化（Vue3 风格）
        const watch = (source, callback, options = {}) => {
            let oldValue;
            let newValue;

            // 解析监听源（signal/ref/reactive）
            const getSourceValue = () => {
                if (typeof source === 'function') return source();
                if (source.__v_isRef) return source.value;
                if (source.__v_isReactive) return { ...source }; // 浅拷贝响应式对象
                if (Array.isArray(source) && source[0] && typeof source[0] === 'function') return source[0](); // 兼容 createSignal
                return source;
            };

            // 执行监听逻辑
            const effect = createEffect(() => {
                newValue = getSourceValue();
                if (options.immediate) {
                    callback(newValue, oldValue);
                } else if (oldValue !== undefined) {
                    callback(newValue, oldValue);
                }
                oldValue = newValue;
            });

            // 返回停止监听函数
            return () => {
                const idx = effectStack.indexOf(effect);
                if (idx > -1) effectStack.splice(idx, 1);
                activeEffect = effectStack.at(-1) || null;
            };
        };

        // 1.5 类型判断工具
        const isRef = (val) => !!val?.__v_isRef;
        const isReactive = (val) => !!val?.__v_isReactive;

        return {
            // 原有 API（保留）
            createSignal, createEffect, createMemo,
            // 新增 Vue3 风格 API
            ref, reactive, computed, watch, isRef, isReactive
        };
    })();

    // ====================== 2. 工具模块（扩展） ======================
    const UtilsModule = (() => {
        // 原有工具：getRealValue（优化）
        const getRealValue = (value) => {
            let realVal = value;
            // 解包 ref
            if (ReactiveModule.isRef(realVal)) realVal = realVal.value;
            // 执行函数（兼容 createSignal 的 get 函数）
            if (typeof realVal === 'function') realVal = realVal();
            // 空值处理
            if ([null, undefined].includes(realVal)) return '';
            if (typeof realVal === 'boolean') return realVal;
            if (typeof realVal === 'number' && (Number.isNaN(realVal) || !Number.isFinite(realVal))) return '';
            return realVal;
        };

        // 原有工具：execEvent（优化）
        const execEvent = (ctx, expr, $event) => {
            try {
                if (!expr) return;
                // 解析事件修饰符（新增）
                const { pureExpr, modifiers } = parseEventModifiers(expr);
                // 执行修饰符逻辑
                modifiers.forEach(mod => {
                    switch (mod) {
                        case 'stop': $event.stopPropagation(); break;
                        case 'prevent': $event.preventDefault(); break;
                        case 'once': $event.target.removeEventListener($event.type, arguments.callee); break;
                        case 'self': if ($event.target !== $event.currentTarget) return; break;
                    }
                });
                // 执行事件表达式
                const keys = [...Object.keys(ctx), '$event'];
                const values = [...Object.values(ctx).map(v => getRealValue(v)), $event];
                const result = new Function(...keys, `return ${pureExpr}`)(...values);
                if (typeof result === 'function') result();
            } catch (err) {
                console.warn('[Event Error]', err, 'Expr:', expr);
            }
        };

        // 原有工具：toast（保留）
        const toast = (msg) => {
            document.querySelectorAll('.mini-toast').forEach(el => el.remove());
            const tip = document.createElement('div');
            tip.className = 'mini-toast';
            tip.textContent = msg;
            tip.style.cssText = `position:fixed;top:20px;right:20px;background:#165DFF;color:#fff;padding:12px 20px;border-radius:6px;z-index:9999;transition:opacity 0.3s;`;
            document.body.appendChild(tip);
            setTimeout(() => { tip.style.opacity = '0'; setTimeout(() => tip.remove(), 300); }, 1500);
        };

        // 原有工具：cloneNode（保留）
        const cloneNode = (el) => el?.cloneNode(true) || null;

        // 原有工具：parseVFor（优化）
        const parseVFor = (str) => {
            // 支持 Vue3 (item, index) in list 写法
            const reg = /^\s*\(?([$\w]+)(?:\s*,\s*([$\w]+))?\)?\s+in\s+([$\w]+)\s*$/;
            const match = str.match(reg);
            if (!match) return null;
            return { itemKey: match[1], indexKey: match[2] || '$index', listKey: match[3] };
        };

        // ====================== 新增工具函数 ======================
        // 2.1 解析事件修饰符（.stop/.prevent/.once/.self）
        const parseEventModifiers = (expr) => {
            const modifiers = [];
            let pureExpr = expr;
            const modReg = /\.(stop|prevent|once|self)$/g;
            let match;
            while ((match = modReg.exec(expr))) {
                modifiers.push(match[1]);
                pureExpr = pureExpr.replace(`.${match[1]}`, '');
            }
            return { pureExpr: pureExpr.trim(), modifiers };
        };

        // 2.2 解析复杂 :class（支持数组/对象）
        const parseVueClass = (classVal, ctx) => {
            const val = getRealValue(ctx[classVal]);
            let className = '';
            // 数组类型：['class1', { class2: true }]
            if (Array.isArray(val)) {
                val.forEach(item => {
                    className += `${parseVueClassItem(item, ctx)} `;
                });
            }
            // 对象类型：{ class1: true, class2: false }
            else if (typeof val === 'object' && val !== null && !ReactiveModule.isRef(val)) {
                Object.keys(val).forEach(key => {
                    if (getRealValue(val[key])) className += `${key} `;
                });
            }
            // 字符串类型
            else {
                className += val;
            }
            return className.trim();
        };
        // 辅助：解析单个 class 项
        const parseVueClassItem = (item, ctx) => {
            if (typeof item === 'object' && item !== null) {
                return Object.keys(item).filter(key => getRealValue(item[key])).join(' ');
            }
            return getRealValue(item);
        };

        // 2.3 解析复杂 :style（支持数组/对象/驼峰转横线）
        const parseVueStyle = (styleVal, ctx) => {
            const val = getRealValue(ctx[styleVal]);
            let cssText = '';
            // 数组类型：[{ color: 'red' }, { fontSize: '18px' }]
            if (Array.isArray(val)) {
                val.forEach(item => {
                    cssText += parseVueStyleItem(item, ctx);
                });
            }
            // 对象类型：{ color: 'red', fontSize: '18px' }
            else if (typeof val === 'object' && val !== null && !ReactiveModule.isRef(val)) {
                Object.keys(val).forEach(prop => {
                    const styleVal = getRealValue(val[prop]);
                    // 驼峰转横线：fontSize → font-size
                    const cssProp = prop.replace(/([A-Z])/g, '-$1').toLowerCase();
                    cssText += `${cssProp}: ${styleVal};`;
                });
            }
            // 字符串类型
            else {
                cssText += val;
            }
            return cssText;
        };
        // 辅助：解析单个 style 项
        const parseVueStyleItem = (item, ctx) => {
            if (typeof item === 'object' && item !== null) {
                let css = '';
                Object.keys(item).forEach(prop => {
                    const val = getRealValue(item[prop]);
                    const cssProp = prop.replace(/([A-Z])/g, '-$1').toLowerCase();
                    css += `${cssProp}: ${val};`;
                });
                return css;
            }
            return getRealValue(item);
        };

        // 2.4 nextTick：微任务执行（Vue3 风格）
        const nextTick = (fn) => {
            return Promise.resolve().then(fn);
        };

        // 2.5 解包响应式数据（ref/reactive）
        const unwrapRef = (val) => {
            if (ReactiveModule.isRef(val)) return val.value;
            if (ReactiveModule.isReactive(val)) return { ...val };
            return val;
        };

        return {
            // 原有工具（保留/优化）
            getRealValue, execEvent, toast, cloneNode, parseVFor,
            // 新增工具
            parseEventModifiers, parseVueClass, parseVueStyle, nextTick, unwrapRef
        };
    })();

    // ====================== 3. 模板编译器（扩展） ======================
    const CompilerModule = (() => {
        const {
            getRealValue, execEvent, cloneNode, parseVFor,
            parseEventModifiers, parseVueClass, parseVueStyle, unwrapRef
        } = UtilsModule;
        const INTERPOLATION_REG = /{{([\s\S]+?)}}/g;

        // 原有逻辑：renderInterpolation（优化）
        const renderInterpolation = (node, ctx, watchers) => {
            if (node.nodeType !== Node.TEXT_NODE) return;
            const originText = node.textContent;
            if (!originText.includes('{{')) return;

            const updateText = () => {
                node.textContent = originText.replace(INTERPOLATION_REG, (_, exp) => {
                    try {
                        const expression = exp.trim();
                        // 支持过滤器：{{ msg | uppercase }}
                        const [exprMain, filterName] = expression.split('|').map(e => e.trim());
                        const keys = Object.keys(ctx);
                        const values = keys.map(key => unwrapRef(ctx[key]));
                        let res = new Function(...keys, `return ${exprMain}`)(...values);
                        // 执行过滤器
                        if (filterName && ctx[filterName]) {
                            res = ctx[filterName](res);
                        }
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

        // ====================== 新增编译逻辑 ======================
        // 3.1 编译 v-if/v-else/v-else-if
        const compileCondition = (el, ctx, watchers) => {
            const vIfAttr = el.getAttribute('v-if');
            const vElseAttr = el.hasAttribute('v-else');
            const vElseIfAttr = el.getAttribute('v-else-if');

            if (!vIfAttr && !vElseAttr && !vElseIfAttr) return;

            // 收集条件节点链
            const conditionNodes = [el];
            let nextEl = el.nextElementSibling;
            while (nextEl) {
                if (nextEl.hasAttribute('v-else') || nextEl.hasAttribute('v-else-if')) {
                    conditionNodes.push(nextEl);
                    nextEl = nextEl.nextElementSibling;
                } else {
                    break;
                }
            }

            // 创建占位符
            const placeholder = document.createComment('v-if block');
            el.parentNode.replaceChild(placeholder, el);
            conditionNodes.slice(1).forEach(node => node.remove());

            // 渲染条件节点
            const renderCondition = () => {
                // 清空现有节点
                Array.from(placeholder.parentNode.childNodes).forEach(node => {
                    if (node !== placeholder) node.remove();
                });

                // 判断显示哪个节点
                let targetNode = null;
                for (const node of conditionNodes) {
                    const ifExpr = node.getAttribute('v-if');
                    const elseIfExpr = node.getAttribute('v-else-if');
                    if (ifExpr) {
                        const keys = Object.keys(ctx);
                        const values = keys.map(key => unwrapRef(ctx[key]));
                        const isTrue = new Function(...keys, `return ${ifExpr.trim()}`)(...values);
                        if (isTrue) {
                            targetNode = node;
                            break;
                        }
                    } else if (elseIfExpr) {
                        const keys = Object.keys(ctx);
                        const values = keys.map(key => unwrapRef(ctx[key]));
                        const isTrue = new Function(...keys, `return ${elseIfExpr.trim()}`)(...values);
                        if (isTrue) {
                            targetNode = node;
                            break;
                        }
                    } else if (vElseAttr) {
                        targetNode = node;
                        break;
                    }
                }

                // 渲染目标节点
                if (targetNode) {
                    const clone = cloneNode(targetNode);
                    const childWatchers = [];
                    compileNode(clone, ctx, childWatchers);
                    placeholder.parentNode.insertBefore(clone, placeholder);
                    watchers.push(...childWatchers);
                }
            };

            renderCondition();
            watchers.push(renderCondition);
            return true; // 标记已处理条件逻辑
        };

        // 3.2 编译 v-model（支持 input/checkbox/radio/select）
        const compileVModel = (el, ctx, watchers) => {
            const vModelAttr = el.getAttribute('v-model');
            if (!vModelAttr) return;

            const modelKey = vModelAttr.trim();
            const elType = el.tagName.toLowerCase();
            const inputType = el.type || 'text';

            // 更新视图逻辑
            const updateModel = () => {
                const val = unwrapRef(ctx[modelKey]);
                if (elType === 'input') {
                    if (inputType === 'checkbox') {
                        el.checked = Array.isArray(val) ? val.includes(el.value) : !!val;
                    } else if (inputType === 'radio') {
                        el.checked = val === el.value;
                    } else {
                        el.value = getRealValue(val);
                    }
                } else if (elType === 'select') {
                    el.value = getRealValue(val);
                } else if (elType === 'textarea') {
                    el.value = getRealValue(val);
                }
            };

            // 绑定输入事件
            const handleInput = (e) => {
                const refVal = ctx[modelKey];
                let newValue;
                if (elType === 'input') {
                    if (inputType === 'checkbox') {
                        newValue = Array.isArray(unwrapRef(refVal))
                            ? el.checked
                                ? [...unwrapRef(refVal), el.value]
                                : unwrapRef(refVal).filter(v => v !== el.value)
                            : el.checked;
                    } else if (inputType === 'radio') {
                        newValue = el.value;
                    } else {
                        newValue = e.target.value;
                    }
                } else if (elType === 'select' || elType === 'textarea') {
                    newValue = e.target.value;
                }

                // 更新响应式数据
                if (ReactiveModule.isRef(refVal)) {
                    refVal.value = newValue;
                } else if (Array.isArray(refVal) && typeof refVal[0] === 'function') {
                    refVal[1](newValue); // 兼容 createSignal
                } else if (ReactiveModule.isReactive(refVal)) {
                    // 暂不支持对象深层 v-model，可扩展
                }
            };

            // 初始化 + 监听
            updateModel();
            watchers.push(updateModel);
            el.addEventListener('input', handleInput);
            el.removeAttribute('v-model');
        };

        // 原有核心：compileNode（扩展）
        const compileNode = (el, ctx, watchers) => {
            if (!el) return;

            // 优先处理条件渲染（v-if/v-else）
            if (compileCondition(el, ctx, watchers)) return;

            if (el.nodeType === Node.TEXT_NODE) {
                renderInterpolation(el, ctx, watchers);
                return;
            }
            if (el.nodeType !== Node.ELEMENT_NODE) return;

            // 1. 事件绑定（支持修饰符）
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

            // 2. v-html（原有）
            const vHtmlAttr = el.getAttribute('v-html');
            if (vHtmlAttr) {
                const updateHtml = () => { el.innerHTML = getRealValue(ctx[vHtmlAttr]); };
                updateHtml();
                watchers.push(updateHtml);
                el.removeAttribute('v-html');
            }

            // 3. v-model（新增）
            compileVModel(el, ctx, watchers);

            // 4. :class/:style（扩展支持复杂写法）
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
                    if (prop === 'class') {
                        el.className = parseVueClass(key, ctx); // 新增：复杂 class
                    } else if (prop === 'style') {
                        el.style.cssText = parseVueStyle(key, ctx); // 新增：复杂 style
                    } else {
                        const val = getRealValue(ctx[key]) ?? '';
                        el.setAttribute(prop, val);
                    }
                };
                updateBind();
                watchers.push(updateBind);
            });

            // 5. v-for（优化：支持 key 属性）
            const vForAttr = el.getAttribute('v-for');
            if (vForAttr) {
                const parent = el.parentNode;
                const vForConf = parseVFor(vForAttr);
                if (vForConf && parent) {
                    const tpl = cloneNode(el);
                    tpl?.removeAttribute('v-for');
                    // 提取 key 属性（优化渲染）
                    const keyAttr = tpl?.getAttribute('key') || '$index';
                    tpl?.removeAttribute('key');
                    el.remove();

                    const renderList = () => {
                        try {
                            parent.querySelectorAll('[data-msv-item]').forEach(n => n.remove());
                            const listData = Array.isArray(unwrapRef(ctx[vForConf.listKey]))
                                ? unwrapRef(ctx[vForConf.listKey])
                                : [];
                            listData.forEach((item, index) => {
                                const node = cloneNode(tpl);
                                if (node) {
                                    node.setAttribute('data-msv-item', '');
                                    // 绑定 key 属性
                                    const itemKey = item[keyAttr] || index;
                                    node.setAttribute('data-v-key', itemKey);

                                    const childCtx = { ...ctx, [vForConf.itemKey]: item, [vForConf.indexKey]: index };
                                    const childWatchers = [];
                                    compileNode(node, childCtx, childWatchers);
                                    parent.appendChild(node);
                                    watchers.push(...childWatchers);
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

        // 原有核心：compile（保留）
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

    // ====================== 4. 组件系统（扩展） ======================
    const ComponentModule = (() => {
        const { createEffect } = ReactiveModule;
        const { compile } = CompilerModule;
        const { nextTick } = UtilsModule;
        const componentMap = new Map();
        // 全局配置
        const globalConfig = {
            globalProperties: {}, // 全局属性
            errorHandler: (err) => console.error('[Global Error]', err)
        };

        // 生命周期钩子存储
        const lifecycleHooks = {
            mounted: [],
            updated: [],
            unmounted: []
        };

        // 原有核心：defineComponent（扩展 props 校验）
        const defineComponent = (name, options) => {
            // 标准化 props 配置
            const normalizedProps = {};
            if (options.props) {
                Object.keys(options.props).forEach(key => {
                    const prop = options.props[key];
                    normalizedProps[key] = {
                        type: prop.type || String,
                        default: prop.default || undefined,
                        required: prop.required || false
                    };
                });
            }

            // 标准化组件选项
            const normalizedOptions = {
                props: normalizedProps,
                setup: options.setup || (() => ({})),
                template: options.template || '',
                // 新增：过滤器
                filters: options.filters || {}
            };
            componentMap.set(name.toLowerCase(), normalizedOptions);
        };

        // 原有核心：renderComponent（扩展生命周期/错误捕获）
        const renderComponent = (name, props = {}, container) => {
            if (!container) throw new Error('Container not found');
            const option = componentMap.get(name.toLowerCase());
            if (!option) throw new Error(`Component ${name} not registered`);

            try {
                container.innerHTML = '';
                // 1. Props 校验
                const normalizedProps = {};
                Object.keys(option.props).forEach(key => {
                    const propConf = option.props[key];
                    // 必传校验
                    if (propConf.required && !props.hasOwnProperty(key)) {
                        throw new Error(`Prop "${key}" is required for component "${name}"`);
                    }
                    // 默认值
                    normalizedProps[key] = props[key] ?? propConf.default;
                    // 类型校验
                    if (propConf.type && normalizedProps[key] !== undefined) {
                        const isTypeValid = propConf.type === Array
                            ? Array.isArray(normalizedProps[key])
                            : normalizedProps[key] instanceof propConf.type || typeof normalizedProps[key] === propConf.type.name.toLowerCase();
                        if (!isTypeValid) {
                            console.warn(`Prop "${key}" should be of type "${propConf.type.name}" for component "${name}"`);
                        }
                    }
                });

                // 2. 执行 setup（注入生命周期）
                const lifecycleCtx = {
                    onMounted: (fn) => lifecycleHooks.mounted.push(fn),
                    onUpdated: (fn) => lifecycleHooks.updated.push(fn),
                    onUnmounted: (fn) => lifecycleHooks.unmounted.push(fn)
                };
                const setupCtx = option.setup({ ...normalizedProps }, lifecycleCtx) || {};

                // 3. 合并上下文（全局属性 + props + setup + 过滤器）
                const renderCtx = {
                    ...globalConfig.globalProperties,
                    ...normalizedProps,
                    ...setupCtx,
                    ...option.filters
                };

                // 4. 编译模板
                const { root, watchers } = compile(option.template, renderCtx);
                container.appendChild(root);

                // 5. 响应式驱动
                createEffect(() => {
                    watchers.forEach(w => { try { w(); } catch (e) { globalConfig.errorHandler(e); } });
                    // 触发 updated 生命周期
                    lifecycleHooks.updated.forEach(fn => fn());
                });

                // 6. 触发 mounted 生命周期
                nextTick(() => {
                    lifecycleHooks.mounted.forEach(fn => fn());
                });

                // 7. 绑定卸载逻辑
                container.dataset.msvComponent = name;
                container.addEventListener('unmount', () => {
                    lifecycleHooks.unmounted.forEach(fn => fn());
                    container.innerHTML = '';
                });

            } catch (err) {
                globalConfig.errorHandler(err);
            }
        };

        // 原有核心：createApp（扩展全局配置）
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
                },
                // 新增：全局配置
                config: globalConfig,
                // 新增：全局属性
                provide(key, value) {
                    globalConfig.globalProperties[key] = value;
                    return this;
                }
            };
        };

        return { defineComponent, renderComponent, createApp };
    })();

    // 全局挂载（扩展 Vue3 风格 API）
    const Framework = {
        // 原有 API
        ...ReactiveModule,
        ...ComponentModule,
        utils: UtilsModule,
        // 新增：Vue3 风格别名
        ref: ReactiveModule.ref,
        reactive: ReactiveModule.reactive,
        computed: ReactiveModule.computed,
        watch: ReactiveModule.watch,
        nextTick: UtilsModule.nextTick
    };
    if (typeof window !== 'undefined') {
        window.MiniSolidVue = Framework;
        window.Vue = Framework; // 兼容 Vue 全局变量
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = Framework;
})(window);