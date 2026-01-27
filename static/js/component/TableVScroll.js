// 虚拟滚动表格组件，支持大数据量渲染，减少DOM节点
const tableVScroll = {
    // 组件实例缓存
    instances: {},

    // 初始化虚拟滚动表格
    init(elId, columns, data, rowHeight = 48) {
        const el = document.getElementById(elId);
        if (!el) return;

        // 渲染表格结构
        this.renderTable(el, columns);
        // 初始化实例参数
        const instance = {
            el,
            columns,
            data,
            rowHeight,
            viewportHeight: el.querySelector('.v-table-body').clientHeight,
            visibleCount: Math.ceil(el.querySelector('.v-table-body').clientHeight / rowHeight) + 2,
            startIndex: 0,
            scrollTop: 0
        };
        // 缓存实例
        this.instances[elId] = instance;
        // 渲染可见行
        this.renderVisibleRows(instance);
        // 绑定滚动事件
        this.bindScrollEvent(instance);
    },

    // 渲染表格基础结构
    renderTable(el, columns) {
        // 渲染表头
        const headerHtml = columns.map(col => `
      <div class="v-table-header-item" style="flex: ${col.width || 1};">${col.label}</div>
    `).join('');
        // 渲染表格主体
        el.innerHTML = `
      <div class="v-table-header">${headerHtml}</div>
      <div class="v-table-body">
        <div class="v-table-row-wrapper"></div>
      </div>
    `;
        // 空数据处理
        if (columns.length === 0 || !columns) {
            el.querySelector('.v-table-body').innerHTML = '<div class="v-table-empty">暂无数据</div>';
        }
    },

    // 渲染可见行
    renderVisibleRows(instance) {
        const { el, data, columns, rowHeight, visibleCount, startIndex } = instance;
        const rowWrapper = el.querySelector('.v-table-row-wrapper');
        const totalCount = data.length;

        // 空数据处理
        if (totalCount === 0) {
            el.querySelector('.v-table-body').innerHTML = '<div class="v-table-empty">暂无数据</div>';
            return;
        }

        // 计算结束索引
        let endIndex = startIndex + visibleCount;
        if (endIndex > totalCount) endIndex = totalCount;
        // 截取可见数据
        const visibleData = data.slice(startIndex, endIndex);

        // 渲染可见行
        let rowsHtml = '';
        visibleData.forEach((row, index) => {
            const rowIndex = startIndex + index;
            const rowItems = columns.map(col => {
                // 自定义渲染函数
                if (col.render) {
                    return `<div class="v-table-row-item" style="flex: ${col.width || 1};">${col.render(row, rowIndex)}</div>`;
                }
                return `<div class="v-table-row-item" style="flex: ${col.width || 1};">${row[col.prop] || ''}</div>`;
            }).join('');
            rowsHtml += `<div class="v-table-row" data-index="${rowIndex}">${rowItems}</div>`;
        });

        // 设置行容器样式（占位高度 + 偏移）
        rowWrapper.style.height = `${totalCount * rowHeight}px`;
        rowWrapper.style.transform = `translateY(${startIndex * rowHeight}px)`;
        rowWrapper.innerHTML = rowsHtml;
    },

    // 绑定滚动事件
    bindScrollEvent(instance) {
        const { el, rowHeight, data } = instance;
        const bodyEl = el.querySelector('.v-table-body');

        bodyEl.addEventListener('scroll', () => {
            // 更新滚动距离
            instance.scrollTop = bodyEl.scrollTop;
            // 计算起始索引
            instance.startIndex = Math.floor(instance.scrollTop / rowHeight);
            // 边界处理
            if (instance.startIndex < 0) instance.startIndex = 0;
            if (instance.startIndex > data.length - instance.visibleCount) {
                instance.startIndex = Math.max(0, data.length - instance.visibleCount);
            }
            // 重新渲染可见行
            this.renderVisibleRows(instance);
        });
    },

    // 更新表格数据
    updateData(elId, newData) {
        const instance = this.instances[elId];
        if (!instance) return;
        instance.data = newData;
        instance.startIndex = 0;
        this.renderVisibleRows(instance);
    },

    // 销毁组件
    destroy(elId) {
        delete this.instances[elId];
    }
};