// 前端全局入口，页面初始化 & 路由控制
document.addEventListener('DOMContentLoaded', function () {
    // 初始化核心模块
    store.init();
    theme.init();
    csrf.init();
    loading.init();
    notify.init();
    pagination.init();
    tree.init();
    tableVScroll.init();

    // 登录状态校验
    if (!store.get('token') && window.location.pathname !== '/') {
        window.location.href = '/';
        return;
    }

    // 初始化页面
    initApp();
});

// 初始化后台管理系统布局
function initApp() {
    // 渲染侧边栏菜单
    renderSidebar();
    // 渲染顶部导航
    renderHeader();
    // 路由初始化
    initRouter();
    // 绑定全局事件
    bindGlobalEvents();
    // 获取未读通知数量
    getUnreadNotifyCount();
}

// 渲染侧边栏菜单
async function renderSidebar() {
    const sidebarEl = document.querySelector('.sidebar .menu-list');
    if (!sidebarEl) return;

    try {
        const res = await api.get('/api/menu/list');
        if (res.code === 200) {
            const menuTree = res.data;
            sidebarEl.innerHTML = renderMenuTree(menuTree);
            // 绑定菜单点击事件
            bindMenuClick();
        }
    } catch (err) {
        notify.error('菜单加载失败');
    }
}

// 渲染菜单树形结构
function renderMenuTree(menuList) {
    let html = '';
    menuList.forEach(menu => {
        html += `
      <li class="menu-item" data-path="${menu.path}">
        <a href="javascript:;" class="menu-link flex align-center gap-10">
          <i class="${menu.icon}"></i>
          <span class="menu-name">${menu.name}</span>
        </a>
        ${menu.children && menu.children.length > 0 ? `
          <ul class="submenu">${renderMenuTree(menu.children)}</ul>
        ` : ''}
      </li>
    `;
    });
    return html;
}

// 绑定菜单点击事件
function bindMenuClick() {
    const menuLinks = document.querySelectorAll('.menu-link');
    menuLinks.forEach(link => {
        link.addEventListener('click', function () {
            // 展开/折叠子菜单
            const parent = this.closest('.menu-item');
            const submenu = parent.querySelector('.submenu');
            if (submenu) {
                submenu.classList.toggle('hidden');
                this.querySelector('i').classList.toggle('fa-caret-down');
                this.querySelector('i').classList.toggle('fa-caret-right');
            }
            // 跳转路由
            const path = parent.dataset.path;
            if (path) {
                window.history.pushState({}, '', path);
                loadPage(path);
                // 激活当前菜单
                document.querySelectorAll('.menu-item').forEach(item => {
                    item.classList.remove('active');
                });
                parent.classList.add('active');
            }
        });
    });
}

// 渲染顶部导航
async function renderHeader() {
    const userInfoEl = document.querySelector('.user-info');
    const notifyCountEl = document.querySelector('.notify-count');
    if (!userInfoEl) return;

    try {
        const res = await api.get('/api/user/info');
        if (res.code === 200) {
            const user = res.data;
            userInfoEl.innerHTML = `
        <img src="${user.avatar}" alt="头像" class="avatar" width="32" height="32" style="border-radius: 50%;">
        <span class="nickname">${user.nickname}</span>
      `;
            // 绑定退出登录事件
            document.querySelector('#logout-btn').addEventListener('click', logout);
        }
    } catch (err) {
        notify.error('用户信息加载失败');
    }
}

// 初始化前端路由
function initRouter() {
    // 加载当前页面
    loadPage(window.location.pathname);
    // 监听路由变化
    window.addEventListener('popstate', function () {
        loadPage(window.location.pathname);
    });
}

// 加载页面组件
async function loadPage(path) {
    const contentEl = document.querySelector('.main-content');
    if (!contentEl) return;

    // 首页重定向到仪表盘
    if (path === '/' || path === '/index.html') {
        window.history.pushState({}, '', '/dashboard');
        path = '/dashboard';
    }

    try {
        loading.show();
        // 加载页面HTML
        const res = await fetch(`/static/pages${path}/index.html`);
        if (res.ok) {
            const html = await res.text();
            contentEl.innerHTML = html;
            // 执行页面初始化脚本
            const script = document.createElement('script');
            script.src = `/static/pages${path}/index.js`;
            contentEl.appendChild(script);
        } else {
            contentEl.innerHTML = '<div class="text-center" style="margin-top: 100px;">404 页面不存在</div>';
        }
    } catch (err) {
        contentEl.innerHTML = '<div class="text-center" style="margin-top: 100px;">页面加载失败</div>';
        notify.error('页面加载失败');
    } finally {
        loading.hide();
    }
}

// 绑定全局事件
function bindGlobalEvents() {
    // 主题切换
    document.querySelector('.theme-switch').addEventListener('click', theme.toggle);
    // 通知图标点击
    document.querySelector('.notify-icon').addEventListener('click', function () {
        loadPage('/notify');
    });
}

// 退出登录
function logout() {
    modal.confirm('确认退出登录吗？', function () {
        store.remove('token');
        window.location.href = '/';
        notify.success('退出登录成功');
    });
}

// 获取未读通知数量
async function getUnreadNotifyCount() {
    const notifyCountEl = document.querySelector('.notify-count');
    if (!notifyCountEl) return;

    try {
        const res = await api.get('/api/notify/unread-count');
        if (res.code === 200 && res.data.count > 0) {
            notifyCountEl.textContent = res.data.count;
            notifyCountEl.classList.remove('hidden');
        } else {
            notifyCountEl.classList.add('hidden');
        }
    } catch (err) {
        console.error('未读通知数量加载失败', err);
    }
}