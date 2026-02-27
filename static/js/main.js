// 新增：全局缓存用户信息，避免重复请求
let userInfoCache = null; // 缓存用户信息
let isUserInfoRequesting = false; // 防止并发请求

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
    // 渲染顶部导航（包含CSRF Token初始化，只请求一次）
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

// 渲染顶部导航（修复语法错误 + 429 处理）
async function renderHeader() {
    const userInfoEl = document.querySelector('.user-info');
    const notifyCountEl = document.querySelector('.notify-count');
    if (!userInfoEl) return;

    // 1. 如果有缓存，直接用缓存渲染，不发请求
    if (userInfoCache) {
        renderUserInfo(userInfoCache);
        return;
    }

    // 2. 如果正在请求中，避免重复请求
    if (isUserInfoRequesting) return;

    let err = null; // 修复：提前定义 err 变量
    try {
        isUserInfoRequesting = true; // 标记正在请求
        const res = await api.get('/api/user/info');
        if (res.code === 200) {
            userInfoCache = res.data; // 缓存用户信息
            renderUserInfo(res.data); // 渲染
        }
    } catch (error) {
        err = error; // 赋值给提前定义的 err
        // 处理 429 错误：提示用户并延迟重试（只重试1次）
        if (err.response && err.response.status === 429) {
            notify.warning('请求过于频繁，正在重试...');
            setTimeout(async () => {
                try {
                    const res = await api.get('/api/user/info');
                    if (res.code === 200) {
                        userInfoCache = res.data;
                        renderUserInfo(res.data);
                    }
                } catch (retryErr) {
                    notify.error('用户信息加载失败，请刷新页面');
                } finally {
                    isUserInfoRequesting = false;
                }
            }, 1000); // 延迟1秒重试
        } else {
            notify.error('用户信息加载失败');
        }
    } finally {
        // 修复：判断 err 已定义，避免未定义报错
        if (!err || (err.response && err.response.status !== 429)) {
            isUserInfoRequesting = false; // 解除请求标记
        }
    }
}

// 抽离渲染逻辑，复用缓存
function renderUserInfo(user) {
    const userInfoEl = document.querySelector('.user-info');
    // 兜底：防止 user 为空或属性缺失
    const avatar = user?.avatar || '/static/images/avatar-default.png';
    const nickname = user?.nickname || '未知用户';

    userInfoEl.innerHTML = `
        <img src="${avatar}" alt="头像" class="avatar" width="32" height="32" style="border-radius: 50%;">
        <span class="nickname">${nickname}</span>
    `;
    // 绑定退出登录事件（只绑定一次）
    const logoutBtn = document.querySelector('#logout-btn');
    if (logoutBtn) {
        logoutBtn.removeEventListener('click', logout); // 先移除，避免重复绑定
        logoutBtn.addEventListener('click', logout);
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
// main.js 中的 loadPage 函数（修改部分）
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

            // ========== 修改：脚本加载完成后执行回调 ==========
            const script = document.createElement('script');
            script.src = `/static/pages${path}/index.js`;
            // 脚本加载完成后触发（确保DOM已就绪）
            script.onload = function () {
                console.log(`✅ 动态脚本 ${path}/index.js 加载完成`);
                // 仪表盘页面兜底调用（确保只执行一次）
                if (path === '/dashboard' && window.initDashboard && !window.dashboardLoaded) {
                    window.dashboardLoaded = true;
                    window.initDashboard();
                }
            };
            // 脚本加载失败提示
            script.onerror = function () {
                console.error(`❌ 动态脚本 ${path}/index.js 加载失败`);
                notify.error('页面脚本加载失败');
            };
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
    document.querySelector('.theme-switch').addEventListener('click', theme.toggle.bind(theme));
    // 通知图标点击
    document.querySelector('.notify-icon').addEventListener('click', function () {
        loadPage('/notify');
    });
}

// 退出登录
function logout() {
    modal.confirm('确认退出登录吗？', function () {
        store.remove('token');
        userInfoCache = null; // 清空缓存
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