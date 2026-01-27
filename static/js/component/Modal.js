// 弹窗组件，支持普通弹窗、确认弹窗、自定义内容
const modal = {
    // 弹窗实例
    instance: null,

    // 创建弹窗容器
    createContainer() {
        if (this.instance) return this.instance;

        // 遮罩层
        const mask = document.createElement('div');
        mask.className = 'modal-mask';
        // 容器
        const container = document.createElement('div');
        container.className = 'modal-container';
        // 头部
        const header = document.createElement('div');
        header.className = 'modal-header';
        // 标题
        const title = document.createElement('div');
        title.className = 'modal-title';
        // 关闭按钮
        const close = document.createElement('div');
        close.className = 'modal-close';
        close.innerHTML = '&times;';
        // 内容
        const body = document.createElement('div');
        body.className = 'modal-body';
        // 底部
        const footer = document.createElement('div');
        footer.className = 'modal-footer';

        // 组装
        header.appendChild(title);
        header.appendChild(close);
        container.appendChild(header);
        container.appendChild(body);
        container.appendChild(footer);
        mask.appendChild(container);
        document.body.appendChild(mask);

        // 绑定关闭事件
        close.addEventListener('click', () => this.close());
        mask.addEventListener('click', e => {
            if (e.target === mask) this.close();
        });

        // 缓存实例
        this.instance = {
            mask,
            container,
            title,
            body,
            footer
        };

        return this.instance;
    },

    // 打开弹窗
    open(options = {}) {
        const instance = this.createContainer();
        const { title = '提示', content = '', width = '', footer = true, onConfirm = null, onCancel = null } = options;

        // 设置样式
        if (width) instance.container.style.width = width;
        // 设置标题
        instance.title.textContent = title;
        // 设置内容（支持HTML）
        instance.body.innerHTML = content;
        // 设置底部按钮
        instance.footer.innerHTML = '';
        if (footer) {
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'btn btn-default';
            cancelBtn.textContent = '取消';
            const confirmBtn = document.createElement('button');
            confirmBtn.className = 'btn btn-primary';
            confirmBtn.textContent = '确认';

            // 绑定事件
            cancelBtn.addEventListener('click', () => {
                if (typeof onCancel === 'function') onCancel();
                this.close();
            });
            confirmBtn.addEventListener('click', () => {
                if (typeof onConfirm === 'function') onConfirm();
                this.close();
            });

            instance.footer.appendChild(cancelBtn);
            instance.footer.appendChild(confirmBtn);
        }

        // 显示弹窗
        instance.mask.classList.remove('hidden');
    },

    // 确认弹窗（快捷方法）
    confirm(content, onConfirm, onCancel = null, title = '确认提示') {
        this.open({
            title,
            content,
            onConfirm,
            onCancel
        });
    },

    // 提示弹窗（无取消按钮）
    alert(content, onConfirm = null, title = '提示') {
        this.open({
            title,
            content,
            footer: false,
            onConfirm
        });
    },

    // 关闭弹窗
    close() {
        if (this.instance) {
            this.instance.mask.classList.add('hidden');
            // 清空内容（避免缓存）
            this.instance.body.innerHTML = '';
            this.instance.footer.innerHTML = '';
        }
    },

    // 销毁弹窗
    destroy() {
        if (this.instance) {
            document.body.removeChild(this.instance.mask);
            this.instance = null;
        }
    }
};