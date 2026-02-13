// api.js 最终修复版（解决CSRF Token 403问题）
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
        console.log("读取到的CSRF Token:", csrfToken); // 调试用，可删除
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
    request(method, url, data = {}) {
        const fullUrl = this.buildUrl(url);
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open(method, fullUrl, true);

            // ========== 关键修复：跨域携带Cookie ==========
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
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(res);
                    } else {
                        // 传递完整错误信息（包含code/msg）
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

            // 超时处理（可选，避免无限等待）
            xhr.timeout = 10000; // 10秒超时
            xhr.ontimeout = function () {
                reject({ code: 0, msg: '请求超时，请重试' });
            };

            // 发送请求
            if (method === 'GET' || method === 'DELETE') {
                xhr.send();
            } else {
                xhr.send(JSON.stringify(data));
            }
        });
    },

    // 快捷请求方法（无修改）
    get(url) {
        return this.request('GET', url);
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

    // ========== 新增：初始化CSRF Token ==========
    /**
     * 页面加载时主动获取CSRF Token（调用任意GET接口）
     * 确保首次登录时Cookie中已有Token
     */
    initCsrfToken() {
        // 调用后端任意GET接口（如健康检查、用户信息等）
        return this.get('/api/user/info').catch(err => {
            // 忽略GET接口的错误（仅为获取Token）
            console.log("初始化CSRF Token时GET接口失败（非关键）：", err.msg);
            return null;
        });
    }
};

// 页面加载时自动初始化CSRF Token
document.addEventListener('DOMContentLoaded', () => {
    api.initCsrfToken();
});