// api.js 中新增防抖工具函数
const requestDebounce = (() => {
    const pendingRequests = new Map(); // 存储待处理的请求
    return async (url, requestFn) => {
        // 如果同一URL正在请求，返回已有Promise
        if (pendingRequests.has(url)) {
            return pendingRequests.get(url);
        }
        // 执行请求并缓存Promise
        const promise = requestFn().finally(() => {
            pendingRequests.delete(url); // 请求完成后移除
        });
        pendingRequests.set(url, promise);
        return promise;
    };
})();
// api.js 最终版（删除initCsrfToken的自动调用）
const api = {
    // 基础请求地址，按实际后端地址调整
    baseUrl: 'http://127.0.0.1:8080',
    // 修复：正确读取Cookie（处理解码+语法错误）
    getCookie(name) {
        // 处理空Cookie场景
        if (!document.cookie) return null;

        const cookieList = document.cookie.split(';');
        for (let cookie of cookieList) {
            // 去除首尾空格
            const trimmedCookie = cookie.trim();
            // 分割Cookie名和值（处理值中包含=的情况）
            const separatorIndex = trimmedCookie.indexOf('=');
            if (separatorIndex === -1) continue;

            const cookieKey = trimmedCookie.substring(0, separatorIndex);
            const cookieValue = trimmedCookie.substring(separatorIndex + 1);

            // 匹配目标Cookie名（区分大小写，与后端一致）
            if (cookieKey === name) {
                // 解码Cookie值（处理特殊字符）
                try {
                    return decodeURIComponent(cookieValue);
                } catch (e) {
                    // 解码失败时返回原始值
                    return cookieValue;
                }
            }
        }
        return null;
    },

    // 修复：构建请求头（保留原有Token逻辑，确保CSRF Token正确携带）
    getHeaders() {
        const headers = {
            "Content-Type": "application/json;charset=utf-8"
        };
        // 登录态Token（如已实现）
        const token = localStorage.getItem('token');
        if (token && token.trim() !== '') {
            headers["Authorization"] = `Bearer ${token.trim()}`;
        }
        // 读取并携带CSRF Token（与后端约定的X-CSRF-Token头名一致）
        const csrfToken = this.getCookie('X-CSRF-Token');
        // console.log("读取到的CSRF Token:", csrfToken); // 调试用，可删除
        if (csrfToken) {
            headers["X-CSRF-Token"] = csrfToken;
        }
        return headers;
    },

    // 保留：URL拼接逻辑（已修复）
    buildUrl(url) {
        if (url.startsWith('http://') || url.startsWith('https://')) {
            return url;
        }
        let base = this.baseUrl;
        if (!base) return url;
        // 统一URL格式
        if (base.endsWith('/')) base = base.slice(0, -1);
        if (!url.startsWith('/')) url = '/' + url;
        return base + url;
    },

    // 核心修复：基础请求方法（添加withCredentials + 完善错误处理）
    // api.js 中新增请求防抖+缓存逻辑（全局生效）


    // 新增：请求缓存（避免短时间重复请求同一接口）
    requestCache: new Map(),
    // 新增：防抖计时器
    requestDebounceTimer: {},

    // 原有方法（getCookie/getHeaders/buildUrl）保持不变...

    // 修改核心 request 方法，添加防抖+缓存
    request(method, url, data = {}) {
        const fullUrl = this.buildUrl(url);
        const cacheKey = `${method}_${fullUrl}`;

        // 1. 如果有缓存且未过期（5秒），直接返回缓存
        const cache = this.requestCache.get(cacheKey);
        if (cache && Date.now() - cache.time < 5000) {
            return Promise.resolve(cache.data);
        }

        // 2. 防抖：取消之前的请求计时器
        if (this.requestDebounceTimer[cacheKey]) {
            clearTimeout(this.requestDebounceTimer[cacheKey]);
        }

        // 3. 返回新的Promise
        return new Promise((resolve, reject) => {
            this.requestDebounceTimer[cacheKey] = setTimeout(() => {
                const xhr = new XMLHttpRequest();
                xhr.open(method, fullUrl, true);
                xhr.withCredentials = true;

                // 设置请求头
                const headers = this.getHeaders();
                for (const key in headers) {
                    if (Object.prototype.hasOwnProperty.call(headers, key)) {
                        xhr.setRequestHeader(key, headers[key]);
                    }
                }

                // 响应处理
                xhr.onload = function () {
                    try {
                        const res = JSON.parse(xhr.responseText || '{}');
                        // 缓存成功的响应（5秒有效期）
                        if (xhr.status >= 200 && xhr.status < 300) {
                            api.requestCache.set(cacheKey, {
                                time: Date.now(),
                                data: res
                            });
                            resolve(res);
                        } else {
                            reject({
                                code: res.code || xhr.status,
                                msg: res.msg || `请求失败（${xhr.status}）`,
                                response: res
                            });
                        }
                    } catch (e) {
                        reject({
                            code: xhr.status,
                            msg: '响应数据格式错误：' + e.message,
                            response: xhr.responseText
                        });
                    }
                };

                // 网络错误处理
                xhr.onerror = function () {
                    reject({
                        code: 0,
                        msg: '网络异常，请检查网络连接或跨域配置'
                    });
                };

                // 超时处理
                xhr.timeout = 10000;
                xhr.ontimeout = function () {
                    reject({ code: 0, msg: '请求超时，请重试' });
                };

                // 发送请求
                if (method === 'GET' || method === 'DELETE') {
                    xhr.send();
                } else {
                    xhr.send(JSON.stringify(data));
                }

                // 清理计时器
                delete api.requestDebounceTimer[cacheKey];
            }, 300); // 300ms防抖延迟
        });
    },

    // 原有快捷方法（get/post/put/delete）保持不变...

    // 快捷请求方法（无修改）
    get(url) {
        return requestDebounce(url, () => this.request('GET', url));
    },
    post(url, data) {
        return this.request('POST', url, data);

    },
    put(url, data) {
        return this.request('PUT', url, data);
    },
    delete(url) {
        return this.request('DELETE', url);
    },

    // ========== 调整：移除自动初始化CSRF Token ==========
    /**
     * 初始化CSRF Token（由main.js统一调用，避免重复请求）
     */
    initCsrfToken() {
        return Promise.resolve(); // 空实现，避免重复请求
    }
};

// 移除：页面加载时自动初始化CSRF Token（避免重复请求/api/user/info）
// document.addEventListener('DOMContentLoaded', () => {
//     api.initCsrfToken();
// });