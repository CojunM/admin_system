// api.js 完整修复版（原生JS，无框架依赖）
const api = {
    // 基础请求地址，按你的实际后端地址调整
    baseUrl: 'http://127.0.0.1:8080', // 如：'http://localhost:8000'

    // 修复后的请求头构建函数（核心：避免split()报错）
    getHeaders() {
        const headers = {
            "Content-Type": "application/json;charset=utf-8"
        };
        // 从localStorage获取Token，未登录时为null
        const token = localStorage.getItem('token');
        // 仅当Token存在时，设置Authorization请求头
        if (token && token.trim() !== '') {
            // 拼接Bearer前缀（后端鉴权中间件期望的格式）
            headers["Authorization"] = `Bearer ${token.trim()}`;
        }
        return headers;
    },

    // 基础请求方法
    request(method, url, data = {}) {
        const fullUrl = this.baseUrl ? `${this.baseUrl}${url}` : url;
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open(method, fullUrl, true);
            // 获取修复后的请求头
            const headers = this.getHeaders();
            // 设置请求头
            for (const key in headers) {
                xhr.setRequestHeader(key, headers[key]);
            }
            // 响应处理
            xhr.onload = function () {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const res = JSON.parse(xhr.responseText);
                        resolve(res);
                    } catch (e) {
                        reject({ msg: '响应数据格式错误' });
                    }
                } else {
                    try {
                        const err = JSON.parse(xhr.responseText);
                        reject(err);
                    } catch (e) {
                        reject({ msg: `请求失败，状态码：${xhr.status}` });
                    }
                }
            };
            // 网络错误处理
            xhr.onerror = function () {
                reject({ msg: '网络异常，请检查网络连接' });
            };
            // 发送请求（POST/PUT传JSON字符串，GET不传体）
            if (method === 'GET' || method === 'DELETE') {
                xhr.send();
            } else {
                xhr.send(JSON.stringify(data));
            }
        });
    },

    // GET请求封装
    get(url) {
        return this.request('GET', url);
    },

    // POST请求封装（登录调用的方法）
    post(url, data) {
        return this.request('POST', url, data);
    },

    // PUT请求封装
    put(url, data) {
        return this.request('PUT', url, data);
    },

    // DELETE请求封装
    delete(url) {
        return this.request('DELETE', url);
    }
};