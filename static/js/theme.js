// // 主题切换模块，支持亮色/暗色，状态持久化（终极修复版）
// const theme = {
//     // 主题类型
//     themes: {
//         light: 'light',
//         dark: 'dark'
//     },
//     isToggling: false,
//     // 本地存储兜底（解决store依赖）
//     _store: {
//         get(key, defaultValue = '') {
//             try {
//                 const value = localStorage.getItem(key);
//                 return value ? JSON.parse(value) : defaultValue;
//             } catch (err) {
//                 return defaultValue;
//             }
//         },
//         set(key, value) {
//             try {
//                 localStorage.setItem(key, JSON.stringify(value));
//             } catch (err) {
//                 console.error(`存储${key}失败：`, err);
//             }
//         }
//     },

//     // 初始化
//     init() {
//         try {
//             // 读取保存的主题
//             const savedTheme = window.store?.get
//                 ? window.store.get('theme', this.themes.light)
//                 : this._store.get('theme', this.themes.light);

//             // 应用主题
//             this.switch(savedTheme);

//             // 绑定切换按钮（核心：用bind固定this指向）
//             const toggleBtn = document.getElementById('theme-toggle');
//             if (toggleBtn) {
//                 // 修复：用bind绑定this到theme对象，避免指向丢失
//                 // toggleBtn.onclick = this.toggle.bind(this);
//                 // 更新按钮文本
//                 this.updateBtnText(toggleBtn);
//             }
//         } catch (err) {
//             console.warn("主题初始化失败：", err);
//             this.switch(this.themes.light);
//         }
//     },

//     // 更新按钮文本
//     updateBtnText(toggleBtn) {
//         const appEl = document.getElementById('app');
//         if (!appEl || !toggleBtn) return;
//         const isDark = appEl.classList.contains(this.themes.dark);
//         toggleBtn.textContent = isDark ? '☀️ 浅色模式' : '🌙 深色模式';
//     },

//     // 切换主题（核心函数，this已绑定）
//     toggle() {
//         try {
//             if (this.isToggling) return;
//             this.isToggling = true;
//             const appEl = document.getElementById('app');
//             if (!appEl) {
//                 console.warn("未找到#app元素");
//                 this.isToggling = false;
//                 return;
//             }

//             // 这里的this已经绑定到theme对象，不会undefined
//             const currentTheme = appEl.classList.contains(this.themes.dark)
//                 ? this.themes.light
//                 : this.themes.dark;
//             // alert(`切换到${currentTheme}模式`);
//             this.switch(currentTheme);
//             // alert(`切换到${currentTheme}模式成功`);
//             // 更新按钮文本
//             // const toggleBtn = document.getElementById('theme-toggle');
//             // this.updateBtnText(toggleBtn);
//         } catch (err) {
//             console.error("❌ 主题切换失败：", err);
//         }
//         // finally {
//         //     // alert("❌ 主题切换");
//         //     this.isToggling = false;
//         // }
//     },

//     // 切换到指定主题
//     switch(themeName) {
//         // 校验主题合法性
//         const validThemes = Object.values(this.themes);
//         if (!validThemes.includes(themeName)) {
//             themeName = this.themes.light;
//         }

//         // 应用主题类
//         const appEl = document.getElementById('app');
//         if (appEl) {
//             validThemes.forEach(t => appEl.classList.remove(t));
//             appEl.classList.add(themeName);
//         }

//         // 保存主题
//         if (window.store?.set) {
//             window.store.set('theme', themeName);
//         } else {
//             this._store.set('theme', themeName);
//         }

//         // 设置meta主题色
//         let metaEl = document.querySelector('meta[name="theme-color"]');
//         if (!metaEl) {
//             metaEl = document.createElement('meta');
//             metaEl.name = 'theme-color';
//             document.head.appendChild(metaEl);
//         }
//         metaEl.setAttribute('content', themeName === this.themes.dark ? '#1f2125' : '#f5f7fa');
//     }
// };

// // 页面加载后初始化（适配动态页面）
// // document.addEventListener('DOMContentLoaded', () => theme.init());
// // 兜底：动态页面延迟初始化
// // setTimeout(() => theme.init(), 500);
// 主题切换模块，支持亮色/暗色，状态持久化
// 主题切换模块（修复不切换问题）
const theme = {
    // 主题类型
    themes: {
        light: 'light',
        dark: 'dark'
    },

    // 初始化：加载保存的主题（加DOM校验+异常捕获）
    init() {
        try {
            // 先校验#app元素是否存在
            const appEl = document.getElementById('app');
            if (!appEl) {
                console.warn("❌ 未找到#app元素，主题初始化失败");
                return;
            }

            // 兼容store不存在的情况
            const savedTheme = window.store?.get
                ? store.get('theme', this.themes.light)
                : localStorage.getItem('theme') || this.themes.light;

            this.switch(savedTheme);
            console.log("✅ 主题初始化成功，当前主题：", savedTheme);
        } catch (err) {
            console.error("❌ 主题初始化失败：", err);
            // 兜底：使用浅色主题
            this.switch(this.themes.light);
        }
    },

    // 切换主题（加防抖+DOM校验+this兜底）
    toggle() {
        // 防抖：300ms内只执行一次（避免重复点击）
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => {
            try {
                const appEl = document.getElementById('app');
                if (!appEl) {
                    console.warn("❌ 未找到#app元素，无法切换主题");
                    return;
                }

                // this兜底：防止指向丢失
                const self = this || window.theme;
                const currentTheme = appEl.classList.contains(self.themes.dark)
                    ? self.themes.light
                    : self.themes.dark;

                self.switch(currentTheme);
                console.log("✅ 主题切换完成：", currentTheme);
            } catch (err) {
                console.error("❌ 主题切换失败：", err);
            }
        }, 300);
    },

    // 切换到指定主题（加全量校验）
    switch(themeName) {
        try {
            // 1. 校验主题合法性
            const validThemes = Object.values(this.themes);
            if (!validThemes.includes(themeName)) {
                themeName = this.themes.light;
            }

            // 2. 校验#app元素
            const appEl = document.getElementById('app');
            if (!appEl) return;

            // 3. 安全切换主题类
            appEl.classList.remove(...validThemes);
            appEl.classList.add(themeName);

            // 4. 保存主题（兼容store/localStorage）
            if (window.store?.set) {
                store.set('theme', themeName);
            } else {
                localStorage.setItem('theme', themeName);
            }

            // 5. 同步meta主题色（加元素校验）
            let metaEl = document.querySelector('meta[name="theme-color"]');
            if (!metaEl) {
                // 自动创建meta元素（避免不存在）
                metaEl = document.createElement('meta');
                metaEl.name = 'theme-color';
                document.head.appendChild(metaEl);
            }
            metaEl.setAttribute('content', themeName === this.themes.dark ? '#1f2125' : '#f5f7fa');
        } catch (err) {
            console.error("❌ 设置主题失败：", err);
        }
    },

    // 防抖计时器（初始化）
    debounceTimer: null
};

// ========== 关键：确保DOM加载完成后再绑定事件+初始化 ==========
// document.addEventListener('DOMContentLoaded', function () {
//     // 1. 初始化主题
//     theme.init();

//     // 2. 绑定.theme-switch点击事件（防重复绑定）
//     const switchEl = document.querySelector('.theme-switch');
//     if (switchEl) {
//         // 先移除原有事件，避免重复绑定
//         switchEl.removeEventListener('click', theme.toggle.bind(theme));
//         // 绑定事件（固定this指向）
//         switchEl.addEventListener('click', theme.toggle.bind(theme));
//         console.log("✅ .theme-switch 事件绑定成功");
//     } else {
//         console.warn("❌ 未找到.theme-switch元素，事件绑定失败");
//     }
// });

// 全局挂载（兜底）
window.theme = theme;