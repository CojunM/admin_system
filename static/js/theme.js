// 主题切换模块，支持亮色/暗色，状态持久化
const theme = {
    // 主题类型
    themes: {
        light: 'light',
        dark: 'dark'
    },

    // 初始化：加载保存的主题
    init() {
        const savedTheme = store.get('theme', this.themes.light);
        this.switch(savedTheme);
    },

    // 切换主题
    toggle() {
        const currentTheme = document.getElementById('app').classList.contains(this.themes.dark)
            ? this.themes.light
            : this.themes.dark;
        this.switch(currentTheme);
    },

    // 切换到指定主题
    switch(themeName) {
        const appEl = document.getElementById('app');
        // 移除所有主题类，添加当前主题
        Object.values(this.themes).forEach(theme => {
            appEl.classList.remove(theme);
        });
        appEl.classList.add(themeName);
        // 保存主题到本地
        store.set('theme', themeName);
        // 同步页面标题栏样式（可选）
        document.querySelector('meta[name="theme-color"]').setAttribute('content', themeName === this.themes.dark ? '#1f2125' : '#f5f7fa');
    }
};