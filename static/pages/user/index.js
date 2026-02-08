// 全局变量
let currentPage = 1;
let pageSize = 10;
let total = 0;
let roleList = [];

// 用户管理页面初始化
document.addEventListener('DOMContentLoaded', async function () {
    // 加载角色列表（用于下拉选择）
    await loadRoleList();
    // 加载用户列表
    await loadUserList();
    // 绑定事件
    bindEvents();
});

// 加载角色列表
async function loadRoleList() {
    try {
        const res = await api.get('/api/role/list', { page_size: 100 });
        if (res.code === 200) {
            roleList = res.data.list;
            // 渲染角色下拉
            const roleSelect = document.querySelector('select[name="role_id"]');
            roleSelect.innerHTML = roleList.map(role => `<option value="${role.id}">${role.name}</option>`).join('');
        }
    } catch (err) {
        notify.error('角色列表加载失败');
    }
}

// 加载用户列表
async function loadUserList() {
    try {
        loading.show();
        const keyword = document.getElementById('search-keyword').value.trim();
        const res = await api.get('/api/user/list', {
            page: currentPage,
            page_size: pageSize,
            keyword
        });
        if (res.code === 200) {
            const { list, total: totalCount } = res.data;
            total = totalCount;
            // 渲染虚拟滚动表格
            renderUserTable(list);
            // 更新分页
            updatePagination();
        }
    } catch (err) {
        notify.error('用户列表加载失败');
    } finally {
        loading.hide();
    }
}

// 渲染用户表格
function renderUserTable(data) {
    const columns = [
        { prop: 'id', label: 'ID', width: 0.5 },
        { prop: 'username', label: '用户名', width: 1 },
        { prop: 'nickname', label: '昵称', width: 1 },
        { prop: 'phone', label: '手机号', width: 1.2 },
        { prop: 'email', label: '邮箱', width: 1.5 },
        {
            prop: 'role_id',
            label: '角色',
            width: 1,
            render: (row) => {
                const role = roleList.find(item => item.id === row.role_id);
                return role ? role.name : '';
            }
        },
        {
            prop: 'status',
            label: '状态',
            width: 0.8,
            render: (row) => {
                return row.status === 1 ? '<span class="text-success">启用</span>' : '<span class="text-danger">禁用</span>';
            }
        },
        {
            prop: 'create_time',
            label: '创建时间',
            width: 1.5
        },
        {
            label: '操作',
            width: 1.2,
            render: (row) => {
                return `
          <button class="btn btn-default btn-sm edit-btn" data-id="${row.id}">编辑</button>
          <button class="btn btn-danger btn-sm delete-btn" data-id="${row.id}">删除</button>
        `;
            }
        }
    ];

    // 初始化虚拟滚动表格
    tableVScroll.init('user-table', columns, data);
    // 绑定表格内按钮事件
    bindTableBtnEvents();
}

// 绑定表格内按钮事件
function bindTableBtnEvents() {
    // 编辑按钮
    document.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', async function () {
            const userId = this.dataset.id;
            await loadUserInfo(userId);
        });
    });
    // 删除按钮
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const userId = this.dataset.id;
            deleteUser(userId);
        });
    });
}

// 更新分页
function updatePagination() {
    pagination.init('user-pagination', {
        page: currentPage,
        pageSize: pageSize,
        total: total,
        onPageChange: (page, size) => {
            currentPage = page;
            pageSize = size;
            loadUserList();
        },
        onSizeChange: (size, page) => {
            currentPage = page;
            pageSize = size;
            loadUserList();
        }
    });
}

// 绑定全局事件
function bindEvents() {
    // 添加用户按钮
    document.getElementById('add-user-btn').addEventListener('click', addUser);
    // 搜索按钮
    document.getElementById('search-btn').addEventListener('click', () => {
        currentPage = 1;
        loadUserList();
    });
    // 重置按钮
    document.getElementById('reset-btn').addEventListener('click', () => {
        document.getElementById('search-keyword').value = '';
        currentPage = 1;
        loadUserList();
    });
    // 回车搜索
    document.getElementById('search-keyword').addEventListener('keydown', e => {
        if (e.key === 'Enter') document.getElementById('search-btn').click();
    });
    // 表单提交
    document.getElementById('user-form').addEventListener('submit', async function (e) {
        e.preventDefault();
        await saveUser();
    });
}

// 添加用户
function addUser() {
    // 重置表单
    const form = document.getElementById('user-form');
    form.reset();
    form.name = 'id';
    // 打开弹窗
    modal.open({
        title: '添加用户',
        content: form.outerHTML,
        onConfirm: async () => {
            await saveUser();
        }
    });
    // 重新绑定表单提交事件
    document.querySelector('.modal-body form').addEventListener('submit', async function (e) {
        e.preventDefault();
        await saveUser();
    });
}

// 加载用户信息（编辑）
async function loadUserInfo(userId) {
    try {
        loading.show();
        const res = await api.get(`/api/user/info/${userId}`);
        if (res.code === 200) {
            const user = res.data;
            // 填充表单
            const form = document.getElementById('user-form');
            for (const key in user) {
                const input = form.querySelector(`[name="${key}"]`);
                if (input) input.value = user[key];
            }
            // 密码框留空
            form.querySelector('[name="password"]').value = '';
            // 打开弹窗
            modal.open({
                title: '编辑用户',
                content: form.outerHTML,
                onConfirm: async () => {
                    await saveUser(userId);
                }
            });
            // 重新绑定表单提交事件
            document.querySelector('.modal-body form').addEventListener('submit', async function (e) {
                e.preventDefault();
                await saveUser(userId);
            });
        }
    } catch (err) {
        notify.error('用户信息加载失败');
    } finally {
        loading.hide();
    }
}

// 保存用户（添加/编辑）
async function saveUser(userId) {
    try {
        loading.show();
        // 获取表单数据
        const form = document.querySelector('.modal-body form');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        // 参数验证
        if (!validateParams({
            username: is_username,
            phone: is_phone,
            email: is_email
        }, data)) {
            notify.warning('参数格式错误，请检查后重试');
            return;
        }

        // 添加/编辑接口区分
        let res;
        if (userId) {
            // 编辑：删除空密码（不修改密码）
            if (!data.password) delete data.password;
            res = await api.put(`/api/user/edit/${userId}`, data);
        } else {
            // 添加：验证密码
            if (!data.password || !is_password(data.password)) {
                notify.warning('密码需6-20位，包含字母和数字');
                return;
            }
            res = await api.post('/api/user/add', data);
        }

        if (res.code === 200) {
            notify.success(userId ? '编辑成功' : '添加成功');
            modal.close();
            loadUserList();
        }
    } catch (err) {
        console.error('保存用户失败', err);
    } finally {
        loading.hide();
    }
}

// 删除用户
function deleteUser(userId) {
    modal.confirm('确认删除该用户吗？', async () => {
        try {
            loading.show();
            const res = await api.delete(`/api/user/delete/${userId}`);
            if (res.code === 200) {
                notify.success('删除成功');
                loadUserList();
            }
        } catch (err) {
            notify.error('删除失败，该用户可能已被关联');
        } finally {
            loading.hide();
        }
    });
}