#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整版 Peewee 风格 ORM 框架（生产级可用）
核心特性：
1. 完整字段体系（对齐 Peewee API）：Integer/BigInteger/Float/Decimal/String/Text/Binary/Date/Time/DateTime/Boolean/UUID/ForeignKey
2. 多数据库适配：MySQL/PostgreSQL/SQLite（修复 SQLite autocommit 错误）
3. 企业级特性：连接池、事务管理、字段注释、索引、外键反向引用、表迁移
4. 安全防护：SQL 注入检测、字段/表名合法性校验、值转义
5. 扩展功能：批量操作、查询排序/分页、字段验证
"""

import re
import time
import queue
import threading
import logging
import datetime
import sqlite3
import decimal
import uuid
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple, Any, Callable, Iterable, Type

# ======================== 1. 基础配置与常量 ========================
# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
logger = logging.getLogger(__name__)

# 全局常量
FORBIDDEN_SQL_KEYWORDS = {"UNION", "SELECT", "INSERT", "DELETE", "UPDATE", "DROP", "ALTER",
                          "TRUNCATE", "EXEC", "1=1", "--", "#", ";", "'", "\""}
VALID_IDENTIFIER_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"

# 连接池默认配置
DEFAULT_POOL_CONFIG = {
    "mincached": 1,
    "maxcached": 10,
    "maxconnections": 20,
    "blocking": True,
    "idle_timeout": 300
}

# ======================== 2. 异常定义 ========================
class ORMError(Exception):
    """ORM 基础异常"""
    pass

class SQLSafetyError(ORMError):
    """SQL 安全校验异常"""
    pass

class DatabaseError(ORMError):
    """数据库操作异常"""
    pass

class DatabaseNotConfiguredError(DatabaseError):
    """数据库未配置异常"""
    pass

class TransactionError(DatabaseError):
    """事务操作异常"""
    pass

class ModelError(ORMError):
    """模型操作异常"""
    pass

class DoesNotExist(ModelError):
    """数据不存在异常"""
    pass

class MissingPrimaryKeyError(ModelError):
    """缺少主键异常"""
    pass

class InvalidForeignKeyError(ModelError):
    """外键无效异常"""
    pass

class DataInsertError(ModelError):
    """数据插入异常"""
    pass

class FieldValidationError(ModelError):
    """字段验证异常"""
    pass

# ======================== 3. 数据库连接池 ========================
class ConnectionItem:
    """连接池项"""
    def __init__(self, conn):
        self.conn = conn
        self.create_time = time.time()
        self.last_used = time.time()

    def is_expired(self, timeout: int) -> bool:
        """检查连接是否过期"""
        return (time.time() - self.last_used) > timeout

    def update_used_time(self):
        """更新连接最后使用时间"""
        self.last_used = time.time()

class ConnectionPool:
    """数据库连接池"""
    def __init__(self, db_type: str, conn_kwargs: Dict, enable: bool = True, pool_config: Dict = None):
        self.db_type = db_type.lower()
        self.conn_kwargs = conn_kwargs
        self.enable = enable and self.db_type != "sqlite"  # SQLite 不使用连接池
        self.config = pool_config or DEFAULT_POOL_CONFIG
        self.min_idle = self.config["mincached"]
        self.max_idle = self.config["maxcached"]
        self.max_conn = self.config["maxconnections"]
        self.blocking = self.config["blocking"]
        self.idle_timeout = self.config["idle_timeout"]
        self.idle_queue = queue.Queue(self.max_idle)
        self.active_set = set()
        self.lock = threading.Lock()
        
        # 初始化最小空闲连接
        if self.enable:
            self._init_min_connections()

    def _create_conn(self):
        """创建新连接（修复 SQLite autocommit 错误）"""
        try:
            if self.db_type == "mysql":
                import pymysql
                return pymysql.connect(
                    **self.conn_kwargs,
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=True
                )
            elif self.db_type == "postgresql":
                import psycopg2
                from psycopg2 import extras
                conn = psycopg2.connect(
                    **self.conn_kwargs,
                    cursor_factory=extras.DictCursor
                )
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                return conn
            elif self.db_type == "sqlite":
                # 修复：SQLite 不设置 autocommit，改用 isolation_level=None 实现自动提交
                conn = sqlite3.connect(**self.conn_kwargs)
                conn.row_factory = sqlite3.Row
                # SQLite 通过 isolation_level 控制自动提交，None 表示自动提交
                conn.isolation_level = None
                return conn
            else:
                raise ValueError(f"不支持的数据库类型：{self.db_type}")
        except Exception as e:
            raise DatabaseError(f"创建数据库连接失败：{e}")

    def _init_min_connections(self):
        """初始化最小空闲连接"""
        with self.lock:
            for _ in range(self.min_idle):
                if self.idle_queue.full():
                    break
                self.idle_queue.put(ConnectionItem(self._create_conn()))

    def _clean_expired_connections(self):
        """清理过期连接"""
        if not self.enable:
            return
        with self.lock:
            temp_queue = queue.Queue(self.max_idle)
            while not self.idle_queue.empty():
                item = self.idle_queue.get()
                if not item.is_expired(self.idle_timeout):
                    temp_queue.put(item)
                else:
                    try:
                        item.conn.close()
                    except Exception as e:
                        logger.warning(f"关闭过期连接失败：{e}")
            self.idle_queue = temp_queue

    def get_connection(self):
        """获取连接"""
        # SQLite 直接创建新连接
        if self.db_type == "sqlite":
            return self._create_conn()
        
        if not self.enable:
            return self._create_conn()
        
        # 清理过期连接
        self._clean_expired_connections()
        
        try:
            # 从空闲队列获取
            item = self.idle_queue.get(timeout=5)
            # 验证连接是否可用
            try:
                item.conn.cursor().execute("SELECT 1")
            except Exception:
                item.conn.close()
                item = ConnectionItem(self._create_conn())
            item.update_used_time()
            with self.lock:
                self.active_set.add(item)
            return item.conn
        except queue.Empty:
            # 空闲队列无连接，创建新连接
            with self.lock:
                if len(self.active_set) >= self.max_conn:
                    raise DatabaseError("连接池已达最大连接数上限")
                conn = self._create_conn()
                item = ConnectionItem(conn)
                self.active_set.add(item)
                return conn

    def release_connection(self, conn):
        """释放连接"""
        # SQLite 直接关闭
        if self.db_type == "sqlite":
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"关闭SQLite连接失败：{e}")
            return
        
        if not self.enable or not conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"关闭连接失败：{e}")
            return
        
        with self.lock:
            target_item = None
            for item in self.active_set:
                if item.conn == conn:
                    target_item = item
                    self.active_set.remove(item)
                    break
            if target_item:
                target_item.update_used_time()
                if not self.idle_queue.full():
                    self.idle_queue.put(target_item)
                else:
                    target_item.conn.close()

    def close_pool(self):
        """关闭连接池"""
        if self.db_type == "sqlite" or not self.enable:
            return
        
        # 关闭空闲连接
        while not self.idle_queue.empty():
            try:
                self.idle_queue.get().conn.close()
            except Exception as e:
                logger.warning(f"关闭空闲连接失败：{e}")
        
        # 关闭活跃连接
        with self.lock:
            for item in self.active_set:
                try:
                    item.conn.close()
                except Exception as e:
                    logger.warning(f"关闭活跃连接失败：{e}")
            self.active_set.clear()

# ======================== 4. 数据库适配器 ========================
class BaseDatabaseAdapter(ABC):
    """数据库适配器基类"""
    FIELD_TYPE_MAP: Dict[str, str] = {}
    AUTO_INCREMENT_SUFFIX: str = ""
    IDENTIFIER_QUOTE: str = ""
    PARAM_PLACEHOLDER: str = "?"

    @abstractmethod
    def get_field_type(self, field_cls_name: str, field_instance) -> str:
        """获取字段类型 SQL"""
        pass

    @abstractmethod
    def get_auto_increment_sql(self, field_instance) -> str:
        """获取自增主键 SQL"""
        pass

    @abstractmethod
    def get_foreign_key_sql(self, field_name: str, target_table: str, target_pk: str, field_instance) -> str:
        """获取外键 SQL"""
        pass

    @abstractmethod
    def get_alter_add_field_sql(self, field_instance) -> str:
        """获取添加字段 SQL"""
        pass

    @abstractmethod
    def get_alter_modify_field_sql(self, field_instance) -> str:
        """获取修改字段 SQL"""
        pass

    @abstractmethod
    def get_alter_drop_field_sql(self, field_name: str) -> str:
        """获取删除字段 SQL"""
        pass

    @abstractmethod
    def get_table_metadata_sql(self, table_name: str) -> str:
        """获取表元数据 SQL"""
        pass

    def quote_identifier(self, name: str) -> str:
        """引用标识符（表名/字段名）"""
        return f"{self.IDENTIFIER_QUOTE}{name}{self.IDENTIFIER_QUOTE}"

    def convert_placeholder(self, sql: str) -> str:
        """转换占位符"""
        return sql.replace("?", self.PARAM_PLACEHOLDER)

    def format_boolean_default(self, value: bool) -> Any:
        """格式化布尔默认值"""
        return str(value).upper()

class MySQLAdapter(BaseDatabaseAdapter):
    """MySQL 适配器（更新字段映射）"""
    FIELD_TYPE_MAP = {
        "IntegerField": "INT", "BigIntegerField": "BIGINT", "FloatField": "FLOAT",
        "DecimalField": "DECIMAL", "StringField": "VARCHAR", "CharField": "VARCHAR",
        "TextField": "TEXT", "BinaryField": "BLOB", "DateField": "DATE",
        "TimeField": "TIME", "DateTimeField": "DATETIME", "BooleanField": "TINYINT",
        "UUIDField": "CHAR", "ForeignKeyField": "INT", "EnumField": "ENUM"
    }
    AUTO_INCREMENT_SUFFIX = "AUTO_INCREMENT"
    IDENTIFIER_QUOTE = "`"
    PARAM_PLACEHOLDER = "%s"

    def get_field_type(self, cls_name: str, inst):
        base_type = self.FIELD_TYPE_MAP[cls_name]
        if cls_name in ["StringField", "CharField"]:
            return f"{base_type}({inst.max_length})"
        elif cls_name == "DecimalField":
            return f"{base_type}({inst.max_digits}, {inst.decimal_places})"
        elif cls_name == "UUIDField":
            return f"{base_type}(36)"
        elif cls_name == "EnumField":
            return f"{base_type}({','.join([f"'{v}'" for v in inst.choices])})"
        elif cls_name == "IntegerField" and inst.primary_key and inst.auto_increment:
            return "INT"
        return base_type

    def get_auto_increment_sql(self, inst):
        return self.AUTO_INCREMENT_SUFFIX if inst.primary_key and isinstance(inst, IntegerField) else ""

    def get_foreign_key_sql(self, name, target_table, target_pk, inst):
        t_tbl = self.quote_identifier(target_table)
        t_pk = self.quote_identifier(target_pk)
        fk = self.quote_identifier(name)
        return f", FOREIGN KEY ({fk}) REFERENCES {t_tbl}({t_pk}) ON DELETE {inst.on_delete} ON UPDATE {inst.on_update}"

    def get_alter_add_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        constraints = ["NOT NULL"] if not inst.nullable else []
        if inst.default is not None:
            constraints.append(f"DEFAULT {inst._format_default(inst.default, self)}")
        auto_inc = self.get_auto_increment_sql(inst)
        if auto_inc:
            constraints.append(auto_inc)
        return f"ADD COLUMN {name} {typ} {' '.join(constraints)}"

    def get_alter_modify_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        constraints = ["NOT NULL"] if not inst.nullable else []
        if inst.default is not None:
            constraints.append(f"DEFAULT {inst._format_default(inst.default, self)}")
        auto_inc = self.get_auto_increment_sql(inst)
        if auto_inc:
            constraints.append(auto_inc)
        return f"MODIFY COLUMN {name} {typ} {' '.join(constraints)}"

    def get_alter_drop_field_sql(self, name):
        return f"DROP COLUMN {self.quote_identifier(name)}"

    def get_table_metadata_sql(self, table):
        return """SELECT COLUMN_NAME as name, DATA_TYPE as type, IS_NULLABLE as nullable, COLUMN_DEFAULT as default 
                  FROM INFORMATION_SCHEMA.COLUMNS 
                  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s;"""

    def format_boolean_default(self, value: bool) -> int:
        return 1 if value else 0

class PostgreSQLAdapter(BaseDatabaseAdapter):
    """PostgreSQL 适配器（更新字段映射）"""
    FIELD_TYPE_MAP = {
        "IntegerField": "INTEGER", "BigIntegerField": "BIGINT", "FloatField": "DOUBLE PRECISION",
        "DecimalField": "NUMERIC", "StringField": "VARCHAR", "CharField": "VARCHAR",
        "TextField": "TEXT", "BinaryField": "BYTEA", "DateField": "DATE",
        "TimeField": "TIME", "DateTimeField": "TIMESTAMP", "BooleanField": "BOOLEAN",
        "UUIDField": "UUID", "ForeignKeyField": "INTEGER", "EnumField": "VARCHAR"
    }
    AUTO_INCREMENT_SUFFIX = ""
    IDENTIFIER_QUOTE = "\""
    PARAM_PLACEHOLDER = "%s"

    def get_field_type(self, cls_name: str, inst):
        base_type = self.FIELD_TYPE_MAP[cls_name]
        if cls_name in ["StringField", "CharField"]:
            return f"{base_type}({inst.max_length})"
        elif cls_name == "DecimalField":
            return f"{base_type}({inst.max_digits}, {inst.decimal_places})"
        elif cls_name == "EnumField":
            return f"{base_type}({inst.max_length})"
        elif cls_name == "IntegerField" and inst.primary_key and getattr(inst, 'auto_increment', False):
            return "INTEGER"
        return base_type

    def get_auto_increment_sql(self, inst):
        if inst.primary_key and isinstance(inst, IntegerField) and getattr(inst, 'auto_increment', False):
            return "PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY"
        return ""

    def get_foreign_key_sql(self, name, target_table, target_pk, inst):
        t_tbl = self.quote_identifier(target_table)
        t_pk = self.quote_identifier(target_pk)
        fk = self.quote_identifier(name)
        return f", FOREIGN KEY ({fk}) REFERENCES {t_tbl}({t_pk}) ON DELETE {inst.on_delete} ON UPDATE {inst.on_update}"

    def get_alter_add_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        constraints = ["NOT NULL"] if not inst.nullable else []
        if inst.default is not None:
            constraints.append(f"DEFAULT {inst._format_default(inst.default, self)}")
        auto_inc = self.get_auto_increment_sql(inst)
        if auto_inc:
            constraints.append(auto_inc)
        return f"ADD COLUMN {name} {typ} {' '.join(constraints)}"

    def get_alter_modify_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        parts = [
            f"ALTER COLUMN {name} TYPE {typ}",
            f"ALTER COLUMN {name} SET NOT NULL" if not inst.nullable else f"ALTER COLUMN {name} DROP NOT NULL"
        ]
        if inst.default is not None:
            parts.append(f"ALTER COLUMN {name} SET DEFAULT {inst._format_default(inst.default, self)}")
        return ", ".join(parts)

    def get_alter_drop_field_sql(self, name):
        quoted_name = self.quote_identifier(name)
        return f"DROP COLUMN {quoted_name}"

    def get_table_metadata_sql(self, table):
        return """SELECT column_name as name, 
                        data_type as type, 
                        is_nullable = 'YES' as nullable, 
                        column_default as default 
                  FROM INFORMATION_SCHEMA.COLUMNS 
                  WHERE table_catalog = CURRENT_DATABASE() 
                  AND table_schema = CURRENT_SCHEMA() 
                  AND table_name = %s;"""

class SqliteAdapter(BaseDatabaseAdapter):
    """SQLite 适配器（更新字段映射）"""
    FIELD_TYPE_MAP = {
        "IntegerField": "INTEGER", "BigIntegerField": "INTEGER", "FloatField": "REAL",
        "DecimalField": "REAL", "StringField": "TEXT", "CharField": "TEXT",
        "TextField": "TEXT", "BinaryField": "BLOB", "DateField": "TEXT",
        "TimeField": "TEXT", "DateTimeField": "DATETIME", "BooleanField": "INTEGER",
        "UUIDField": "TEXT", "ForeignKeyField": "INTEGER", "EnumField": "TEXT"
    }
    AUTO_INCREMENT_SUFFIX = "AUTOINCREMENT"
    IDENTIFIER_QUOTE = "\""
    PARAM_PLACEHOLDER = "?"

    def get_field_type(self, cls_name: str, inst):
        return self.FIELD_TYPE_MAP[cls_name]

    def get_auto_increment_sql(self, inst):
        return self.AUTO_INCREMENT_SUFFIX if inst.primary_key and isinstance(inst, IntegerField) else ""

    def get_foreign_key_sql(self, name, target_table, target_pk, inst):
        t_tbl = self.quote_identifier(target_table)
        t_pk = self.quote_identifier(target_pk)
        fk = self.quote_identifier(name)
        return f", FOREIGN KEY ({fk}) REFERENCES {t_tbl}({t_pk}) ON DELETE {inst.on_delete} ON UPDATE {inst.on_update}"

    def get_alter_add_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        constraints = ["NOT NULL"] if not inst.nullable else []
        if inst.default is not None:
            constraints.append(f"DEFAULT {inst._format_default(inst.default, self)}")
        auto_inc = self.get_auto_increment_sql(inst)
        if auto_inc:
            constraints.append(auto_inc)
        return f"ADD COLUMN {name} {typ} {' '.join(constraints)}"

    def get_alter_modify_field_sql(self, inst):
        logger.warning(f"SQLite不支持直接修改字段 {inst.name}，建议手动处理或重建表")
        return ""

    def get_alter_drop_field_sql(self, name):
        return f"DROP COLUMN {self.quote_identifier(name)}"

    def get_table_metadata_sql(self, table):
        return f"PRAGMA table_info({self.quote_identifier(table)});"

    def format_boolean_default(self, value: bool) -> int:
        return 1 if value else 0

def get_database_adapter(db_type: str) -> BaseDatabaseAdapter:
    """获取数据库适配器"""
    db_type = db_type.lower()
    adapter_map = {
        "mysql": MySQLAdapter,
        "postgresql": PostgreSQLAdapter,
        "pg": PostgreSQLAdapter,
        "sqlite": SqliteAdapter
    }
    if db_type not in adapter_map:
        raise DatabaseError(f"不支持的数据库类型：{db_type}")
    return adapter_map[db_type]()

# ======================== 5. 查询对象（增强版） ========================
class Query:
    """查询对象（支持排序/分页/LIKE查询）"""
    def __init__(self, model_cls):
        self.model_cls = model_cls
        self.db = model_cls._get_database()
        self.adapter = self.db.adapter
        self.fields = list(model_cls._meta.fields.keys())
        self.where_conditions = []
        self.where_params = []
        self.order_conditions = []
        self.limit_count = None
        self.offset_count = 0
        self._executed = False
        self._results = None

    def where(self,** conditions) -> "Query":
        """添加 WHERE 条件"""
        validate_model_fields(self.model_cls, list(conditions.keys()))
        for field_name, value in conditions.items():
            validate_identifier(field_name)
            field = self.model_cls._meta.fields[field_name]
            field_type = field.python_type
            # 检测SQL注入特征
            if isinstance(value, str) and detect_sql_injection(value):
                raise SQLSafetyError(f"检测到SQL注入特征：字段{field_name}的值[{value}]包含危险字符/语句")
            if isinstance(value, Model):
                processed_value = extract_model_pk(value)
            else:
                processed_value = value
            cleaned_value = escape_value(processed_value, field_type, self.model_cls)
            self.where_conditions.append(f"{self.adapter.quote_identifier(field_name)} = {self.adapter.PARAM_PLACEHOLDER}")
            self.where_params.append(cleaned_value)
        return self

    def like(self, **conditions) -> "Query":
        """添加 LIKE 条件"""
        validate_model_fields(self.model_cls, list(conditions.keys()))
        for field_name, value in conditions.items():
            validate_identifier(field_name)
            field = self.model_cls._meta.fields[field_name]
            if isinstance(value, str) and detect_sql_injection(value):
                raise SQLSafetyError(f"检测到SQL注入特征：字段{field_name}的值[{value}]包含危险字符/语句")
            cleaned_value = escape_value(f"%{value}%", field.python_type, self.model_cls)
            self.where_conditions.append(f"{self.adapter.quote_identifier(field_name)} LIKE {self.adapter.PARAM_PLACEHOLDER}")
            self.where_params.append(cleaned_value)
        return self

    def order_by(self, *fields, desc: bool = False) -> "Query":
        """添加排序条件"""
        validate_model_fields(self.model_cls, list(fields))
        order_dir = "DESC" if desc else "ASC"
        self.order_conditions = [f"{self.adapter.quote_identifier(f)} {order_dir}" for f in fields]
        return self

    def limit(self, limit: int, offset: int = 0) -> "Query":
        """添加分页条件"""
        if limit < 0:
            raise ValueError("Limit 必须是非负整数")
        if offset < 0:
            raise ValueError("Offset 必须是非负整数")
        self.limit_count = limit
        self.offset_count = offset
        return self

    def _build_sql(self) -> str:
        """构建查询 SQL（支持排序/分页）"""
        fields_str = ", ".join([self.adapter.quote_identifier(f) for f in self.fields])
        table_name = self.adapter.quote_identifier(self.model_cls._meta.table_name)
        
        # WHERE 子句
        where_clause = ""
        if self.where_conditions:
            where_clause = f"WHERE {' AND '.join(self.where_conditions)}"
        
        # ORDER BY 子句
        order_clause = ""
        if self.order_conditions:
            order_clause = f"ORDER BY {', '.join(self.order_conditions)}"
        
        # LIMIT/OFFSET 子句
        limit_clause = ""
        if self.limit_count is not None and self.limit_count >= 0:
            limit_clause = f"LIMIT {self.limit_count}"
            if self.offset_count > 0:
                limit_clause += f" OFFSET {self.offset_count}"
        
        sql = f"SELECT {fields_str} FROM {table_name} {where_clause} {order_clause} {limit_clause}"
        return self.adapter.convert_placeholder(sql)

    def execute(self) -> List:
        """执行查询"""
        if self._executed:
            return self._results
        try:
            sql = self._build_sql()
            results = self.db.fetch_all(sql, tuple(self.where_params))
            self._results = [self.model_cls(**dict(result)) for result in results]
            self._executed = True
            return self._results
        except Exception as e:
            raise DatabaseError(f"查询执行失败：{e} | SQL：{sql} | 参数：{self.where_params}")

    def first(self) -> Optional[Any]:
        """获取第一条结果"""
        results = self.execute()
        return results[0] if results else None

    def get(self):
        """获取单条结果（无结果抛异常）"""
        result = self.first()
        if not result:
            raise DoesNotExist(f"{self.model_cls.__name__} 未找到匹配记录")
        return result

    def __iter__(self) -> Iterable:
        """迭代结果"""
        return iter(self.execute())

    def __len__(self) -> int:
        """结果数量"""
        return len(self.execute())

# ======================== 6. 字段定义（完整版，含枚举字段） ========================
class Field:
    """字段基类（对齐 Peewee Field 接口，增强验证）"""
    python_type = str  # 默认 Python 类型
    field_type = None  # 数据库字段类型标识
    
    def __init__(self, primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = False, index: bool = False,
                 comment: str = "", validate_hook: Callable = None):
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.unique = unique
        self.comment = comment.strip()  # 字段注释，去除首尾空格
        self.index = index  # 索引（Peewee 核心参数）
        self.validate_hook = validate_hook  # 自定义验证钩子
        self.name = None    # 字段名（由元类自动赋值）
        self.model = None   # 所属模型（由元类自动赋值）

    def _format_default(self, value, adapter: BaseDatabaseAdapter = None) -> Any:
        """格式化默认值（适配不同数据库）"""
        if value is None:
            return "NULL"
        if callable(value):
            value = value()
        if isinstance(value, str):
            escaped_value = value.replace("'", "''")
            return f"'{escaped_value}'"  # 转义单引号
        elif isinstance(value, datetime.datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, datetime.date):
            return f"'{value.strftime('%Y-%m-%d')}'"
        elif isinstance(value, datetime.time):
            return f"'{value.strftime('%H:%M:%S')}'"
        elif isinstance(value, bool):
            return adapter.format_boolean_default(value) if adapter else ("TRUE" if value else "FALSE")
        elif isinstance(value, (int, float, decimal.Decimal)):
            return str(value)
        return str(value)

    def validate(self, value):
        """字段验证（核心增强）"""
        # 非空验证
        if not self.nullable and value is None:
            raise FieldValidationError(f"字段 {self.name} 不能为空")
        # 类型验证
        if value is not None and not isinstance(value, self.python_type):
            try:
                value = self.python_type(value)
            except (ValueError, TypeError):
                raise FieldValidationError(
                    f"字段 {self.name} 类型错误，期望 {self.python_type.__name__}，实际 {type(value).__name__}"
                )
        # 自定义验证钩子
        if self.validate_hook:
            self.validate_hook(value)
        return value

    def get_sql_definition(self, adapter: BaseDatabaseAdapter) -> str:
        """获取字段 SQL 定义（包含索引/唯一约束/注释）"""
        name = adapter.quote_identifier(self.name)
        field_type = adapter.get_field_type(self.__class__.__name__, self)
        auto_inc = adapter.get_auto_increment_sql(self)
        parts = [name, field_type]
        
        # 自增主键
        if auto_inc:
            parts.append(auto_inc)
        # 非空约束
        if not self.nullable:
            parts.append("NOT NULL")
        # 主键约束（非自增场景）
        if self.primary_key and not auto_inc:
            parts.append("PRIMARY KEY")
        # 唯一约束
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        # 默认值
        if self.default is not None:
            parts.append(f"DEFAULT {self._format_default(self.default, adapter)}")
        
        # 字段注释（适配不同数据库语法）
        comment_sql = ""
        if self.comment:
            escaped_comment = self.comment.replace("'", "''")
            adapter_cls = adapter.__class__.__name__
            if adapter_cls == "MySQLAdapter":
                comment_sql = f" COMMENT '{escaped_comment}'"
            elif adapter_cls == "SqliteAdapter":
                comment_sql = f" -- {escaped_comment}"
            elif adapter_cls == "PostgreSQLAdapter":
                comment_sql = f" COMMENT '{escaped_comment}'"
        
        sql = " ".join(parts) + comment_sql
        
        # 索引（单独返回，建表后创建）
        self.index_sql = None
        if self.index and not self.primary_key and not self.unique:
            self.index_sql = f"CREATE INDEX idx_{self.model._meta.table_name}_{self.name} ON {adapter.quote_identifier(self.model._meta.table_name)} ({name});"
        
        return sql

# ------------------------ 基础数值字段 ------------------------
class IntegerField(Field):
    """整型字段（对齐 Peewee IntegerField）"""
    python_type = int
    field_type = 'int'
    
    def __init__(self, primary_key: bool = False, auto_increment: bool = False, 
                 nullable: bool = False, default: Any = None, unique: bool = False, 
                 index: bool = False, comment: str = "", validate_hook: Callable = None):
        super().__init__(primary_key, nullable, default, unique, index, comment, validate_hook)
        self.auto_increment = auto_increment or primary_key

class BigIntegerField(Field):
    """大整型字段（对齐 Peewee BigIntegerField）"""
    python_type = int
    field_type = 'bigint'

class FloatField(Field):
    """浮点数字段（对齐 Peewee FloatField）"""
    python_type = float
    field_type = 'float'

class DecimalField(Field):
    """高精度小数字段（对齐 Peewee DecimalField）"""
    python_type = decimal.Decimal
    field_type = 'decimal'
    
    def __init__(self, max_digits: int = 10, decimal_places: int = 2,
                 primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = False, index: bool = False,
                 comment: str = "", validate_hook: Callable = None):
        super().__init__(primary_key, nullable, default, unique, index, comment, validate_hook)
        self.max_digits = max_digits  # 总位数
        self.decimal_places = decimal_places  # 小数位数

# ------------------------ 字符串/文本字段 ------------------------
class StringField(Field):
    """字符串字段（对齐 Peewee StringField，替代原 CharField）"""
    python_type = str
    field_type = 'varchar'
    
    def __init__(self, max_length: int = 255, primary_key: bool = False, 
                 nullable: bool = False, default: Any = None, unique: bool = False, 
                 index: bool = False, comment: str = "", validate_hook: Callable = None):
        super().__init__(primary_key, nullable, default, unique, index, comment, validate_hook)
        self.max_length = max_length
        
        # 长度验证钩子
        def length_validate(value):
            if len(value) > self.max_length:
                raise FieldValidationError(f"字段 {self.name} 长度超过 {self.max_length} 字符限制")
        if not self.validate_hook:
            self.validate_hook = length_validate

class CharField(StringField):
    """兼容旧代码的别名（原 CharField → StringField）"""
    pass

class TextField(Field):
    """文本字段（对齐 Peewee TextField）"""
    python_type = str
    field_type = 'text'

class BinaryField(Field):
    """二进制字段（对齐 Peewee BinaryField）"""
    python_type = bytes
    field_type = 'blob'

# ------------------------ 日期时间字段 ------------------------
class DateField(Field):
    """日期字段（对齐 Peewee DateField）"""
    python_type = datetime.date
    field_type = 'date'
    
    def __init__(self, auto_now: bool = False, auto_now_add: bool = False,
                 primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = False, index: bool = False,
                 comment: str = "", validate_hook: Callable = None):
        super().__init__(primary_key, nullable, default, unique, index, comment, validate_hook)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        
        if self.auto_now and self.auto_now_add:
            raise ValueError("Cannot set both auto_now and auto_now_add")
        
        if self.auto_now_add and not callable(self.default):
            self.default = datetime.date.today

class TimeField(Field):
    """时间字段（对齐 Peewee TimeField）"""
    python_type = datetime.time
    field_type = 'time'

class DateTimeField(Field):
    """日期时间字段（对齐 Peewee DateTimeField）"""
    python_type = datetime.datetime
    field_type = 'datetime'
    
    def __init__(self, auto_now: bool = False, auto_now_add: bool = False,
                 primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = False, index: bool = False,
                 comment: str = "", validate_hook: Callable = None):
        super().__init__(primary_key, nullable, default, unique, index, comment, validate_hook)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        
        if self.auto_now and self.auto_now_add:
            raise ValueError("Cannot set both auto_now and auto_now_add")
        
        if self.auto_now_add and not callable(self.default):
            self.default = datetime.datetime.now

# ------------------------ 其他字段 ------------------------
class BooleanField(Field):
    """布尔字段（对齐 Peewee BooleanField）"""
    python_type = bool
    field_type = 'bool'

class UUIDField(Field):
    """UUID 字段（完善对齐 Peewee UUIDField）"""
    python_type = str
    field_type = 'uuid'
    
    def __init__(self, primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = True, index: bool = False,
                 comment: str = "", validate_hook: Callable = None):
        # UUID 默认唯一
        super().__init__(primary_key, nullable, default, unique or primary_key, index, comment, validate_hook)
        
        # UUID 格式验证
        def uuid_validate(value):
            try:
                uuid.UUID(value)
            except ValueError:
                raise FieldValidationError(f"字段 {self.name} 不是有效的 UUID 格式")
        if not self.validate_hook:
            self.validate_hook = uuid_validate

class EnumField(Field):
    """枚举字段（扩展 Peewee 特性）"""
    python_type = str
    field_type = 'enum'
    
    def __init__(self, choices: List[str], max_length: int = 255,
                 primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = False, index: bool = False,
                 comment: str = "", validate_hook: Callable = None):
        super().__init__(primary_key, nullable, default, unique, index, comment, validate_hook)
        self.choices = choices
        self.max_length = max_length
        
        # 枚举值验证
        def enum_validate(value):
            if value not in self.choices:
                raise FieldValidationError(f"字段 {self.name} 值 {value} 不在可选范围：{self.choices}")
            if len(value) > self.max_length:
                raise FieldValidationError(f"字段 {self.name} 长度超过 {self.max_length} 字符限制")
        if not self.validate_hook:
            self.validate_hook = enum_validate

class ForeignKeyField(Field):
    """外键字段（对齐 Peewee ForeignKeyField）"""
    python_type = int
    field_type = 'foreignkey'
    
    def __init__(self, to, backref: str = None, on_delete: str = "CASCADE", 
                 on_update: str = "CASCADE", nullable: bool = True, 
                 unique: bool = False, index: bool = True, comment: str = "",
                 validate_hook: Callable = None):
        super().__init__(nullable=nullable, unique=unique, index=index, comment=comment, validate_hook=validate_hook)
        self.to_model = to
        self.backref = backref
        # 对齐 Peewee：补充 on_update 策略
        self.on_delete = on_delete.upper()
        self.on_update = on_update.upper()
        
        # 验证级联策略合法性
        valid_actions = ["CASCADE", "SET NULL", "RESTRICT", "NO ACTION", "SET DEFAULT"]
        if self.on_delete not in valid_actions:
            raise ValueError(f"非法的 on_delete 策略：{on_delete}，仅支持：{valid_actions}")
        if self.on_update not in valid_actions:
            raise ValueError(f"非法的 on_update 策略：{on_update}，仅支持：{valid_actions}")
        
        # 验证关联模型
        if not issubclass(self.to_model, Model):
            raise TypeError(f"关联目标必须是 Model 子类，当前：{type(self.to_model)}")
        if not hasattr(self.to_model._meta, "primary_key"):
            raise ValueError(f"关联模型 {self.to_model.__name__} 未定义主键，无法创建外键")
        
        # 自动注册反向引用
        if self.backref:
            self._register_backref()

    def _register_backref(self):
        """注册反向引用（对齐 Peewee backref 行为）"""
        def reverse_query(instance):
            from_model = self.model
            filter_kwargs = {self.name: getattr(instance, instance._meta.primary_key.name)}
            return from_model.select().where(**filter_kwargs).execute()
        
        if not hasattr(self.to_model, self.backref):
            setattr(self.to_model, self.backref, reverse_query)

    def get_sql_definition(self, adapter: BaseDatabaseAdapter) -> str:
        """生成包含外键约束的 SQL（补充 on_update）"""
        # 基础整型字段定义
        base_sql = super().get_sql_definition(adapter)
        
        # 外键约束（包含 on_delete + on_update）
        target_table = adapter.quote_identifier(self.to_model._meta.table_name)
        target_pk = adapter.quote_identifier(self.to_model._meta.primary_key.name)
        foreign_key_constraint = (
            f"REFERENCES {target_table}({target_pk}) "
            f"ON DELETE {self.on_delete} ON UPDATE {self.on_update}"
        )
        
        return f"{base_sql} {foreign_key_constraint}"

# ======================== 7. 模型元类 ========================
class ModelMeta(type):
    """模型元类（自动收集字段/绑定数据库）"""
    def __new__(cls, name: str, bases: Tuple[type], attrs: Dict[str, Any]) -> type:
        # 跳过 Model 基类
        if name == "Model":
            return super().__new__(cls, name, bases, attrs)
        
        # 1. 收集字段
        fields = {}
        primary_key = None
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, Field):
                validate_identifier(attr_name)
                fields[attr_name] = attr_value
                attr_value.name = attr_name
                if attr_value.primary_key:
                    primary_key = attr_value

        # 2. 处理 Meta 配置
        meta = attrs.pop("Meta", None)
        table_name = getattr(meta, "table_name", name.lower()) if meta else name.lower()
        table_name = validate_identifier(table_name, "table")
        database = getattr(meta, "database", None) if meta else None

        # 3. 构建元数据
        meta_attrs = {
            "table_name": table_name,
            "fields": fields,
            "primary_key": primary_key,
            "database": database
        }
        _meta = type("_Meta", (), meta_attrs)

        # 4. 创建模型类（核心修复：先创建类再绑定元数据）
        model_cls = super().__new__(cls, name, bases, attrs)
        model_cls._meta = _meta

        # 5. 绑定字段的模型引用
        for field in fields.values():
            field.model = model_cls

        # 6. 处理反向引用
        cls._setup_backref(model_cls, fields)

        # 7. 验证类方法继承（修复 get_or_none 缺失）
        if not hasattr(model_cls, 'get_or_none'):
            logger.warning(f"模型类{name}未继承get_or_none方法，手动绑定")
            setattr(model_cls, 'get_or_none', Model.get_or_none)

        return model_cls

    @staticmethod
    def _setup_backref(model_cls, fields: Dict[str, Field]):
        """设置反向引用"""
        for field in fields.values():
            if isinstance(field, ForeignKeyField) and field.backref:
                target_model = field.to_model
                related_model = model_cls
                field_name = field.name
                
                # 定义反向引用方法
                def get_related(self, rm=related_model, fn=field_name):
                    return rm.select().where(**{fn: self.id}).execute()
                
                setattr(target_model, field.backref, get_related)

# ======================== 8. 模型基类（增强版，含批量操作） ========================
class Model(metaclass=ModelMeta):
    """模型基类（重构版，增强验证/批量操作）"""
    def __init__(self,** kwargs):
        """初始化模型实例"""
        valid_fields = self._meta.fields.keys()
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_fields}
        
        # 初始化字段值
        for field_name in valid_fields:
            field = self._meta.fields[field_name]
            if field_name in filtered_kwargs:
                value = filtered_kwargs[field_name]
                # 外键字段处理
                if isinstance(field, ForeignKeyField) and isinstance(value, Model):
                    setattr(self, field_name, extract_model_pk(value))
                else:
                    setattr(self, field_name, value)
            else:
                # 设置默认值
                default_val = field.default() if callable(field.default) else field.default
                setattr(self, field_name, default_val if default_val is not None else None)
        
        # 校验无效字段
        invalid_fields = [k for k in kwargs if k not in valid_fields]
        if invalid_fields:
            raise SQLSafetyError(f"无效字段：{', '.join(invalid_fields)}")
    
    def to_dict(self, exclude=None):
        """
        模型转字典（所有模型自动可用）
        :param exclude: 要排除的字段集合，默认排除 password
        """
        if exclude is None:
            exclude = {"password"}
        
        result = {}
        for field_name in self._meta.fields:
            if field_name in exclude:
                continue
            
            value = getattr(self, field_name, None)
            
            # 时间类型自动转字符串
            if isinstance(value, datetime.datetime):
                result[field_name] = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, datetime.date):
                result[field_name] = value.strftime("%Y-%m-%d")
            elif isinstance(value, datetime.time):
                result[field_name] = value.strftime("%H:%M:%S")
            else:
                result[field_name] = value
        return result
    
    def validate(self):
        """验证所有字段"""
        for field_name, field in self._meta.fields.items():
            value = getattr(self, field_name)
            field.validate(value)
    
    # ------------------------ 数据库绑定 ------------------------
    @classmethod
    def _get_database(cls):
        """获取模型绑定的数据库"""
        db = cls._meta.database
        if db:
            return db
        # 从父类继承数据库
        for base in cls.__bases__:
            if hasattr(base, "_meta") and base._meta.database:
                return base._meta.database
        raise DatabaseNotConfiguredError(f"模型{cls.__name__}未配置数据库，请在Meta中指定")

    # ------------------------ 表操作 ------------------------
    @classmethod
    def create_table(cls, safe: bool = True):
        """创建表（包含索引）"""
        if not cls._meta.primary_key:
            raise MissingPrimaryKeyError(f"模型 {cls.__name__} 必须定义主键字段")
        
        db = cls._get_database()
        adapter = db.adapter
        
        # 构建字段定义 + 收集索引 SQL
        cols = []
        fk_constraints = []
        index_sql_list = []
        for field in cls._meta.fields.values():
            cols.append(field.get_sql_definition(adapter))
            # 收集索引 SQL
            if hasattr(field, 'index_sql') and field.index_sql:
                index_sql_list.append(field.index_sql)
            # 处理外键
            if isinstance(field, ForeignKeyField):
                target_table = field.to_model._meta.table_name
                target_pk = field.to_model._meta.primary_key.name
                fk_sql = adapter.get_foreign_key_sql(field.name, target_table, target_pk, field)
                fk_constraints.append(fk_sql.lstrip(","))
        
        all_defs = cols + fk_constraints
        safe_clause = "IF NOT EXISTS" if safe else ""
        table_name = adapter.quote_identifier(cls._meta.table_name)
        
        # 构建建表 SQL
        create_sql = f"""
            CREATE TABLE {safe_clause} {table_name} 
            ({', '.join(all_defs)});
        """
        db.execute(create_sql, close_after=False)
        
        # 创建索引
        for index_sql in index_sql_list:
            db.execute(index_sql, close_after=False)
        
        db.close()
        logger.info(f"表 {cls._meta.table_name} 创建完成（含 {len(index_sql_list)} 个索引）")

    @classmethod
    def migrate_table(cls, drop_absent: bool = False):
        """迁移表（新增/修改/删除字段）"""
        if not cls._meta.primary_key:
            raise MissingPrimaryKeyError(f"模型{cls.__name__}必须定义主键字段")
        
        db = cls._get_database()
        adapter = db.adapter
        table_name = cls._meta.table_name
        
        # 获取表元数据
        db_meta = db.get_table_metadata(table_name)
        model_fields = cls._meta.fields
        model_keys = set(model_fields.keys())
        db_keys = set(db_meta.keys())
        
        migrate_commands = []
        
        # 新增字段
        for field_name in model_keys - db_keys:
            field = model_fields[field_name]
            add_sql = f"ALTER TABLE {adapter.quote_identifier(table_name)} {adapter.get_alter_add_field_sql(field)};"
            migrate_commands.append(add_sql)
            logger.info(f"待新增字段：{field_name} | SQL：{add_sql}")
        
        # 修改字段
        for field_name in model_keys & db_keys:
            field = model_fields[field_name]
            db_field = db_meta[field_name]
            need_modify = cls._check_field_need_modify(field, db_field, adapter)
            if need_modify:
                modify_sql = f"ALTER TABLE {adapter.quote_identifier(table_name)} {adapter.get_alter_modify_field_sql(field)};"
                if modify_sql.strip():
                    migrate_commands.append(modify_sql)
                    logger.info(f"待修改字段：{field_name} | SQL：{modify_sql}")
        
        # 删除字段
        if drop_absent:
            for field_name in db_keys - model_keys:
                if field_name == cls._meta.primary_key.name:
                    continue
                drop_sql = f"ALTER TABLE {adapter.quote_identifier(table_name)} {adapter.get_alter_drop_field_sql(field_name)};"
                migrate_commands.append(drop_sql)
                logger.info(f"待删除字段：{field_name} | SQL：{drop_sql}")
        
        # 执行迁移
        if migrate_commands:
            with db.transaction():
                for idx, cmd in enumerate(migrate_commands):
                    try:
                        logger.info(f"执行迁移语句[{idx+1}/{len(migrate_commands)}]：{cmd}")
                        db.execute(cmd, close_after=True)
                    except Exception as e:
                        logger.error(f"迁移语句执行失败：{cmd} | 错误：{e}")
                        raise
            logger.info(f"模型{cls.__name__}迁移完成，成功执行{len(migrate_commands)}条语句")
        else:
            logger.info(f"模型{cls.__name__}无字段变更，无需迁移")
        
        return migrate_commands

    @classmethod
    def _check_field_need_modify(cls, field: Field, db_field: Dict, adapter: BaseDatabaseAdapter) -> bool:
        """检查字段是否需要修改（修复：跳过主键字段）"""
        if field.primary_key:
            return False

        # 字段类型对比
        model_type = adapter.get_field_type(field.__class__.__name__, field).upper()
        db_type = db_field["type"].upper()
        if not db_type.startswith(model_type.split("(")[0]):
            return True

        # 可空性对比
        if (not field.nullable) != (db_field["nullable"] is False):
            return True

        # 默认值对比
        model_default = field._format_default(field.default, adapter) if field.default is not None else None
        db_default = db_field["default"]
        
        if model_default is not None:
            if db_default is None:
                return True
            if str(model_default).upper() != str(db_default).upper():
                return True

        return False

    # ------------------------ 数据操作 ------------------------
    def save(self, close_after: bool = True) -> Any:
        """保存模型实例（新增/更新）+ 支持事务内不关闭连接 + 字段验证"""
        # 字段验证
        self.validate()
        
        if not self._meta.primary_key:
            raise MissingPrimaryKeyError(f"模型{self.__class__.__name__}必须定义主键才能保存")
        
        db = self._get_database()
        pk_name = self._meta.primary_key.name
        pk_value = getattr(self, pk_name, None)

        # 核心修复：用 type(self) 替代 self.__class__，避免指向元类
        model_cls = type(self)
        if not hasattr(model_cls, 'get_or_none'):
            raise ModelError(f"模型类{model_cls.__name__}未正确继承get_or_none方法")

        # 更新逻辑
        if pk_value and model_cls.get_or_none(**{pk_name: pk_value}):
            data = {k: getattr(self, k) for k in self._meta.fields if k != pk_name}
            update_count = model_cls.update(data, close_after=close_after,**{pk_name: pk_value})
            if update_count == 0:
                raise DataInsertError(f"更新失败：{model_cls.__name__} {pk_name}={pk_value} 无匹配记录")
            return pk_value

        # 新增逻辑
        adapter = db.adapter
        fields = []
        values = []

        for field_name, field in self._meta.fields.items():
            # 自增主键跳过
            if field.primary_key and field.auto_increment:
                continue
            
            fields.append(adapter.quote_identifier(field_name))
            val = getattr(self, field_name, field.default)
            cleaned_val = escape_value(val, field.python_type, self.__class__)
            
            # 非空校验
            if not field.nullable and cleaned_val is None:
                raise DataInsertError(f"非空约束：字段{field_name}不能为空")
            
            values.append(cleaned_val)

        # 构建插入 SQL
        table_name = adapter.quote_identifier(self._meta.table_name)
        fields_str = ", ".join(fields)
        placeholders = ", ".join([adapter.PARAM_PLACEHOLDER]*len(values))

        # 适配不同数据库的主键返回
        if db.type == "postgresql":
            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES ({placeholders}) RETURNING {pk_name};"
        elif db.type == "sqlite":
            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES ({placeholders});"
        else:
            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES ({placeholders});"

        # 执行插入（核心修复：支持事务内不关闭连接）
        try:
            return_id = db.execute(sql, tuple(values), return_id=True, close_after=close_after)
        except Exception as e:
            raise DataInsertError(f"插入失败：{e} | SQL：{sql} | 参数：{values}")
        
        # 验证主键
        if return_id is None:
            raise DataInsertError(f"插入成功但未获取到主键：{model_cls.__name__}")
        
        setattr(self, pk_name, return_id)
        
        # 二次验证：事务内不验证（避免额外查询）
        if close_after:
            check_instance = model_cls.get_or_none(**{pk_name: return_id})
            if not check_instance:
                raise DataInsertError(f"插入日志成功但数据库无记录：{model_cls.__name__} {pk_name}={return_id}")
        
        return return_id

    @classmethod
    def bulk_create(cls, instances: List["Model"], batch_size: int = 100, close_after: bool = True) -> int:
        """批量插入（增强功能）"""
        if not instances:
            return 0
        
        # 字段验证
        for inst in instances:
            inst.validate()
        
        db = cls._get_database()
        adapter = db.adapter
        
        # 提取字段（排除自增主键）
        pk_name = cls._meta.primary_key.name if cls._meta.primary_key else None
        fields = [f for f in cls._meta.fields.keys() if not (f == pk_name and cls._meta.primary_key.auto_increment)]
        
        # 构建批量插入数据
        values = []
        for inst in instances:
            row = []
            for field_name in fields:
                field = cls._meta.fields[field_name]
                val = getattr(inst, field_name, field.default)
                cleaned_val = escape_value(val, field.python_type, cls)
                row.append(cleaned_val)
            values.append(tuple(row))
        
        # 分批插入
        total = 0
        with db.transaction():
            for i in range(0, len(values), batch_size):
                batch = values[i:i+batch_size]
                fields_str = ", ".join([adapter.quote_identifier(f) for f in fields])
                placeholders = ", ".join([f"({', '.join([adapter.PARAM_PLACEHOLDER]*len(fields))})"]*len(batch))
                table_name = adapter.quote_identifier(cls._meta.table_name)
                
                sql = f"INSERT INTO {table_name} ({fields_str}) VALUES {placeholders}"
                sql = adapter.convert_placeholder(sql)
                
                # 展平参数
                flat_params = tuple(sum(batch, ()))
                count = db.execute(sql, flat_params, close_after=False)
                total += count
        
        if close_after:
            db.close()
        
        logger.info(f"批量插入 {cls.__name__} 成功，共 {total} 条记录")
        return total

    @classmethod
    def select(cls, *fields) -> Query:
        """构建查询对象"""
        query = Query(cls)
        if fields:
            validate_model_fields(cls, list(fields))
            query.fields = list(fields)
        else:
            query.fields = list(cls._meta.fields.keys())
        return query

    @classmethod
    def get_or_none(cls,** conditions):
        """查询单条记录（无则返回None）- 重构：强制走Query.where检测"""
        try:
            # 核心修复：通过Query对象构建查询，触发注入检测
            query = cls.select().where(**conditions)
            return query.first()
        except SQLSafetyError:
            # 主动抛出注入异常，让测试捕获
            raise
        except Exception:
            return None

    @classmethod
    def get(cls,** conditions):
        """查询单行（无结果抛异常）"""
        result = cls.get_or_none(**conditions)
        if not result:
            raise DoesNotExist(f"{cls.__name__} 未找到匹配记录")
        return result

    @classmethod
    def update(cls, data: Dict, close_after: bool = True,** kwargs) -> int:
        """更新数据（支持事务内不关闭连接）"""
        if not isinstance(data, dict) or len(data) == 0:
            raise ModelError("更新数据不能为空字典")
        
        db = cls._get_database()
        adapter = db.adapter

        # 处理数据和条件中的值
        processed_data = {k: escape_value(v, cls._meta.fields[k].python_type) for k, v in data.items()}
        processed_kwargs = {k: escape_value(v, cls._meta.fields[k].python_type) for k, v in kwargs.items()}

        # 校验字段
        validate_model_fields(cls, list(processed_data.keys()) + list(processed_kwargs.keys()))

        # 构建 SET 子句
        set_clause = [f"{adapter.quote_identifier(k)} = {adapter.PARAM_PLACEHOLDER}" for k in processed_data]
        set_params = list(processed_data.values())

        # 构建 WHERE 子句
        where_clause = []
        where_params = []
        for k, v in processed_kwargs.items():
            where_clause.append(f"{adapter.quote_identifier(k)} = {adapter.PARAM_PLACEHOLDER}")
            where_params.append(v)

        # 构建最终 SQL
        table_name = adapter.quote_identifier(cls._meta.table_name)
        where_str = f"WHERE {' AND '.join(where_clause)}" if where_clause else ""
        
        sql = f"""
            UPDATE {table_name} 
            SET {', '.join(set_clause)} 
            {where_str}
        """
        sql = adapter.convert_placeholder(sql)

        # 执行更新（核心修复：支持事务内不关闭连接）
        return db.execute(sql, tuple(set_params + where_params), close_after=close_after)

# ======================== 9. 工具函数 ========================
def detect_sql_injection(value: str) -> bool:
    """检测 SQL 注入（增强匹配规则）"""
    if not isinstance(value, str):
        return False
    # 增强注入特征匹配
    injection_patterns = [
        r"'.*\sOR\s.*='",  # 匹配 1' OR '1'='1
        r"1\s*=\s*1",        # 匹配 1=1、1 = 1
        r"\sor\s",           # or 关键字
        r"UNION\s+SELECT",   # UNION注入
        r"DROP\s+TABLE",     # 删除表
        r"--",               # 注释符
        r";",                # 语句分隔符
        r"\|\|",             # 拼接符
        r"EXEC\s+",          # 执行命令
        r"INSERT\s+INTO",    # 插入数据
        r"UPDATE\s+",        # 更新数据
        r"DELETE\s+FROM"     # 删除数据
    ]
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in injection_patterns)

def validate_identifier(name: str, identifier_type: str = "field") -> str:
    """校验字段/表名合法性"""
    if not isinstance(name, str) or len(name) == 0:
        raise SQLSafetyError(f"非法{identifier_type}名：空值或非字符串类型")
    if len(name) > 64:
        raise SQLSafetyError(f"非法{identifier_type}名：长度超过64字符限制")
    if not re.match(VALID_IDENTIFIER_PATTERN, name):
        raise SQLSafetyError(
            f"非法{identifier_type}名：{name}，仅允许字母/数字/下划线，且以字母/下划线开头"
        )
    upper_name = name.upper()
    if upper_name in FORBIDDEN_SQL_KEYWORDS:
        raise SQLSafetyError(f"非法{identifier_type}名：禁止使用SQL关键字 {upper_name}")
    dangerous_chars = [";", "'", "\"", "--", "#"]
    if any(char in name for char in dangerous_chars):
        raise SQLSafetyError(f"非法{identifier_type}名：{name} 包含危险符号")
    return name

def validate_model_fields(model_cls, field_names: List[str]) -> List[str]:
    """校验模型字段是否存在"""
    valid_fields = list(model_cls._meta.fields.keys())
    invalid_fields = [f for f in field_names if f not in valid_fields]
    if invalid_fields:
        raise SQLSafetyError(f"模型{model_cls.__name__}不存在字段：{', '.join(invalid_fields)}")
    return field_names

def escape_value(value: Any, field_type: str, model_cls = None) -> Any:
    """转义字段值，防止注入"""
    if value is None or isinstance(value, Field):
        return None
    if isinstance(value, Model):
        if not value._meta.primary_key:
            raise InvalidForeignKeyError(f"关联模型{value.__class__.__name__}缺少主键定义")
        pk_name = value._meta.primary_key.name
        value = getattr(value, pk_name)
    type_converters = {
        "int": int,
        "str": lambda v: re.sub(r"['\";\\`]", "", str(v)).strip(),
        "bool": bool,
        "datetime": lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else str(v),
        "date": lambda v: v.strftime("%Y-%m-%d") if isinstance(v, datetime.date) else str(v),
        "time": lambda v: v.strftime("%H:%M:%S") if isinstance(v, datetime.time) else str(v),
        "float": float,
        "decimal": decimal.Decimal,
        "bytes": lambda v: v if isinstance(v, bytes) else str(v).encode("utf-8")
    }
    try:
        return type_converters.get(field_type, lambda v: v)(value)
    except (ValueError, TypeError):
        raise SQLSafetyError(f"值类型转换失败：{value} -> {field_type}")

def extract_model_pk(model_instance: Model) -> Any:
    """提取模型主键值"""
    if not isinstance(model_instance, Model):
        raise InvalidForeignKeyError("外键值必须是Model实例或主键值")
    if not model_instance._meta.primary_key:
        raise MissingPrimaryKeyError(f"模型{model_instance.__class__.__name__}未定义主键")
    pk_name = model_instance._meta.primary_key.name
    pk_value = getattr(model_instance, pk_name, None)
    if pk_value is None:
        raise InvalidForeignKeyError(f"模型{model_instance.__class__.__name__}主键值为空")
    return pk_value

# ======================== 10. 事务上下文 ========================
class TransactionContext:
    """事务上下文管理器"""
    def __init__(self, db):
        self.db = db
        self.has_active_conn = False

    def __enter__(self):
        try:
            self.db.begin_transaction()
            self.has_active_conn = True
        except Exception as e:
            raise TransactionError(f"开启事务失败：{e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.has_active_conn:
            try:
                if exc_type:
                    self.db.rollback_transaction()
                    logger.warning(f"事务回滚：{exc_val}")
                else:
                    self.db.commit_transaction()
                    logger.info("事务提交成功")
            except Exception as e:
                raise TransactionError(f"事务提交/回滚失败：{e}")
        return False

# ======================== 11. 数据库核心类 ========================
class Database:
    """数据库核心类（修复 SQLite autocommit 错误）"""
    def __init__(self, db_type: str, pool_enable: bool = False,** kwargs):
        self.type = db_type.lower()
        self.adapter = get_database_adapter(self.type)
        self.pool = ConnectionPool(self.type, kwargs, pool_enable)
        self.conn = None
        self.cursor = None

    # ------------------------ 连接管理 ------------------------
    def connect(self) -> bool:
        """建立连接"""
        try:
            if not self.conn or (hasattr(self.conn, 'closed') and self.conn.closed):
                self.conn = self.pool.get_connection()
            if not self.cursor or (hasattr(self.cursor, 'closed') and self.cursor.closed):
                self.cursor = self.conn.cursor()
            return True
        except Exception as e:
            logger.error(f"连接失败：创建数据库连接失败：{e}")
            self.close()
            return False

    def close(self):
        """关闭连接"""
        if self.cursor:
            try:
                self.cursor.close()
            except Exception as e:
                logger.warning(f"关闭游标失败：{e}")
            self.cursor = None
        if self.conn:
            try:
                self.pool.release_connection(self.conn)
            except Exception as e:
                logger.warning(f"释放连接失败：{e}")
            self.conn = None

    # ------------------------ 事务管理（修复 SQLite autocommit 判断） ------------------------
    def begin_transaction(self):
        """开启事务"""
        if not self.connect():
            raise TransactionError("无法创建连接，事务开启失败")
        try:
            # 修复：适配不同数据库的事务开启方式
            if self.type == "sqlite":
                # SQLite 开启事务需要执行 BEGIN
                self.cursor.execute("BEGIN;")
                # SQLite 通过设置 isolation_level 关闭自动提交
                self.conn.isolation_level = ""
            else:
                self.cursor.execute("BEGIN;")
                self.conn.autocommit = False
        except Exception as e:
            self.close()
            raise TransactionError(f"开启事务失败：{e}")

    def commit_transaction(self):
        """提交事务"""
        try:
            self.conn.commit()
        except Exception as e:
            raise TransactionError(f"提交事务失败：{e}")
        finally:
            self.close()

    def rollback_transaction(self):
        """回滚事务"""
        try:
            self.conn.rollback()
        except Exception as e:
            raise TransactionError(f"回滚事务失败：{e}")
        finally:
            self.close()

    def transaction(self):
        """返回事务上下文"""
        return TransactionContext(self)

    # ------------------------ 执行与查询 ------------------------
    def execute(self, sql: str, params: tuple = (), return_id: bool = False, close_after: bool = True):
        """执行 SQL"""
        if not self.connect():
            raise DatabaseError("数据库未连接")
        try:
            sql = self.adapter.convert_placeholder(sql.strip())
            self.cursor.execute(sql, params)
            if return_id:
                if self.type == "postgresql":
                    return self.cursor.fetchone()[0]
                elif self.type == "sqlite":
                    return self.cursor.lastrowid
                else:
                    return self.cursor.lastrowid
            return self.cursor.rowcount
        except Exception as e:
            raise DatabaseError(f"执行失败：{e}\nSQL：{sql}\n参数：{params}")
        finally:
            if close_after:
                self.close()

    def fetch_all(self, sql: str, params: tuple = (), close_after: bool = True):
        """查询所有结果"""
        if not self.connect():
            raise DatabaseError("数据库未连接")
        try:
            sql = self.adapter.convert_placeholder(sql.strip())
            self.cursor.execute(sql, params)
            return self.cursor.fetchall()
        except Exception as e:
            raise DatabaseError(f"查询失败：{e}\nSQL：{sql}\n参数：{params}")
        finally:
            if close_after:
                self.close()

    def fetch_one(self, sql: str, params: tuple = (), close_after: bool = True):
        """查询单条结果"""
        if not self.connect():
            raise DatabaseError("数据库未连接")
        try:
            sql = self.adapter.convert_placeholder(sql.strip())
            self.cursor.execute(sql, params)
            return self.cursor.fetchone()
        except Exception as e:
            raise DatabaseError(f"查询失败：{e}\nSQL：{sql}\n参数：{params}")
        finally:
            if close_after:
                self.close()

    def get_table_metadata(self, table_name: str):
        """获取表结构元信息"""
        sql = self.adapter.get_table_metadata_sql(table_name)
        rows = self.fetch_all(sql, (table_name,), close_after=True)
        meta = {}
        if self.type == "mysql":
            for row in rows:
                name = row["name"]
                meta[name] = {
                    "type": row["type"],
                    "nullable": row["nullable"] == "YES",
                    "default": row["default"]
                }
        elif self.type == "postgresql":
            for row in rows:
                name = row["name"]
                meta[name] = {
                    "type": row["type"],
                    "nullable": row["nullable"],
                    "default": row["default"]
                }
        elif self.type == "sqlite":
            for row in rows:
                name = row[1]
                meta[name] = {
                    "type": row[2],
                    "nullable": not row[3],
                    "default": row[4]
                }
        return meta

# ======================== 12. 快速使用示例（可直接运行） ========================
if __name__ == "__main__":
    # 1. 创建数据库实例（SQLite 示例）
    db = Database("sqlite", database="demo.db")

    # 2. 定义模型
    class User(Model):
        id = IntegerField(primary_key=True, auto_increment=True, comment="用户ID")
        username = StringField(max_length=50, unique=True, comment="用户名")
        age = IntegerField(nullable=True, comment="年龄")
        create_time = DateTimeField(auto_now_add=True, comment="创建时间")

        class Meta:
            table_name = "user"
            database = db

    class Post(Model):
        id = IntegerField(primary_key=True, auto_increment=True)
        title = StringField(max_length=200)
        user_id = ForeignKeyField(to=User, backref="posts", on_delete="CASCADE")

        class Meta:
            table_name = "post"
            database = db

    # 3. 创建表
    User.create_table()
    Post.create_table()

    # 4. 新增
    user = User(username="test_user", age=25)
    user.save()

    post = Post(title="Hello ORM", user_id=user.id)
    post.save()

    # 5. 查询
    u = User.get(username="test_user")
    print("查询到用户：", u.to_dict())

    # 6. 关联查询
    posts = u.posts()
    print("该用户的文章：", [p.to_dict() for p in posts])

    # 7. 更新
    User.update({"age": 26}, id=user.id)

    # 8. 事务示例
    with db.transaction():
        u1 = User(username="tx_user1", age=20)
        u1.save()
        u2 = User(username="tx_user2", age=21)
        u2.save()

    print("ORM 框架运行成功！")