#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终版 Peewee 风格 ORM 框架（修复所有已知错误）
核心特性：
1. 修复 isinstance 参数错误、代码顺序错误
2. 支持 PostgreSQL/MySQL/SQLite 多数据库适配
3. 修复 PostgreSQL 自增主键、外键约束、事务连接问题
4. 模块化设计，执行顺序合理，无依赖错误
"""

import re
import time
import queue
import threading
import logging
import datetime
import sqlite3
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple, Any, Callable, Iterable,Type

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
        """创建新连接"""
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
                conn = sqlite3.connect(**self.conn_kwargs)
                conn.row_factory = sqlite3.Row
                conn.autocommit = True
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
    """MySQL 适配器"""
    FIELD_TYPE_MAP = {
        "IntField": "INT", "CharField": "VARCHAR", "TextField": "TEXT",
        "DateTimeField": "DATETIME", "BooleanField": "TINYINT",
        "UUIDField": "CHAR", "ForeignKeyField": "INT"
    }
    AUTO_INCREMENT_SUFFIX = "AUTO_INCREMENT"
    IDENTIFIER_QUOTE = "`"
    PARAM_PLACEHOLDER = "%s"

    def get_field_type(self, cls_name: str, inst):
        base_type = self.FIELD_TYPE_MAP[cls_name]
        if cls_name == "CharField":
            return f"{base_type}({inst.max_length})"
        elif cls_name == "UUIDField":
            return f"{base_type}(36)"
        return base_type

    def get_auto_increment_sql(self, inst):
        return self.AUTO_INCREMENT_SUFFIX if inst.primary_key and isinstance(inst, IntField) else ""

    def get_foreign_key_sql(self, name, target_table, target_pk, inst):
        t_tbl = self.quote_identifier(target_table)
        t_pk = self.quote_identifier(target_pk)
        fk = self.quote_identifier(name)
        return f", FOREIGN KEY ({fk}) REFERENCES {t_tbl}({t_pk}) ON DELETE {inst.on_delete}"

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
    """PostgreSQL 适配器（修复 SERIAL 问题）"""
    FIELD_TYPE_MAP = {
        "IntField": "INTEGER", "CharField": "VARCHAR", "TextField": "TEXT",
        "DateTimeField": "TIMESTAMP", "BooleanField": "BOOLEAN",
        "UUIDField": "UUID", "ForeignKeyField": "INTEGER"
    }
    AUTO_INCREMENT_SUFFIX = ""
    IDENTIFIER_QUOTE = "\""
    PARAM_PLACEHOLDER = "%s"

    def get_field_type(self, cls_name: str, inst):
        base_type = self.FIELD_TYPE_MAP[cls_name]
        if cls_name == "CharField":
            return f"{base_type}({inst.max_length})"
        # 修复：自增主键返回 INTEGER（SERIAL 是伪类型）
        elif cls_name == "IntField" and inst.primary_key and getattr(inst, 'auto_increment', False):
            return "INTEGER"
        return base_type

    def get_auto_increment_sql(self, inst):
        # 修复：使用 PostgreSQL 标准自增语法
        if inst.primary_key and isinstance(inst, IntField) and getattr(inst, 'auto_increment', False):
            return "PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY"
        return ""

    def get_foreign_key_sql(self, name, target_table, target_pk, inst):
        t_tbl = self.quote_identifier(target_table)
        t_pk = self.quote_identifier(target_pk)
        fk = self.quote_identifier(name)
        return f", FOREIGN KEY ({fk}) REFERENCES {t_tbl}({t_pk}) ON DELETE {inst.on_delete}"

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
    """SQLite 适配器"""
    FIELD_TYPE_MAP = {
        "IntField": "INTEGER", "CharField": "TEXT", "TextField": "TEXT",
        "DateTimeField": "DATETIME", "BooleanField": "INTEGER",
        "UUIDField": "TEXT", "ForeignKeyField": "INTEGER"
    }
    AUTO_INCREMENT_SUFFIX = "AUTOINCREMENT"
    IDENTIFIER_QUOTE = "\""
    PARAM_PLACEHOLDER = "?"

    def get_field_type(self, cls_name: str, inst):
        return self.FIELD_TYPE_MAP[cls_name]

    def get_auto_increment_sql(self, inst):
        return self.AUTO_INCREMENT_SUFFIX if inst.primary_key and isinstance(inst, IntField) else ""

    def get_foreign_key_sql(self, name, target_table, target_pk, inst):
        t_tbl = self.quote_identifier(target_table)
        t_pk = self.quote_identifier(target_pk)
        fk = self.quote_identifier(name)
        return f", FOREIGN KEY ({fk}) REFERENCES {t_tbl}({t_pk}) ON DELETE {inst.on_delete}"

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

# ======================== 5. 查询对象 ========================
class Query:
    """查询对象"""
    def __init__(self, model_cls):
        self.model_cls = model_cls
        self.db = model_cls._get_database()
        self.adapter = self.db.adapter
        self.fields = list(model_cls._meta.fields.keys())
        self.where_conditions = []
        self.where_params = []
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

    def _build_sql(self) -> str:
        """构建查询 SQL"""
        fields_str = ", ".join([self.adapter.quote_identifier(f) for f in self.fields])
        table_name = self.adapter.quote_identifier(self.model_cls._meta.table_name)
        where_clause = ""
        if self.where_conditions:
            where_clause = f"WHERE {' AND '.join(self.where_conditions)}"
        sql = f"SELECT {fields_str} FROM {table_name} {where_clause}"
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

    def first(self) -> Optional [Any] :
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

# ======================== 6. 字段定义 ========================
class Field:
    """字段基类"""
    python_type = "str"
    
    def __init__(self, primary_key: bool = False, nullable: bool = False, 
                 default: Any = None, unique: bool = False):
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.unique = unique
        self.name = None  # 字段名（由元类自动赋值）
        self.model = None  # 所属模型（由元类自动赋值）

    def _format_default(self, value, adapter: BaseDatabaseAdapter = None) -> Any:
        """格式化默认值"""
        if callable(value):
            value = value()
        if isinstance(value, str):
            return f"'{value}'"
        elif isinstance(value, datetime.datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        elif isinstance(value, bool):
            return adapter.format_boolean_default(value) if adapter else ("TRUE" if value else "FALSE")
        return value

    def get_sql_definition(self, adapter: BaseDatabaseAdapter) -> str:
        """获取字段 SQL 定义"""
        name = adapter.quote_identifier(self.name)
        field_type = adapter.get_field_type(self.__class__.__name__, self)
        auto_inc = adapter.get_auto_increment_sql(self)
        parts = [name, field_type]
        
        if auto_inc:
            parts.append(auto_inc)
        if not self.nullable:
            parts.append("NOT NULL")
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        if self.primary_key and not auto_inc:
            parts.append("PRIMARY KEY")
        if self.default is not None:
            parts.append(f"DEFAULT {self._format_default(self.default, adapter)}")
        
        return " ".join(parts)

class IntField(Field):
    """整数字段"""
    python_type = "int"
    
    def __init__(self, primary_key: bool = False, auto_increment: bool = False, 
                 nullable: bool = False, default: Any = None, unique: bool = False):
        super().__init__(primary_key, nullable, default, unique)
        self.auto_increment = auto_increment or primary_key

class CharField(Field):
    """字符字段"""
    python_type = "str"
    
    def __init__(self, max_length: int = 255, primary_key: bool = False, 
                 nullable: bool = False, default: Any = None, unique: bool = False):
        super().__init__(primary_key, nullable, default, unique)
        self.max_length = max_length

class TextField(Field):
    """文本字段"""
    python_type = "str"

class DateTimeField(Field):
    """日期时间字段"""
    python_type = "datetime"

class BooleanField(Field):
    """布尔字段"""
    python_type = "bool"

class ForeignKeyField(Field):
    """外键字段"""
    python_type = "int"
    
    def __init__(self, to, backref: str = None, on_delete: str = "CASCADE", 
                 nullable: bool = True, unique: bool = False):
        super().__init__(nullable=nullable, unique=unique)
        self.to_model = to
        self.backref = backref
        self.on_delete = on_delete.upper()
    # 【补充1：验证级联删除策略合法性】
        valid_on_delete = ["CASCADE", "SET NULL", "RESTRICT", "NO ACTION", "SET DEFAULT"]
        if self.on_delete not in valid_on_delete:
            raise ValueError(
                f"非法的on_delete策略：{on_delete}，仅支持：{valid_on_delete}"
            )
        
        # 【补充2：验证关联模型合法性】
        if not issubclass(self.to_model, Model):
            raise TypeError(f"关联目标必须是Model子类，当前：{type(self.to_model)}")
        if not hasattr(self.to_model._meta, "primary_key"):
            raise ValueError(f"关联模型{self.to_model.__name__}未定义主键，无法创建外键")
        
        # 【补充3：自动注册反向引用】（如果指定backref）
        if self.backref:
            self._register_backref()

    def _register_backref(self):
        """注册反向引用（给关联模型添加查询当前模型的属性）"""
        # 定义反向关联的简易实现（可根据实际需求扩展）
        def reverse_query(instance):
            """反向查询函数：通过关联模型实例查询当前模型数据"""
            from_model = self.model  # 当前外键所属的模型（如EmployeeModel）
            filter_kwargs = {self.name: getattr(instance, instance._meta.primary_key.name)}
            return [obj for obj in from_model._all_data if all(
                getattr(obj, k) == v for k, v in filter_kwargs.items()
            )]
        
        # 给关联模型（如DepartmentModel）添加反向引用属性
        if not hasattr(self.to_model, self.backref):
            setattr(self.to_model, self.backref, reverse_query)

    def get_sql_definition(self, adapter: BaseDatabaseAdapter) -> str:
        """【补充4：重写SQL生成逻辑】生成包含外键约束的SQL"""
        # 1. 生成基础整型字段定义（外键本质是整型）
        base_sql = super().get_sql_definition(adapter)
        
        # 2. 拼接外键约束（REFERENCES + ON DELETE）
        target_table = adapter.quote_identifier(self.to_model._meta.table_name)
        target_pk = adapter.quote_identifier(self.to_model._meta.primary_key.name)
        foreign_key_constraint = (
            f"REFERENCES {target_table}({target_pk}) ON DELETE {self.on_delete}"
        )
        
        # 3. 组合最终SQL（基础字段 + 外键约束）
        final_sql = f"{base_sql} {foreign_key_constraint}"
        
        return final_sql




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

# ======================== 8. 模型基类 ========================
class Model(metaclass=ModelMeta):
    """模型基类（重构版）"""
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
        """创建表"""
        if not cls._meta.primary_key:
            raise MissingPrimaryKeyError(f"模型{cls.__name__}必须定义主键字段")
        
        db = cls._get_database()
        adapter = db.adapter
        
        # 构建字段定义
        cols = []
        fk_constraints = []
        for field in cls._meta.fields.values():
            cols.append(field.get_sql_definition(adapter))
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
        sql = f"""
            CREATE TABLE {safe_clause} {table_name} 
            ({', '.join(all_defs)});
        """
        db.execute(sql, close_after=True)
        logger.info(f"表 {cls._meta.table_name} 创建完成")

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
        """保存模型实例（新增/更新）+ 支持事务内不关闭连接"""
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

# ======================== 9. 工具函数（关键：移到 Model/Field 之后） ========================
def detect_sql_injection(value: str) -> bool:
    """检测 SQL 注入（增强匹配规则，覆盖1' OR '1'='1这类特征）"""
    if not isinstance(value, str):
        return False
    # 增强注入特征匹配：覆盖单引号+OR、1=1、注释等
    injection_patterns = [
        r"'.*\sOR\s.*='",  # 匹配 1' OR '1'='1
        r"1\s*=\s*1",        # 匹配 1=1、1 = 1
        r"\sor\s",           # or 关键字（转义后）
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
    # 忽略大小写匹配
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
    """转义字段值，防止注入（修复 isinstance 参数错误）"""
    # 修复1：第二个参数改为 Field 类（而非字符串）
    if value is None or isinstance(value, Field):
        return None
    # 修复2：第二个参数改为 Model 类（而非字符串）
    if isinstance(value, Model):
        if not value._meta.primary_key:
            raise InvalidForeignKeyError(f"关联模型{value.__class__.__name__}缺少主键定义")
        pk_name = value._meta.primary_key.name
        value = getattr(value, pk_name)
    type_converters = {
        "int": int,
        "str": lambda v: re.sub(r"['\";\\`]", "", str(v)).strip(),
        "bool": bool,
        "datetime": lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else str(v)
    }
    try:
        return type_converters.get(field_type, lambda v: v)(value)
    except (ValueError, TypeError):
        raise SQLSafetyError(f"值类型转换失败：{value} -> {field_type}")

def extract_model_pk(model_instance: Model) -> Any:
    """提取模型主键值（修复 isinstance 参数）"""
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
    """数据库核心类（重构版）"""
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
            logger.error(f"连接失败：{e}")
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

    # ------------------------ 事务管理 ------------------------
    def begin_transaction(self):
        """开启事务"""
        if not self.connect():
            raise TransactionError("无法创建连接，事务开启失败")
        try:
            self.cursor.execute("BEGIN;")
            self.conn.autocommit = False
        except Exception as e:
            self.close()
            raise TransactionError(f"开启事务失败：{e}")

    def commit_transaction(self):
        """提交事务"""
        if not self.conn:
            logger.warning("无活跃连接，跳过事务提交")
            return
        try:
            self.conn.commit()
            self.conn.autocommit = True
        except Exception as e:
            raise TransactionError(f"提交事务失败：{e}")
        finally:
            self.close()

    def rollback_transaction(self):
        """回滚事务"""
        if not self.conn:
            logger.warning("无活跃连接，跳过事务回滚")
            return
        try:
            self.conn.rollback()
            self.conn.autocommit = True
        except Exception as e:
            raise TransactionError(f"回滚事务失败：{e}")
        finally:
            self.close()

    def transaction(self) -> TransactionContext:
        """获取事务上下文"""
        return TransactionContext(self)

    # ------------------------ SQL 执行 ------------------------
    def execute(self, sql: str, params: Tuple = (), return_id: bool = False, close_after: bool = True) -> Any:
        """执行 SQL（修复：事务内不提交、不关闭连接）"""
        result = None
        try:
            if not self.connect():
                raise DatabaseError("无法创建连接，SQL执行失败")
            
            self.cursor.execute(sql, params)
            
            # 核心修复：事务内（autocommit=False）不自动提交
            if self.conn.autocommit:
                self.conn.commit()
            
            # 返回主键 ID
            if return_id:
                if self.type == "mysql":
                    result = self.cursor.lastrowid
                elif self.type == "postgresql":
                    fetch_result = self.cursor.fetchone()
                    result = fetch_result[0] if fetch_result else None
                elif self.type == "sqlite":
                    result = self.conn.lastrowid
            else:
                # 返回受影响行数
                result = self.cursor.rowcount
            
            return result
        except Exception as e:
            # 核心修复：事务内不回滚（交给事务上下文处理）
            if self.conn.autocommit:
                self.rollback_transaction()
            raise DatabaseError(f"SQL执行失败：{e} | SQL：{sql} | 参数：{params}")
        finally:
            # 核心修复：事务内（autocommit=False）不关闭连接
            if close_after and self.conn and self.conn.autocommit:
                self.close()

    def fetch_one(self, sql: str, params: Tuple = ()) -> Optional[Dict]:
        """查询单行"""
        try:
            self.execute(sql, params, close_after=False)
            row = self.cursor.fetchone()
            return dict(row) if row else None
        finally:
            self.close()

    def fetch_all(self, sql: str, params: Tuple = ()) -> List[Dict]:
        """查询多行"""
        try:
            self.execute(sql, params, close_after=False)
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows] if rows else []
        finally:
            self.close()

    # ------------------------ 元数据查询 ------------------------
    def get_table_metadata(self, table_name: str) -> Dict[str, Dict]:
        """获取表元数据"""
        sql = self.adapter.get_table_metadata_sql(table_name)
        sql = self.adapter.convert_placeholder(sql)
        results = self.fetch_all(sql, (table_name,))
        
        meta = {}
        for row in results:
            if self.type == "sqlite":
                meta[row["name"]] = {
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": bool(row["notnull"] == 0),
                    "default": row["dflt_value"]
                }
            else:
                meta[row["name"]] = row
        
        return meta

# ======================== 12. 快捷函数 ========================
def SqliteDatabase(database: str, pool_enable: bool = False) -> Database:
    """快捷创建 SQLite 数据库"""
    return Database("sqlite", pool_enable, database=database)

def MySQLDatabase(database: str, user: str, password: str, host: str = "127.0.0.1", 
                  port: int = 3306, pool_enable: bool = True) -> Database:
    """快捷创建 MySQL 数据库"""
    return Database(
        "mysql", pool_enable,
        host=host, port=port, user=user, password=password,
        database=database, charset="utf8mb4"
    )

def PostgresqlDatabase(database: str, user: str, password: str, host: str = "127.0.0.1", 
                       port: int = 5432, pool_enable: bool = True) -> Database:
    """快捷创建 PostgreSQL 数据库"""
    return Database(
        "postgresql", pool_enable,
        host=host, port=port, user=user, password=password,
        database=database
    )

# ======================== 13. 测试用例 ========================
if __name__ == "__main__":
    # ========== 数据库配置（请修改为你的实际 PostgreSQL 配置） ==========
    DB = PostgresqlDatabase(
        database="admin_system",  # 你的数据库名
        host="127.0.0.1",         # 数据库地址
        port=5432,                # 端口
        user="postgres",          # 用户名
        password="postgres",      # 密码
        pool_enable=True         # 调试阶段关闭连接池
    )

    # 基础模型（所有模型继承此类）
    class BaseModel(Model):
        class Meta:
            database = DB

    try:
        # ========== 定义业务模型 ==========
        class UserModel(BaseModel):
            """用户模型"""
            id = IntField(primary_key=True, auto_increment=True)
            username = CharField(nullable=False, max_length=32)
            email = CharField(nullable=True, default="")
            phone = CharField(nullable=True, max_length=11)
            # address = CharField(nullable=True, default="")

            class Meta:
                table_name = "sys_user"

        class OrderModel(BaseModel):
            """订单模型"""
            id = IntField(primary_key=True, auto_increment=True)
            order_no = CharField(nullable=False, max_length=32)
            amount = IntField(nullable=False, default=0)
            user_id = ForeignKeyField(to=UserModel, on_delete="CASCADE")

            class Meta:
                table_name = "sys_order"

        class Tweet(BaseModel):
            """推文模型"""
            id = IntField(primary_key=True, auto_increment=True)
            author_id = ForeignKeyField(to=UserModel, backref='tweets', nullable=False)
            message = TextField()
            created_date = DateTimeField(default=datetime.datetime.now)
            is_published = BooleanField(default=True)

            class Meta:
                table_name = "sys_tweet"

        # ========== 删除旧表（带 CASCADE 处理外键依赖） ==========
        # try:
        #     DB.execute("DROP TABLE IF EXISTS sys_tweet CASCADE;")
        #     DB.execute("DROP TABLE IF EXISTS sys_order CASCADE;")
        #     DB.execute("DROP TABLE IF EXISTS sys_user CASCADE;")
        #     logger.info("旧表删除完成")
        # except Exception as e:
        #     logger.warning(f"删除旧表失败（首次运行可忽略）：{e}")

        # ========== 创建新表 ==========
        UserModel.create_table()
        OrderModel.create_table()
        Tweet.create_table()

        time.sleep(0.5)  # 确保表创建完成
        UserModel.migrate_table(drop_absent=True) 
        # ========== 数据操作测试 ==========
        # 1. 创建用户
        user = UserModel(username="test_user", email="test@example.com")
        user.save()
        logger.info(f"用户创建成功，ID：{user.id} | 类型：{type(user.id)}")
        
        # 验证用户
        user_check = UserModel.get_or_none(id=user.id)
        if not user_check:
            raise DataInsertError(f"用户插入失败！ID={user.id}")
        logger.info(f"用户验证成功：{user_check.username}")

        # 2. 创建推文
        tweet = Tweet(
            author_id=user.id,
            message="Hello 最终版 Peewee-style ORM!",
            created_date=datetime.datetime.now(),
            is_published=True
        )
        tweet.save()
        logger.info(f"推文创建成功，ID：{tweet.id} | author_id：{tweet.author_id}")
        
        # 验证推文
        tweet_check = Tweet.get_or_none(id=tweet.id)
        if not tweet_check:
            raise DataInsertError(f"推文插入失败！ID={tweet.id}")
        logger.info(f"推文验证成功：{tweet_check.message}")

        # 3. 查询测试
        user = UserModel.get(username="test_user")
        print(f"\n✅ 查询到用户：{user.username} | ID：{user.id}")

        # 4. 反向引用查询
        tweets = user.tweets()
        print(f"✅ 用户的推文数量：{len(tweets)}")
        for t in tweets:
            print(f"✅ 推文内容：{t.message} | 发布状态：{t.is_published} | ID：{t.id}")

        # 5. 更新测试
        update_count = Tweet.update({"is_published": False}, author_id=user.id)
        logger.info(f"✅ 更新了 {update_count} 条推文")

        # 查询更新后的推文
        updated_tweet = Tweet.get(author_id=user.id)
        print(f"\n✅ 更新后发布状态：{updated_tweet.is_published}")

        # 6. 事务批量插入（修复后）
        with DB.transaction():
            user1 = UserModel(username="admin", email="admin@test.com", phone="13800138000")
            user1.save(close_after=False)
            logger.info(f"✅ 批量插入用户1成功，ID：{user1.id}")

            user2 = UserModel(username="test2", email="test2@test.com", phone="13900139000")
            user2.save(close_after=False)
            logger.info(f"✅ 批量插入用户2成功，ID：{user2.id}")

            # 事务内插入订单（不关闭连接）
            OrderModel(order_no="ORD20260001", amount=99, user_id=user1.id).save(close_after=False)
            OrderModel(order_no="ORD20260002", amount=199, user_id=user2.id).save(close_after=False)

        logger.info("✅ 事务插入数据完成")

        # 验证订单数据
        order1 = OrderModel.get_or_none(user_id=user1.id)
        order2 = OrderModel.get_or_none(user_id=user2.id)
        print(f"\n✅ 验证订单1：{order1.order_no} | 金额：{order1.amount}")
        print(f"✅ 验证订单2：{order2.order_no} | 金额：{order2.amount}")

    except Exception as e:
        logger.error(f"❌ 执行异常：{e}", exc_info=True)
    finally:
        # 关闭数据库连接
        DB.close()
        if hasattr(DB, 'pool'):
            DB.pool.close_pool()
        logger.info("✅ 数据库连接已安全关闭")