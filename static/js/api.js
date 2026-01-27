// 后端API请求封装，统一处理请求头、响应、错误
const api = {
    // 基础配置
    baseUrl: '',
    timeout: 10000,

    // 请求头配置
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json',
            'X-CSRF-Token': document.cookie.split('; ').find(row => row.startsWith('X-CSRF-Token=')).split('=')[1] || ''
        };
        // 添加Token
        const token = store.get('token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    },

    // 统一请求处理
    async request(method, url, data = {}) {
        try {
            const options = {
                method: method.toUpperCase(),
                headers: this.getHeaders(),
                timeout: this.timeout
            };

            // GET请求拼接参数，其他请求设置body
            if (method.toUpperCase() === 'GET') {
                const params = new URLSearchParams(data);
                url += params.toString() ? `?${params.toString()}` : '';
            } else {
                options.body = JSON.stringify(data);
            }

            // 发送请求
            const response = await fetch(this.baseUrl + url, options);
            const res = await response.json();

            // 统一响应处理
            if (res.code === 200) {
                return res;
            } else if (res.code === 401) {
                // 未登录/Token过期，跳转到登录页
                store.remove('token');
                window.location.href = '/';
                notify.error(res.msg || '登录状态过期，请重新登录');
                throw new Error(res.msg);
            } else {
                notify.error(res.msg || '请求失败');
                throw new Error(res.msg);
            }
        } catch (err) {
            if (err.message !== 'Failed to fetch') {
                notify.error(err.message || '网络异常，请稍后重试');
            }
            throw err;
        }
    },

    // 快捷请求方法
    get(url, params = {}) {
        return this.request('GET', url, params);
    },

    post(url, data = {}) {
        return this.request('POST', url, data);
    },

    put(url, data = {}) {
        return this.request('PUT', url, data);
    },

    delete(url, data = {}) {
        return this.request('DELETE', url, data);
    },

    patch(url, data = {}) {
        return this.request('PATCH', url, data);
    }
};