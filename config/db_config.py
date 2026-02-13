# config/db_config.py
from core.peewee_orm_single import PostgresqlDatabase, MySQLDatabase

# 选择数据库类型（PostgreSQL/MySQL）
DB_TYPE = "postgresql"

# 通用配置
DB_CONFIG = {
    "database": "admin_system",  # 你的数据库名
    "host": "127.0.0.1",
    "port": 5432,  # PostgreSQL默认5432，MySQL默认3306
    "user": "postgres",
    "password": "postgres",
    "pool_enable": True  # 开启连接池（生产环境建议开启）
}

# 初始化DB实例
if DB_TYPE == "postgresql":
    DB = PostgresqlDatabase(**DB_CONFIG)
elif DB_TYPE == "mysql":
    DB = MySQLDatabase(**DB_CONFIG)
else:
    raise ValueError("不支持的数据库类型")