// 消息通知组件，支持成功/错误/警告/信息提示，自动消失
const notify = {
    // 通知类型
    types: {
        success: 'notify-success',
        error: 'notify-error',
        warning: 'notify-warning',
        info: 'notify-info'
    },

    // 显示通知
    show(type, message, duration = 3000) {
        // 创建通知元素
        const toast = document.createElement('div');
        toast.className = `notify-toast ${this.types[type] || this.types.info}`;
        toast.textContent = message;
        // 添加到页面
        document.body.appendChild(toast);
        // 自动消失
        setTimeout(() => {
            document.body.removeChild(toast);
        }, duration);
    },

    // 快捷方法
    success(message, duration) {
        this.show('success', message, duration);
    },

    error(message, duration) {
        this.show('error', message, duration);
    },

    warning(message, duration) {
        this.show('warning', message, duration);
    },

    info(message, duration) {
        this.show('info', message, duration);
    },

    // 初始化（全局样式已在base.css）
    init() { }
};