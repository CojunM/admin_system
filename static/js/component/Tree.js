// 树形数据组件，支持复选框、展开/折叠、节点点击
const tree = {
    // 组件实例缓存
    instances: {},

    // 初始化树形组件
    init(elId, data, options = {}) {
        const el = document.getElementById(elId);
        if (!el) return;

        // 默认配置
        const defaultOptions = {
            showCheckbox: false, // 是否显示复选框
            expandAll: false,    // 是否默认展开所有节点
            onCheck: null,       // 复选框点击回调
            onNodeClick: null    // 节点点击回调
        };
        const finalOptions = { ...defaultOptions, ...options };

        // 初始化实例
        const instance = {
            el,
            data: JSON.parse(JSON.stringify(data)), // 深拷贝数据
            options: finalOptions,
            checkedKeys: [] // 选中的节点ID
        };
        this.instances[elId] = instance;

        // 渲染树形结构
        this.renderTree(instance);
        // 绑定事件
        this.bindTreeEvents(instance);
    },

    // 渲染树形结构
    renderTree(instance, parentEl = null, data = null, level = 0, parentIds = []) {
        const { el, options } = instance;
        const renderData = data || instance.data;
        const container = parentEl || el;

        // 清空容器（根节点）
        if (level === 0) container.innerHTML = '';

        renderData.forEach(node => {
            // 节点ID（默认id，可自定义）
            const nodeId = node.id;
            // 标记是否展开
            const isExpanded = options.expandAll || node.expanded;
            // 构建节点类名
            const nodeClass = `tree-node ${node.disabled ? 'tree-node-disabled' : ''}`;
            // 构建子节点容器类名
            const childrenClass = `tree-children ${isExpanded ? 'expanded' : ''}`;

            // 节点HTML
            let nodeHtml = `
        <div class="${nodeClass}" data-id="${nodeId}" data-level="${level}" data-parent-ids="${parentIds.join(',')}">
          <div class="tree-indent">${this.renderIndent(instance, level, node, renderData)}</div>
          <div class="tree-toggle ${isExpanded ? 'expanded' : ''}">
            ${node.children && node.children.length > 0 ? '▶' : ''}
          </div>
          ${options.showCheckbox ? `
            <div class="tree-checkbox ${this.isChecked(instance, nodeId) ? 'checked' : ''} ${node.disabled ? 'disabled' : ''}"></div>
          ` : ''}
          <i class="tree-icon ${node.icon || 'fa-solid fa-folder'}"></i>
          <span class="tree-label">${node.name}</span>
        </div>
      `;

            // 创建节点元素
            const nodeEl = document.createElement('div');
            nodeEl.innerHTML = nodeHtml;
            container.appendChild(nodeEl.firstChild);

            // 渲染子节点
            if (node.children && node.children.length > 0) {
                const childrenEl = document.createElement('div');
                childrenEl.className = childrenClass;
                container.appendChild(childrenEl);
                // 递归渲染子节点
                this.renderTree(instance, childrenEl, node.children, level + 1, [...parentIds, nodeId]);
            }
        });
    },

    // 渲染缩进和连接线
    renderIndent(instance, level, node, siblingData) {
        if (level === 0) return '';

        let indentHtml = '';
        const parentIds = node.parentIds ? node.parentIds.split(',') : [];

        for (let i = 0; i < level - 1; i++) {
            const isLastSibling = this.isLastSibling(siblingData, node);
            indentHtml += `<div class="tree-line tree-line-v ${isLastSibling ? 'hidden' : ''}"></div>`;
        }

        // 最后一级的横线
        indentHtml += `<div class="tree-line tree-line-h"></div>`;
        return indentHtml;
    },

    // 判断是否是最后一个子节点
    isLastSibling(siblingData, node) {
        const lastNode = siblingData[siblingData.length - 1];
        return lastNode.id === node.id;
    },

    // 判断节点是否被选中
    isChecked(instance, nodeId) {
        return instance.checkedKeys.includes(nodeId);
    },

    // 绑定树形事件
    bindTreeEvents(instance) {
        const { el, options } = instance;

        // 展开/折叠事件
        el.addEventListener('click', e => {
            const toggleEl = e.target.closest('.tree-toggle');
            if (toggleEl) {
                const nodeEl = toggleEl.closest('.tree-node');
                const childrenEl = nodeEl.nextElementSibling;
                if (childrenEl && childrenEl.classList.contains('tree-children')) {
                    childrenEl.classList.toggle('expanded');
                    toggleEl.classList.toggle('expanded');
                }
            }
        });

        // 复选框点击事件
        if (options.showCheckbox) {
            el.addEventListener('click', e => {
                const checkboxEl = e.target.closest('.tree-checkbox');
                if (checkboxEl && !checkboxEl.classList.contains('disabled')) {
                    const nodeEl = checkboxEl.closest('.tree-node');
                    const nodeId = parseInt(nodeEl.dataset.id);
                    // 切换选中状态
                    this.toggleCheck(instance, nodeId);
                    // 触发回调
                    if (typeof options.onCheck === 'function') {
                        options.onCheck(instance.checkedKeys);
                    }
                }
            });
        }

        // 节点点击事件
        el.addEventListener('click', e => {
            const labelEl = e.target.closest('.tree-label');
            const iconEl = e.target.closest('.tree-icon');
            if ((labelEl || iconEl) && !e.target.closest('.tree-checkbox') && !e.target.closest('.tree-toggle')) {
                const nodeEl = (labelEl || iconEl).closest('.tree-node');
                const nodeId = parseInt(nodeEl.dataset.id);
                // 触发回调
                if (typeof options.onNodeClick === 'function') {
                    options.onNodeClick(nodeId);
                }
            }
        });
    },

    // 切换节点选中状态（支持半选/全选子节点）
    toggleCheck(instance, nodeId) {
        const { data, checkedKeys } = instance;
        const node = this.findNode(data, nodeId);
        if (!node) return;

        // 切换当前节点
        const index = checkedKeys.indexOf(nodeId);
        if (index > -1) {
            checkedKeys.splice(index, 1);
            // 取消所有子节点选中
            this.uncheckChildren(instance, node);
        } else {
            checkedKeys.push(nodeId);
            // 选中所有子节点
            this.checkChildren(instance, node);
        }

        // 更新视图
        this.updateCheckView(instance);
    },

    // 查找节点（递归）
    findNode(data, nodeId) {
        for (let i = 0; i < data.length; i++) {
            const node = data[i];
            if (node.id === nodeId) return node;
            if (node.children && node.children.length > 0) {
                const found = this.findNode(node.children, nodeId);
                if (found) return found;
            }
        }
        return null;
    },

    // 选中所有子节点
    checkChildren(instance, node) {
        const { checkedKeys } = instance;
        if (node.children && node.children.length > 0) {
            node.children.forEach(child => {
                if (!checkedKeys.includes(child.id)) {
                    checkedKeys.push(child.id);
                }
                this.checkChildren(instance, child);
            });
        }
    },

    // 取消所有子节点选中
    uncheckChildren(instance, node) {
        const { checkedKeys } = instance;
        if (node.children && node.children.length > 0) {
            node.children.forEach(child => {
                const index = checkedKeys.indexOf(child.id);
                if (index > -1) {
                    checkedKeys.splice(index, 1);
                }
                this.uncheckChildren(instance, child);
            });
        }
    },

    // 更新复选框视图
    updateCheckView(instance) {
        const { el, checkedKeys } = instance;
        const allCheckboxes = el.querySelectorAll('.tree-checkbox');
        allCheckboxes.forEach(checkbox => {
            const nodeId = parseInt(checkbox.closest('.tree-node').dataset.id);
            checkbox.classList.toggle('checked', checkedKeys.includes(nodeId));
        });
    },

    // 获取选中的节点ID
    getCheckedKeys(elId) {
        const instance = this.instances[elId];
        return instance ? instance.checkedKeys : [];
    },

    // 设置选中的节点ID
    setCheckedKeys(elId, keys) {
        const instance = this.instances[elId];
        if (!instance) return;
        instance.checkedKeys = keys;
        this.updateCheckView(instance);
    },

    // 销毁组件
    destroy(elId) {
        delete this.instances[elId];
    }
};