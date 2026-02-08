// 加载动画组件，全局单例，支持显示/隐藏
const loading = {
    // 实例
    instance: null,

    // 创建加载容器
    createContainer() {
        if (this.instance) return this.instance;

        const loading = document.createElement('div');
        loading.className = 'loading hidden';
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        loading.appendChild(spinner);
        document.body.appendChild(loading);

        this.instance = loading;
        return loading;
    },

    // 显示加载
    show() {
        const loading = this.createContainer();
        loading.classList.remove('hidden');
    },

    // 隐藏加载
    hide() {
        if (this.instance) {
            this.instance.classList.add('hidden');
        }
    },

    // 初始化
    init() { }
};