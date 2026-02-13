from core.peewee_orm_single1_1 import Model,PostgresqlDatabase
from config.settings import DB_CONFIG

DB = PostgresqlDatabase(
    database=DB_CONFIG["database"],
    host=DB_CONFIG["host"],
    port=DB_CONFIG["port"],
    user=DB_CONFIG["user"],
    password=DB_CONFIG["password"],
    pool_enable=DB_CONFIG["pool_enable"],  # 核心修复：测试阶段关闭连接池
)

class BaseModel(Model):
    class Meta:
        database = DB
