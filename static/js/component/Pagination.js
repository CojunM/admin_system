// 分页组件，支持页码切换、每页条数选择、跳页
const pagination = {
    // 组件实例缓存
    instances: {},

    // 初始化分页组件
    init(elId, options = {}) {
        const el = document.getElementById(elId);
        if (!el) return;

        // 默认配置
        const defaultOptions = {
            page: 1,          // 当前页
            pageSize: 10,     // 每页条数
            total: 0,         // 总条数
            pageSizes: [10, 20, 50, 100], // 可选每页条数
            layout: 'prev, pager, next, jumper, ->, total, sizes', // 布局
            onSizeChange: null, // 每页条数改变回调
            onPageChange: null  // 页码改变回调
        };
        const finalOptions = { ...defaultOptions, ...options };

        // 初始化实例
        const instance = {
            el,
            options: finalOptions
        };
        this.instances[elId] = instance;

        // 渲染分页
        this.renderPagination(instance);
        // 绑定事件
        this.bindPaginationEvents(instance);
    },

    // 渲染分页结构
    renderPagination(instance) {
        const { el, options } = instance;
        const { page, pageSize, total, pageSizes, layout } = options;
        const totalPages = Math.ceil(total / pageSize) || 1;

        // 清空容器
        el.innerHTML = '';
        // 无数据时隐藏
        if (total === 0) {
            el.classList.add('hidden');
            return;
        }
        el.classList.remove('hidden');

        // 解析布局
        const layoutItems = layout.split(',').map(item => item.trim());
        let paginationHtml = '';

        layoutItems.forEach(item => {
            switch (item) {
                // 上一页
                case 'prev':
                    const prevDisabled = page === 1 ? 'disabled' : '';
                    paginationHtml += `
            <div class="pagination-item prev ${prevDisabled}" data-page="${page - 1}">
              <i class="fa-solid fa-angle-left"></i>
            </div>
          `;
                    break;
                // 页码
                case 'pager':
                    let pagerHtml = '';
                    // 页码显示规则：当前页前后各2页，首尾各1页
                    const startPage = Math.max(1, page - 2);
                    const endPage = Math.min(totalPages, page + 2);

                    // 首页
                    if (startPage > 1) {
                        pagerHtml += `<div class="pagination-item" data-page="1">1</div>`;
                        if (startPage > 2) {
                            pagerHtml += `<div class="pagination-item ellipsis">...</div>`;
                        }
                    }

                    // 中间页码
                    for (let i = startPage; i <= endPage; i++) {
                        const active = i === page ? 'active' : '';
                        pagerHtml += `<div class="pagination-item ${active}" data-page="${i}">${i}</div>`;
                    }

                    // 尾页
                    if (endPage < totalPages) {
                        if (endPage < totalPages - 1) {
                            pagerHtml += `<div class="pagination-item ellipsis">...</div>`;
                        }
                        pagerHtml += `<div class="pagination-item" data-page="${totalPages}">${totalPages}</div>`;
                    }

                    paginationHtml += pagerHtml;
                    break;
                // 下一页
                case 'next':
                    const nextDisabled = page === totalPages ? 'disabled' : '';
                    paginationHtml += `
            <div class="pagination-item next ${nextDisabled}" data-page="${page + 1}">
              <i class="fa-solid fa-angle-right"></i>
            </div>
          `;
                    break;
                // 跳页
                case 'jumper':
                    paginationHtml += `
            <div class="pagination-jump">
              <span>前往</span>
              <input type="number" min="1" max="${totalPages}" value="${page}" class="jump-input">
              <span>页</span>
              <div class="btn btn-default jump-btn">确定</div>
            </div>
          `;
                    break;
                // 总条数
                case 'total':
                    paginationHtml += `<div class="pagination-total">共 ${total} 条</div>`;
                    break;
                // 每页条数
                case 'sizes':
                    let sizesHtml = `<select class="page-size-select form-input" style="width: 80px;">`;
                    pageSizes.forEach(size => {
                        const selected = size === pageSize ? 'selected' : '';
                        sizesHtml += `<option value="${size}" ${selected}>${size} 条/页</option>`;
                    });
                    sizesHtml += `</select>`;
                    paginationHtml += sizesHtml;
                    break;
                // 分隔符
                case '->':
                    paginationHtml += `<div class="pagination-separator"></div>`;
                    break;
            }
        });

        // 渲染到容器
        el.innerHTML = paginationHtml;
    },

    // 绑定分页事件
    bindPaginationEvents(instance) {
        const { el, options } = instance;
        const totalPages = Math.ceil(options.total / options.pageSize) || 1;

        // 页码点击事件
        el.addEventListener('click', e => {
            const pageItem = e.target.closest('.pagination-item');
            if (pageItem && !pageItem.classList.contains('disabled') && !pageItem.classList.contains('ellipsis')) {
                const page = parseInt(pageItem.dataset.page);
                if (page && page >= 1 && page <= totalPages && page !== options.page) {
                    this.handlePageChange(instance, page);
                }
            }
        });

        // 跳页按钮事件
        const jumpBtn = el.querySelector('.jump-btn');
        const jumpInput = el.querySelector('.jump-input');
        if (jumpBtn && jumpInput) {
            jumpBtn.addEventListener('click', () => {
                let page = parseInt(jumpInput.value);
                if (isNaN(page)) page = 1;
                page = Math.max(1, Math.min(totalPages, page));
                if (page !== options.page) {
                    this.handlePageChange(instance, page);
                }
                jumpInput.value = page;
            });

            // 回车跳页
            jumpInput.addEventListener('keydown', e => {
                if (e.key === 'Enter') jumpBtn.click();
            });
        }

        // 每页条数改变事件
        const sizeSelect = el.querySelector('.page-size-select');
        if (sizeSelect) {
            sizeSelect.addEventListener('change', () => {
                const pageSize = parseInt(sizeSelect.value);
                if (pageSize !== options.pageSize) {
                    this.handleSizeChange(instance, pageSize);
                }
            });
        }
    },

    // 处理页码改变
    handlePageChange(instance, page) {
        instance.options.page = page;
        this.renderPagination(instance);
        if (typeof instance.options.onPageChange === 'function') {
            instance.options.onPageChange(page, instance.options.pageSize);
        }
    },

    // 处理每页条数改变
    handleSizeChange(instance, pageSize) {
        instance.options.pageSize = pageSize;
        instance.options.page = 1; // 重置为第一页
        this.renderPagination(instance);
        if (typeof instance.options.onSizeChange === 'function') {
            instance.options.onSizeChange(pageSize, 1);
        }
    },

    // 更新分页配置
    updateOptions(elId, newOptions) {
        const instance = this.instances[elId];
        if (!instance) return;
        instance.options = { ...instance.options, ...newOptions };
        this.renderPagination(instance);
        this.bindPaginationEvents(instance);
    },

    // 销毁组件
    destroy(elId) {
        delete this.instances[elId];
    }
};