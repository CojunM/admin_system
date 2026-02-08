CREATE DATABASE IF NOT EXISTS admin_system ENCODING 'UTF8' LC_COLLATE 'zh_CN.UTF-8' LC_CTYPE 'zh_CN.UTF-8';
\c admin_system;

-- 权限表（细粒度：页面/按钮/接口）
CREATE TABLE IF NOT EXISTS permissions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) UNIQUE NOT NULL COMMENT '权限标识（如：user:add）',
    name VARCHAR(32) NOT NULL COMMENT '权限名称',
    type TINYINT NOT NULL COMMENT '1-页面 2-按钮 3-接口',
    parent_id INT DEFAULT 0 COMMENT '父权限ID',
    sort INT DEFAULT 0 COMMENT '排序',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 角色表
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(32) UNIQUE NOT NULL COMMENT '角色名称',
    code VARCHAR(64) UNIQUE NOT NULL COMMENT '角色标识',
    desc VARCHAR(255) DEFAULT '' COMMENT '角色描述',
    is_admin TINYINT DEFAULT 0 COMMENT '是否超级管理员 0-否 1-是',
    sort INT DEFAULT 0 COMMENT '排序',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 角色-权限关联表
CREATE TABLE IF NOT EXISTS role_permissions (
    id SERIAL PRIMARY KEY,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    UNIQUE(role_id, permission_id)
);

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(32) UNIQUE NOT NULL COMMENT '用户名',
    password VARCHAR(255) NOT NULL COMMENT '加密密码',
    nickname VARCHAR(32) NOT NULL COMMENT '昵称',
    email VARCHAR(64) DEFAULT '' COMMENT '邮箱',
    phone VARCHAR(11) DEFAULT '' COMMENT '手机号',
    avatar VARCHAR(255) DEFAULT '/static/imgs/avatar-default.png' COMMENT '头像',
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    status TINYINT DEFAULT 1 COMMENT '状态 0-禁用 1-启用',
    last_login_time TIMESTAMP NULL COMMENT '最后登录时间',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 通知表
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    title VARCHAR(128) NOT NULL COMMENT '通知标题',
    content TEXT NOT NULL COMMENT '通知内容',
    type TINYINT DEFAULT 1 COMMENT '1-系统通知 2-业务通知',
    user_id INT NULL REFERENCES users(id) ON DELETE CASCADE COMMENT '指定用户（NULL为全体）',
    is_read TINYINT DEFAULT 0 COMMENT '是否已读 0-未读 1-已读',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 菜单表（前端路由）
CREATE TABLE IF NOT EXISTS menus (
    id SERIAL PRIMARY KEY,
    name VARCHAR(32) NOT NULL COMMENT '菜单名称',
    path VARCHAR(64) NOT NULL COMMENT '路由路径',
    component VARCHAR(128) NOT NULL COMMENT '前端组件路径',
    icon VARCHAR(64) DEFAULT '' COMMENT '菜单图标',
    parent_id INT DEFAULT 0 COMMENT '父菜单ID',
    sort INT DEFAULT 0 COMMENT '排序',
    is_show TINYINT DEFAULT 1 COMMENT '是否显示 0-隐藏 1-显示',
    permission_code VARCHAR(64) DEFAULT '' COMMENT '关联权限标识',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 初始化超级管理员权限、角色、用户
INSERT INTO permissions (code, name, type, parent_id) VALUES 
('*', '所有权限', 1, 0),
('dashboard:view', '仪表盘查看', 1, 1),
('user:manage', '用户管理', 1, 1),
('user:add', '用户添加', 2, 3),
('user:edit', '用户编辑', 2, 3),
('user:delete', '用户删除', 2, 3),
('role:manage', '角色管理', 1, 1),
('permission:manage', '权限管理', 1, 1),
('notify:manage', '通知管理', 1, 1);

INSERT INTO roles (name, code, desc, is_admin) VALUES 
('超级管理员', 'admin', '系统最高权限', 1),
('普通管理员', 'operator', '日常业务管理', 0);

-- 密码：Admin@123（bcrypt加密，盐值固定仅用于初始化，生产环境请修改）
INSERT INTO users (username, password, nickname, role_id, status) VALUES 
('admin', '$2b$12$EixZaYb4xU58Gpq1R0yWbeb00LU5qUaK6x8hP9x0eG6Q8vXQ8hP9x', '系统管理员', 1, 1);

-- 超级管理员关联所有权限
INSERT INTO role_permissions (role_id, permission_id) SELECT 1, id FROM permissions;

-- 初始化系统通知
INSERT INTO notifications (title, content, type) VALUES 
('系统初始化完成', '欢迎使用后台管理系统，初始账号：admin，密码：Admin@123，请及时修改密码！', 1);

-- 初始化菜单
INSERT INTO menus (name, path, component, icon, parent_id, permission_code) VALUES 
('仪表盘', '/dashboard', 'dashboard/index.html', 'fa-solid fa-gauge', 0, 'dashboard:view'),
('用户管理', '/user', 'user/index.html', 'fa-solid fa-user', 0, 'user:manage'),
('角色管理', '/role', 'role/index.html', 'fa-solid fa-shield-halved', 0, 'role:manage'),
('权限管理', '/permission', 'permission/index.html', 'fa-solid fa-key', 0, 'permission:manage'),
('通知管理', '/notify', 'notify/index.html', 'fa-solid fa-bell', 0, 'notify:manage');