#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL连接池（新增空闲超时回收，基于psycopg2）
"""
import time
import psycopg2
from psycopg2 import pool
from config.settings import  POOL_MIN_CONN, POOL_MAX_CONN, POOL_IDLE_TIMEOUT


# 全局连接池实例
db_pool = None
# 记录每个连接的最后使用时间（key: 连接对象, value: 最后使用时间戳）
conn_last_used = {}
# 空闲连接检查间隔（设为超时时间的1/5，避免频繁检查）
CHECK_INTERVAL = max(1, POOL_IDLE_TIMEOUT // 5)

def get_db_pool():
    """初始化数据库连接池"""
    global db_pool
    if db_pool is None:
        try:
            db_pool = pool.SimpleConnectionPool(
                minconn=POOL_MIN_CONN,
                maxconn=POOL_MAX_CONN,
                dsn=DATABASE_URL
            )
            if db_pool:
                print(f"数据库连接池初始化成功（最小{POOL_MIN_CONN}，最大{POOL_MAX_CONN}，空闲超时{POOL_IDLE_TIMEOUT}秒）")
                # 启动空闲连接回收守护线程
                start_idle_conn_reaper()
        except Exception as e:
            raise DatabaseError(f"数据库连接池初始化失败：{str(e)}")

def get_db_connection():
    """从连接池获取连接，更新最后使用时间"""
    if db_pool is None:
        init_db_pool()
    try:
        conn = db_pool.getconn()
        conn.autocommit = True  # 自动提交事务
        # 记录/更新连接最后使用时间
        conn_last_used[conn] = time.time()
        return conn
    except Exception as e:
        raise DatabaseError(f"获取数据库连接失败：{str(e)}")

def release_db_connection(conn):
    """释放连接回连接池，更新最后使用时间"""
    if db_pool and conn:
        try:
            db_pool.putconn(conn)
            # 释放时也更新使用时间（避免刚释放就被回收）
            conn_last_used[conn] = time.time()
        except Exception as e:
            print(f"释放数据库连接失败：{str(e)}")

def close_idle_connections():
    """回收超时的空闲连接"""
    if not db_pool or not conn_last_used:
        return
    current_time = time.time()
    idle_conns = []
    # 筛选超时的空闲连接
    for conn, last_used in conn_last_used.items():
        if current_time - last_used > POOL_IDLE_TIMEOUT:
            idle_conns.append(conn)
    # 回收超时连接
    for conn in idle_conns:
        try:
            db_pool.close(conn)  # 关闭超时连接
            del conn_last_used[conn]  # 从记录中移除
            print(f"回收1个超时空闲数据库连接（超时{POOL_IDLE_TIMEOUT}秒）")
        except Exception as e:
            print(f"回收空闲连接失败：{str(e)}")
            del conn_last_used[conn]

def start_idle_conn_reaper():
    """启动守护线程，定时检查并回收空闲连接"""
    import threading
    def reaper_loop():
        while True:
            close_idle_connections()
            time.sleep(CHECK_INTERVAL)
    # 设为守护线程：主程序退出时自动终止，无需手动关闭
    reaper_thread = threading.Thread(target=reaper_loop, daemon=True)
    reaper_thread.start()
    print(f"空闲连接回收守护线程已启动（检查间隔{CHECK_INTERVAL}秒）")

def close_db_pool():
    """关闭连接池（程序退出时调用）"""
    if db_pool:
        try:
            db_pool.closeall()
            conn_last_used.clear()  # 清空连接记录
            print("数据库连接池已关闭，所有连接释放完成")
        except Exception as e:
            print(f"关闭数据库连接池失败：{str(e)}")