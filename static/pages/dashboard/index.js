// 仪表盘页面初始化
document.addEventListener('DOMContentLoaded', async function () {
    await loadStatData();
});

// 加载统计数据
async function loadStatData() {
    try {
        const res = await api.get('/api/dashboard/stat');
        if (res.code === 200) {
            const stat = res.data;
            // 更新统计卡片
            document.getElementById('user-count').textContent = stat.user_count;
            document.getElementById('role-count').textContent = stat.role_count;
            document.getElementById('perm-count').textContent = stat.perm_count;
            document.getElementById('unread-notify').textContent = stat.unread_notify;
            // 渲染角色分布（简易柱状图）
            renderRoleDist(stat.role_dist);
        }
    } catch (err) {
        notify.error('统计数据加载失败');
    }
}

// 渲染角色分布
function renderRoleDist(roleDist) {
    const container = document.getElementById('role-dist');
    if (!container || roleDist.length === 0) return;

    // 简易柱状图实现
    let html = '<div class="flex h-full align-end gap-4 p-4">';
    const maxCount = Math.max(...roleDist.map(item => item.count));

    roleDist.forEach(item => {
        const height = maxCount === 0 ? 0 : (item.count / maxCount) * 80;
        html += `
      <div class="flex-1 flex flex-col items-center">
        <div class="w-full bg-primary/60 rounded-t-md mb-2" style="height: ${height}%;"></div>
        <span class="text-sm">${item.name}</span>
        <span class="text-xs text-gray-500">${item.count}</span>
      </div>
    `;
    });
    html += '</div>';
    container.innerHTML = html;
}