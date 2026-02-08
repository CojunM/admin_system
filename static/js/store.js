// 前端本地状态管理，基于LocalStorage，封装增删改查
const store = {
    // 前缀，避免键名冲突
    prefix: 'admin_system_',

    // 初始化：检查LocalStorage可用性
    init() {
        if (!this.isSupport()) {
            notify.error('您的浏览器不支持LocalStorage，部分功能将无法使用');
        }
    },

    // 检查LocalStorage是否可用
    isSupport() {
        try {
            const key = this.prefix + 'test';
            window.localStorage.setItem(key, 'test');
            window.localStorage.removeItem(key);
            return true;
        } catch (e) {
            return false;
        }
    },

    // 获取值
    get(key, defaultValue = null) {
        if (!this.isSupport()) return defaultValue;
        const value = window.localStorage.getItem(this.prefix + key);
        try {
            return value ? JSON.parse(value) : defaultValue;
        } catch (e) {
            return value || defaultValue;
        }
    },

    // 设置值
    set(key, value) {
        if (!this.isSupport()) return false;
        window.localStorage.setItem(this.prefix + key, JSON.stringify(value));
        return true;
    },

    // 删除值
    remove(key) {
        if (!this.isSupport()) return false;
        window.localStorage.removeItem(this.prefix + key);
        return true;
    },

    // 清空所有值（当前前缀）
    clear() {
        if (!this.isSupport()) return false;
        for (let key in window.localStorage) {
            if (key.startsWith(this.prefix)) {
                window.localStorage.removeItem(key);
            }
        }
        return true;
    }
};