// CSRF Token处理模块，自动获取并维护Token
const csrf = {
    // 初始化：检查Token是否存在
    init() {
        if (!this.getToken()) {
            // 触发Token生成（发起一次GET请求）
            fetch('/api/user/info', { method: 'GET' }).catch(() => { });
        }
    },

    // 获取CSRF Token
    getToken() {
        const cookieArr = document.cookie.split('; ');
        for (let i = 0; i < cookieArr.length; i++) {
            const [key, value] = cookieArr[i].split('=');
            if (key === 'X-CSRF-Token') {
                return value;
            }
        }
        return '';
    }
};