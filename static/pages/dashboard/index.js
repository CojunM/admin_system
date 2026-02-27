// // 先添加调试代码，看事件是否触发、函数是否存在
// // console.log("脚本已加载，准备绑定事件");

// document.addEventListener('DOMContentLoaded', async function () {
//     console.log("DOMContentLoaded 事件触发！"); // 检查事件是否触发
//     try {
//         // console.log("开始执行 loadStatData 函数");
//         await loadStatData();
//         console.log("loadStatData 执行完成");
//     } catch (err) {
//         console.error("loadStatData 执行失败：", err); // 捕获异步错误
//     }
// });

// // 检查 loadStatData 函数是否定义（放在函数定义后）
// // console.log("loadStatData 函数是否存在：", typeof loadStatData);
// // 加载统计数据
// async function loadStatData() {
//     try {
//         notify.loading('正在加载统计数据...');
//         const res = await api.get('/api/dashboard/stats');
//         if (res.code === 200) {
//             const stat = res.data;
//             alert(res.msg);
//             // 更新统计卡片
//             document.getElementById('user-count').textContent = stat.user_count;
//             document.getElementById('role-count').textContent = stat.role_count;
//             document.getElementById('perm-count').textContent = stat.perm_count;
//             document.getElementById('unread-notify').textContent = stat.unread_notify;
//             // 渲染角色分布（简易柱状图）
//             renderRoleDist(stat.role_dist);
//         }
//     } catch (err) {
//         notify.error('统计数据加载失败');
//     }
// }

// // 渲染角色分布
// function renderRoleDist(roleDist) {
//     const container = document.getElementById('role-dist');
//     if (!container || roleDist.length === 0) return;

//     // 简易柱状图实现
//     let html = '<div class="flex h-full align-end gap-4 p-4">';
//     const maxCount = Math.max(...roleDist.map(item => item.count));

//     roleDist.forEach(item => {
//         const height = maxCount === 0 ? 0 : (item.count / maxCount) * 80;
//         html += `
//       <div class="flex-1 flex flex-col items-center">
//         <div class="w-full bg-primary/60 rounded-t-md mb-2" style="height: ${height}%;"></div>
//         <span class="text-sm">${item.name}</span>
//         <span class="text-xs text-gray-500">${item.count}</span>
//       </div>
//     `;
//     });
//     html += '</div>';
//     container.innerHTML = html;
// }
// /static/pages/dashboard/index.js（最终版）
// console.log("✅ 仪表盘脚本动态加载完成");

// // 检查核心依赖
// console.log("🔍 api 对象是否存在：", typeof api);
// console.log("🔍 notify 对象是否存在：", typeof notify);
// // 打印 notify 的所有方法，确认可用方法
// console.log("🔍 notify 可用方法：", Object.keys(notify || {}));

// 封装初始化逻辑
// /static/pages/dashboard/index.js 中修改 initDashboard 函数
async function initDashboard() {
    // 防重复执行
    if (window.dashboardLoading) return;
    window.dashboardLoading = true;

    // 获取页面元素
    const loadingTipEl = document.getElementById('loading-tip');
    const statsContainerEl = document.getElementById('stats-container');
    const roleDistContainerEl = document.getElementById('role-dist-container');

    try {
        // 加载开始：显示加载提示，隐藏统计内容
        if (loadingTipEl) loadingTipEl.style.display = 'block';
        if (statsContainerEl) statsContainerEl.classList.add('hidden');
        if (roleDistContainerEl) roleDistContainerEl.classList.add('hidden');

        if (notify?.info) {
            notify.info('正在加载统计数据...');
        }
        console.log("🔄 开始加载统计数据...");

        const res = await api.get('/api/dashboard/stats');
        console.log("📥 接口返回完整数据：", JSON.stringify(res, null, 2));

        if (res.code === 200) {
            const {
                user_count = 0,
                role_count = 0,
                perm_count = 0,
                unread_notify = 0,
                role_dist = []
            } = res.data || {};

            console.log("🔍 解构后的数据：", {
                user_count, role_count, perm_count, unread_notify, role_dist
            });

            // 更新统计卡片
            const userCountEl = document.getElementById('user-count');
            if (userCountEl) userCountEl.textContent = user_count;
            const roleCountEl = document.getElementById('role-count');
            if (roleCountEl) roleCountEl.textContent = role_count;
            const permCountEl = document.getElementById('perm-count');
            if (permCountEl) permCountEl.textContent = perm_count;
            const unreadNotifyEl = document.getElementById('unread-notify');
            if (unreadNotifyEl) unreadNotifyEl.textContent = unread_notify;

            // 渲染角色分布
            renderRoleDist(role_dist);

            // 加载成功：隐藏加载提示，显示统计内容
            if (loadingTipEl) loadingTipEl.style.display = 'none';
            if (statsContainerEl) statsContainerEl.classList.remove('hidden');
            if (roleDistContainerEl) roleDistContainerEl.classList.remove('hidden');

            if (notify?.success) {
                notify.success('统计数据加载成功');
            }
        } else {
            const errMsg = res.msg || '未知错误';
            // 加载失败：替换加载提示为错误信息
            if (loadingTipEl) loadingTipEl.innerHTML = `<span style="color: red;">加载失败：${errMsg}</span>`;
            if (notify?.error) notify.error(`数据加载失败：${errMsg}`);
        }
    } catch (err) {
        const errMsg = err?.msg || err?.message || '未知错误';
        console.error("❌ 加载统计数据失败：", errMsg);
        // 加载异常：替换加载提示为错误信息
        if (loadingTipEl) loadingTipEl.innerHTML = `<span style="color: red;">加载失败：${errMsg}</span>`;
        if (notify?.error) notify.error(`统计数据加载失败：${errMsg}`);
    } finally {
        // 释放标记
        window.dashboardLoading = false;
    }
}

// 渲染角色分布函数保持不变...
// 渲染角色分布
function renderRoleDist(roleDist) {
    const container = document.getElementById('role-dist');
    if (!container) {
        console.warn("⚠️ 未找到角色分布容器 #role-dist");
        return;
    }

    // ========== 修复：强制校验数据格式 ==========
    // 确保是数组，且每个项有 name/count 字段
    const validRoleDist = Array.isArray(roleDist)
        ? roleDist.filter(item => item && item.name && typeof item.count === 'number')
        : [];

    console.log("🔍 有效角色分布数据：", validRoleDist);

    if (validRoleDist.length === 0) {
        container.innerHTML = '<div class="text-center p-4 text-gray-500">暂无角色数据</div>';
        return;
    }

    // 渲染柱状图
    let html = '<div class="flex h-full items-end gap-4 p-4">';
    const maxCount = Math.max(...validRoleDist.map(item => item.count));

    validRoleDist.forEach(item => {
        const height = maxCount === 0 ? 0 : (item.count / maxCount) * 80;
        html += `
            <div class="flex-1 flex flex-col items-center">
                <div class="w-full bg-blue-500/60 rounded-t-md mb-2" style="height: ${height}%;"></div>
                <span class="text-sm">${item.name}</span>
                <span class="text-xs text-gray-500">${item.count}</span>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
    console.log("✅ 角色分布渲染完成");
}
// 动态加载后立即执行（延迟100ms确保DOM就绪）
setTimeout(initDashboard, 100);

// 暴露到全局，方便主脚本兜底调用
// window.initDashboard = initDashboard;