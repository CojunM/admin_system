#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单文件版 Peewee 风格 ORM 框架
核心特性：自研连接池 | 防SQL注入 | MySQL/PG无缝切换 | 模型自动迁移 | 事务/关联/复杂查询
无第三方依赖（仅需数据库官方驱动） | 无DBUtils | 对齐Peewee API
"""
# ------------------------------ 导入依赖（标准库 + 数据库驱动）------------------------------
import re
import time
import queue
import threading
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple, Any

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ------------------------------ 1. 全局配置常量 ------------------------------
# 修复：仅拦截整词匹配的SQL关键字（避免子串误判），移除OR/AND等运算符（改为在条件拼接时校验）
FORBIDDEN_KEYWORDS = [
    "UNION", "SELECT", "INSERT", "DELETE", "UPDATE", "DROP", "ALTER",
    "TRUNCATE", "EXEC", "1=1", "--", "#", ";", "'", "\""
]
VALID_NAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"

# 连接池默认配置
POOL_CONFIG = {
    "mincached": 1,
    "maxcached": 10,
    "maxconnections": 20,
    "blocking": True,
    "idle_timeout": 300
}

# 查询操作符映射
OPERATOR_MAP = {
    "eq": "=", "ne": "!=", "gt": ">", "lt": "<",
    "gte": ">=", "lte": "<=", "like": "LIKE",
    "in": "IN", "not_in": "NOT IN"
}

# ------------------------------ 2. 安全校验与基础数据结构 ------------------------------
class SQLSafetyError(Exception):
    """SQL安全校验异常"""
    pass

class ConnectionItem:
    """连接池存储单元，记录连接生命周期"""
    def __init__(self, conn):
        self.conn = conn
        self.create_time = time.time()
        self.last_used = time.time()

    def is_expired(self, timeout: int) -> bool:
        return (time.time() - self.last_used) > timeout

    def update_used_time(self):
        self.last_used = time.time()
# ====================== SQL注入检测工具函数 ======================
def detect_sql_injection(value: str) -> bool:
    """检测参数值是否包含SQL注入特征"""
    if not isinstance(value, str):
        return False
    # 定义注入特征关键词（覆盖常见注入语句）
    injection_patterns = [
        r"'.*OR.*='",  # 匹配 ' OR '1'='1 这类
        r"1=1",        # 恒真条件
        r"UNION",      # 联合查询
        r"DROP",       # 删除表
        r"DELETE",     # 删除数据
        r"INSERT",     # 插入数据
        r"UPDATE",     # 更新数据
        r"EXEC",       # 执行命令
        r"--",         # 注释符
        r";",          # 多语句分隔符
        r"\|\|",       # 拼接符
    ]
    import re
    for pattern in injection_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            return True
    return False

def validate_identifier(name: str, identifier_type: str = "field") -> str:
    """
    校验表名/字段名，杜绝注入
    修复：1. 整词匹配禁用关键字 2. 排除子串误判 3. 仅拦截危险关键字，而非运算符
    """
    if not isinstance(name, str) or len(name) == 0:
        raise SQLSafetyError(f"非法{identifier_type}名：空值或非字符串")
    if len(name) > 64:
        raise SQLSafetyError(f"非法{identifier_type}名：长度超过64字符")
    if not re.match(VALID_NAME_PATTERN, name):
        raise SQLSafetyError(f"非法{identifier_type}名：格式不合法（仅允许字母/数字/下划线，且以字母/下划线开头）")
    
    # 修复核心：整词匹配禁用关键字（而非子串包含）
    upper_name = name.upper()
    if upper_name in FORBIDDEN_KEYWORDS:
        raise SQLSafetyError(f"非法{identifier_type}名：禁止使用SQL关键字 {upper_name}")
    
    # 额外防护：检查是否包含危险符号（避免注入）
    dangerous_chars = [";", "'", "\"", "--", "#"]
    for char in dangerous_chars:
        if char in name:
            raise SQLSafetyError(f"非法{identifier_type}名：包含危险符号 {char}")
    
    return name

def validate_model_fields(model_cls: Any, field_names: List[str]) -> List[str]:
    """校验字段是否属于模型，防止非法字段注入"""
    valid_fields = list(model_cls._meta.fields.keys())
    invalid = [f for f in field_names if f not in valid_fields]
    if invalid:
        raise SQLSafetyError(f"模型{model_cls.__name__}不存在字段：{invalid}")
    return field_names

def escape_value(value: Any, field_type: str) -> Any:
    """值类型强制转换+清洗，防注入"""
    # 修复核心：如果值是字段实例，直接返回None
    if isinstance(value, Field):
        return None
    if value is None:
        return None
    try:
        if field_type == "int":
            return int(value)
        elif field_type == "str":
            return re.sub(r"['\";\\`]", "", str(value)).strip()
        elif field_type == "bool":
            return bool(value)
        return value
    except (ValueError, TypeError):
        raise SQLSafetyError(f"值类型转换失败：{value} -> {field_type}")

# ------------------------------ 3. 数据库适配器（跨库兼容）------------------------------
class BaseDatabaseAdapter(ABC):
    FIELD_TYPE_MAP = {}
    AUTO_INCREMENT_SUFFIX = ""
    IDENTIFIER_QUOTE = ""
    PARAM_PLACEHOLDER = "%s"
    AGGREGATE_FUNC_MAP = {"count": "COUNT", "sum": "SUM", "avg": "AVG", "max": "MAX", "min": "MIN"}

    @abstractmethod
    def get_field_type(self, field_cls_name: str, field_instance) -> str:
        pass

    @abstractmethod
    def get_auto_increment_sql(self, field_instance) -> str:
        pass

    @abstractmethod
    def get_foreign_key_sql(self, *args, **kwargs) -> str:
        pass

    @abstractmethod
    def get_alter_add_field_sql(self, field_instance) -> str:
        pass

    @abstractmethod
    def get_alter_modify_field_sql(self, field_instance) -> str:
        pass

    @abstractmethod
    def get_alter_drop_field_sql(self, field_name: str) -> str:
        pass

    @abstractmethod
    def get_table_metadata_sql(self, table_name: str) -> str:
        pass

    def get_condition_sql(self, field_name: str, operator: str, field_type: str) -> Tuple[str, Optional[callable]]:
        field = self.quote_identifier(validate_identifier(field_name))
        op = OPERATOR_MAP.get(operator, "=")
        if op in ("IN", "NOT IN"):
            return f"{field} {op} (%s)", None
        if op == "LIKE":
            return f"{field} {op} %s", lambda v: f"%{escape_value(v, field_type)}%"
        return f"{field} {op} %s", lambda v: escape_value(v, field_type)

    def quote_identifier(self, name: str) -> str:
        return f"{self.IDENTIFIER_QUOTE}{name}{self.IDENTIFIER_QUOTE}"

class MySQLAdapter(BaseDatabaseAdapter):
    FIELD_TYPE_MAP = {"IntField": "INT", "CharField": "VARCHAR", "UUIDField": "CHAR", "ForeignKeyField": "INT"}
    AUTO_INCREMENT_SUFFIX = "AUTO_INCREMENT"
    IDENTIFIER_QUOTE = "`"

    def get_field_type(self, cls_name: str, inst):
        base = self.FIELD_TYPE_MAP[cls_name]
        if cls_name == "CharField":
            return f"{base}({inst.max_length})"
        if cls_name == "UUIDField":
            return f"{base}(36)"
        return base

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
            constraints.append(f"DEFAULT {inst._format_default(inst.default)}")
        # 自增字段单独处理
        auto_inc = self.get_auto_increment_sql(inst)
        if auto_inc:
            constraints.append(auto_inc)
        return f"ADD COLUMN {name} {typ} {' '.join(constraints)}"

    def get_alter_modify_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        constraints = ["NOT NULL"] if not inst.nullable else []
        if inst.default is not None:
            constraints.append(f"DEFAULT {inst._format_default(inst.default)}")
        # 自增字段单独处理
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

class PostgreSQLAdapter(BaseDatabaseAdapter):
    # 修复核心1：移除SERIAL，改用标准INTEGER类型
    FIELD_TYPE_MAP = {"IntField": "INTEGER", "CharField": "VARCHAR", "UUIDField": "UUID", "ForeignKeyField": "INTEGER"}
    AUTO_INCREMENT_SUFFIX = ""  # 自增逻辑移到get_auto_increment_sql
    IDENTIFIER_QUOTE = '"'

    def get_field_type(self, cls_name: str, inst):
        # 修复：主键IntField返回标准INTEGER，自增通过IDENTITY后缀实现
        base = self.FIELD_TYPE_MAP[cls_name]
        if cls_name == "CharField":
            return f"{base}({inst.max_length})"
        return base

    def get_auto_increment_sql(self, inst):
        # 修复核心2：主键IntField返回IDENTITY列语法（适配PG 10+）
        if inst.primary_key and isinstance(inst, IntField):
            return "GENERATED BY DEFAULT AS IDENTITY"
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
            constraints.append(f"DEFAULT {inst._format_default(inst.default)}")
        # 自增字段（IDENTITY）单独处理
        auto_inc = self.get_auto_increment_sql(inst)
        if auto_inc:
            constraints.append(auto_inc)
        # 修复：PostgreSQL中ALTER ADD COLUMN时，主键约束需单独添加（这里暂不拼接，避免语法错误）
        # 移除：if inst.primary_key: constraints.append("PRIMARY KEY")
        return f"ADD COLUMN {name} {typ} {' '.join(constraints)}"
    def get_alter_modify_field_sql(self, inst):
        name = self.quote_identifier(inst.name)
        typ = self.get_field_type(inst.__class__.__name__, inst)
        parts = []
        # 修改字段类型
        parts.append(f"ALTER COLUMN {name} TYPE {typ}")
        # 修改非空约束
        parts.append(f"ALTER COLUMN {name} SET NOT NULL" if not inst.nullable else f"ALTER COLUMN {name} DROP NOT NULL")
        # 修改默认值
        if inst.default is not None:
            parts.append(f"ALTER COLUMN {name} SET DEFAULT {inst._format_default(inst.default)}")
        # 注意：PG中IDENTITY列的属性修改需要单独语句，这里避免修改主键自增属性（防止报错）
        return ", ".join(parts)

    def get_alter_drop_field_sql(self, name):
        return f"DROP COLUMN {self.quote_identifier(name)}"

    def get_table_metadata_sql(self, table):
        return """SELECT column_name as name, 
                        data_type as type, 
                        is_nullable = 'YES' as nullable, 
                        column_default as default 
                  FROM INFORMATION_SCHEMA.COLUMNS 
                  WHERE table_catalog = CURRENT_DATABASE() 
                  AND table_schema = CURRENT_SCHEMA() 
                  AND table_name = %s;"""

def get_db_adapter(db_type: str) -> BaseDatabaseAdapter:
    db_type = db_type.lower()
    if db_type == "mysql":
        return MySQLAdapter()
    if db_type in ("postgresql", "pg"):
        return PostgreSQLAdapter()
    raise ValueError(f"不支持数据库类型：{db_type}")

# ------------------------------ 4. 自研连接池（无DBUtils）------------------------------
class ConnectionPool:
    def __init__(self, db_type: str, conn_kwargs: Dict, enable: bool = True, pool_config: Dict = None):
        self.db_type = db_type
        self.conn_kwargs = conn_kwargs
        self.enable = enable
        self.cfg = pool_config or POOL_CONFIG
        self.min_idle = self.cfg["mincached"]
        self.max_idle = self.cfg["maxcached"]
        self.max_conn = self.cfg["maxconnections"]
        self.blocking = self.cfg["blocking"]
        self.timeout = self.cfg["idle_timeout"]

        self.idle_queue = queue.Queue(self.max_idle)
        self.active_set = set()
        self.lock = threading.Lock()

        if self.enable:
            self._init_min_conn()

    def _create_conn(self):
        try:
            if self.db_type == "mysql":
                import pymysql
                return pymysql.connect(**self.conn_kwargs, cursorclass=pymysql.cursors.DictCursor, autocommit=True)
            if self.db_type == "postgresql":
                import psycopg2
                from psycopg2 import extras
                conn = psycopg2.connect(**self.conn_kwargs, cursor_factory=extras.DictCursor)
                conn.autocommit = True
                return conn
        except Exception as e:
            raise RuntimeError(f"连接创建失败：{e}")

    def _init_min_conn(self):
        with self.lock:
            for _ in range(self.min_idle):
                if self.idle_queue.full():
                    break
                self.idle_queue.put(ConnectionItem(self._create_conn()))

    def _clean_expired(self):
        if not self.enable:
            return
        with self.lock:
            temp = queue.Queue(self.max_idle)
            while not self.idle_queue.empty():
                item = self.idle_queue.get()
                if not item.is_expired(self.timeout):
                    temp.put(item)
                else:
                    try:
                        item.conn.close()
                    except:
                        pass
            self.idle_queue = temp

    def get_conn(self):
        if not self.enable:
            return self._create_conn()
        self._clean_expired()
        try:
            item = self.idle_queue.get(timeout=5)
            try:
                # 校验连接是否可用
                item.conn.cursor().execute("SELECT 1")
            except:
                item.conn.close()
                item = ConnectionItem(self._create_conn())
            item.update_used_time()
            with self.lock:
                self.active_set.add(item)
            return item.conn
        except queue.Empty:
            with self.lock:
                if len(self.active_set) >= self.max_conn:
                    raise RuntimeError("连接池已达上限")
                conn = self._create_conn()
                item = ConnectionItem(conn)
                self.active_set.add(item)
                return conn

    def release(self, conn):
        if not self.enable or not conn:
            try:
                conn.close()
            except:
                pass
            return
        with self.lock:
            target = None
            for item in self.active_set:
                if item.conn == conn:
                    target = item
                    self.active_set.remove(item)
                    break
            if target:
                target.update_used_time()
                if not self.idle_queue.full():
                    self.idle_queue.put(target)
                else:
                    target.conn.close()

    def close_pool(self):
        if not self.enable:
            return
        while not self.idle_queue.empty():
            try:
                self.idle_queue.get().conn.close()
            except:
                pass
        with self.lock:
            for item in self.active_set:
                try:
                    item.conn.close()
                except:
                    pass
            self.active_set.clear()

# ------------------------------ 5. ORM字段定义 ------------------------------
class Field:
    python_type = "str"
    def __init__(self, primary_key=False, nullable=False, default=None, max_length=None, auto_increment=False, unique=False):
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.max_length = max_length
        self.auto_increment = auto_increment  # 自增属性
        self.unique = unique  # 新增：唯一约束属性
        self.name = None
        self.model = None

    def _format_default(self, value):
        return f"'{value}'" if isinstance(value, str) else value

    def get_sql_def(self, adapter):
        name = validate_identifier(self.name)
        typ = adapter.get_field_type(self.__class__.__name__, self)
        auto_inc = adapter.get_auto_increment_sql(self)
        parts = [adapter.quote_identifier(name), typ]
        if auto_inc:
            parts.append(auto_inc)
        if not self.nullable:
            parts.append("NOT NULL")
        if self.unique and not self.primary_key:  # 主键默认唯一，无需重复加
            parts.append("UNIQUE")
        # 修复核心：移除条件判断，主键字段强制添加PRIMARY KEY约束
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if self.default is not None:
            parts.append(f"DEFAULT {self._format_default(self.default)}")
        return " ".join(parts)

class IntField(Field):
    python_type = "int"
    # 修复核心2：IntField作为主键时，自动设置auto_increment=True
    def __init__(self, primary_key=False, nullable=False, default=None, max_length=None):
        # 主键IntField默认开启自增
        auto_increment = primary_key
        super().__init__(primary_key, nullable, default, max_length, auto_increment)

class CharField(Field):
    python_type = "str"
    def __init__(self, primary_key=False, nullable=False, default=None, max_length=255, unique=False):
        # 字符型字段默认不自增
        super().__init__(primary_key, nullable, default, max_length, auto_increment=False)

class ForeignKeyField(Field):
    python_type = "int"
    def __init__(self, to_model, on_delete="CASCADE", nullable=True):
        # 外键字段默认不自增
        super().__init__(nullable=nullable, auto_increment=False)
        self.to_model = to_model
        self.on_delete = on_delete.upper()

class ManyToManyField(Field):
    def __init__(self, to_model):
        # 多对多字段默认不自增
        super().__init__(nullable=True, auto_increment=False)
        self.to_model = to_model

# ------------------------------ 6. 模型基类与元类 ------------------------------
class ModelMeta(type):
    def __new__(cls, name, bases, attrs):
        if name == "Model":
            return super().__new__(cls, name, bases, attrs)
        fields = {}
        pk = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                validate_identifier(k)
                fields[k] = v
                v.name = k
                v.model = cls
                if v.primary_key:
                    pk = v
        meta = attrs.get("Meta")
        table = getattr(meta, "table_name", name.replace("Model", "").lower())
        table = validate_identifier(table, "table")
        _meta = type("_Meta", (), {"table_name": table, "fields": fields, "primary_key": pk})
        if "Meta" in attrs:
            del attrs["Meta"]
        model_cls = super().__new__(cls, name, bases, attrs)
        model_cls._meta = _meta
        return model_cls
class DoesNotExist(Exception):
    """模型查询无结果时的异常"""
    pass
class Model(metaclass=ModelMeta):
    def __init__(self,** kwargs):
        # 修复核心1：初始化所有模型字段的实例属性，避免读取类属性的字段实例
        for field_name in self._meta.fields.keys():
            # 优先使用kwargs中的值，无则使用字段默认值，仍无则设为None
            if field_name in kwargs:
                setattr(self, field_name, kwargs[field_name])
            else:
                field = self._meta.fields[field_name]
                setattr(self, field_name, field.default if field.default is not None else None)
        
        # 校验传入的字段是否合法
        for k in kwargs.keys():
            if k not in self._meta.fields:
                raise SQLSafetyError(f"无效字段：{k}")

    @classmethod
    def create_table(cls, db, safe=True):
        adapter = db.adapter
        cols = []
        fk_constraints = []  # 新增：存储外键约束
        for f in cls._meta.fields.values():
            if isinstance(f, ManyToManyField):
                continue
            # 拼接字段基础定义
            cols.append(f.get_sql_def(adapter))
            # 新增：如果是外键字段，拼接外键约束
            if isinstance(f, ForeignKeyField):
                target_table = f.to_model._meta.table_name
                target_pk = f.to_model._meta.primary_key.name
                fk_sql = adapter.get_foreign_key_sql(f.name, target_table, target_pk, f)
                fk_constraints.append(fk_sql.lstrip(","))  # 去掉开头的逗号
        
        # 合并字段定义和外键约束
        all_defs = cols + fk_constraints
        sql = f"CREATE TABLE {'IF NOT EXISTS' if safe else ''} {adapter.quote_identifier(cls._meta.table_name)} ({', '.join(all_defs)});"
        db.execute(sql, close_after=True)
        logger.info(f"表 {cls._meta.table_name} 创建完成（含{len(fk_constraints)}个外键约束）")
    @classmethod
    def migrate_table(cls, db, drop_absent=False):
        adapter = db.adapter
        table = cls._meta.table_name
        db_meta = db.get_table_meta(table)  # 该方法内部会处理连接关闭
        model_fields = cls._meta.fields
        cmds = []
        model_keys = set(model_fields.keys())
        db_keys = set(db_meta.keys())

        for k in model_keys - db_keys:
            if isinstance(model_fields[k], ManyToManyField):
                continue
            cmds.append(f"ALTER TABLE {adapter.quote_identifier(table)} {adapter.get_alter_add_field_sql(model_fields[k])};")
        for k in model_keys & db_keys:
            if isinstance(model_fields[k], ManyToManyField):
                continue
            cmds.append(f"ALTER TABLE {adapter.quote_identifier(table)} {adapter.get_alter_modify_field_sql(model_fields[k])};")
        if drop_absent:
            for k in db_keys - model_keys:
                if k == cls._meta.primary_key.name:
                    continue
                cmds.append(f"ALTER TABLE {adapter.quote_identifier(table)} {adapter.get_alter_drop_field_sql(k)};")
        if cmds:
            with db.transaction():
                for cmd in cmds:
                    db.execute(cmd, close_after=True)
        logger.info(f"模型迁移完成，执行{len(cmds)}条语句")
        return cmds

    def save(self, db):
        pk_name = self._meta.primary_key.name
        # 修复核心2：确保pk_val是基础类型（None/数值），而非字段实例
        pk_val = getattr(self, pk_name, None)
        # 额外防护：如果pk_val是字段实例，强制设为None
        if isinstance(pk_val, Field):
            pk_val = None
        
        # 仅当pk_val是有效数值时，才执行更新逻辑
        if pk_val is not None and isinstance(pk_val, (int, str)) and self.get_or_none(db, **{pk_name: pk_val}):
            data = {k: getattr(self, k) for k in self._meta.fields if k != pk_name}
            return self.__class__.update(db, data, **{pk_name: pk_val})
        
        # 新增逻辑
        adapter = db.adapter
        fields = []
        values = []
        for k, f in self._meta.fields.items():
            if isinstance(f, ManyToManyField):
                continue
            # 修复核心3：判断自增主键（现在f.auto_increment属性已存在）
            if f.primary_key and f.auto_increment:
                continue
            fields.append(adapter.quote_identifier(k))
            # 修复核心3：值清洗，确保传递的是基础类型
            val = getattr(self, k, f.default)
            values.append(escape_value(val, f.python_type))
        
        # 修复PostgreSQL自增ID获取：使用RETURNING子句
        if db.type == "postgresql":
            sql = f"""
                INSERT INTO {adapter.quote_identifier(self._meta.table_name)} ({', '.join(fields)}) 
                VALUES ({', '.join([adapter.PARAM_PLACEHOLDER]*len(values))})
                RETURNING {adapter.quote_identifier(pk_name)};
            """
        else:
            sql = f"INSERT INTO {adapter.quote_identifier(self._meta.table_name)} ({', '.join(fields)}) VALUES ({', '.join([adapter.PARAM_PLACEHOLDER]*len(values))});"
        
        return db.execute(sql, tuple(values), return_id=True, close_after=True)
    @classmethod
    def _build_where_clause(cls, conditions):
        """
        构建WHERE子句和参数列表（安全的参数化查询，避免注入）
        :param conditions: 查询条件字典，如 {"username": "admin", "age": 25}
        :return: (where_clause_str, params_list)
        """
        if not conditions:
            return "", []  # 无条件时返回空WHERE子句和空参数
        
        # 拼接条件表达式（如 "username = %s", "age = %s"）
        where_conditions = []
        params = []
        for field_name, value in conditions.items():
            # 验证字段名合法性（复用原有注入检测逻辑）
            validate_identifier(field_name)
            # 拼接字段条件（参数化占位符 %s）
            where_conditions.append(f"{field_name} = %s")
            params.append(value)
        
        # 组合成完整WHERE子句（多个条件用AND连接）
        where_clause = "WHERE " + " AND ".join(where_conditions)
        return where_clause, params
    @classmethod
    def get_or_none(cls, db, **conditions):
        """查询单行（无结果返回None），新增注入检测"""
        # 1. 检测条件字段名是否危险
        for k in conditions.keys():
            if validate_identifier(k) is None:
                raise SQLSafetyError(f"危险字段名：{k}")
        # 2. 检测条件参数值是否含注入特征
        for v in conditions.values():
            if detect_sql_injection(str(v)):
                raise SQLSafetyError(f"检测到SQL注入特征：{v}")
        # 3. 拼接SQL并执行（原有逻辑）
        where_clause, params = cls._build_where_clause(conditions)
        sql = f"SELECT * FROM {cls._meta.table_name} {where_clause} LIMIT 1;"
        result = db.fetch_one(sql, params)
        if result:
            return cls(**result)
        return None

    @classmethod
    def get(cls, db, **conditions):
        """查询单行（无结果抛异常），复用注入检测"""
        instance = cls.get_or_none(db, **conditions)
        if not instance:
            raise DoesNotExist(f"{cls.__name__} 未找到匹配记录")
        return instance
    # 补充：添加update方法（原代码缺失，导致测试用例报错）
    @classmethod
    def update(cls, db, data: Dict, **kwargs):
        adapter = db.adapter
        validate_model_fields(cls, list(data.keys()) + list(kwargs.keys()))
        
        # 构建SET子句
        set_clause = []
        set_params = []
        for k, v in data.items():
            set_clause.append(f"{adapter.quote_identifier(k)} = %s")
            set_params.append(escape_value(v, cls._meta.fields[k].python_type))
        
        # 构建WHERE子句
        where_clause = []
        where_params = []
        for k, v in kwargs.items():
            where_clause.append(f"{adapter.quote_identifier(k)} = %s")
            where_params.append(escape_value(v, cls._meta.fields[k].python_type))
        
        sql = f"""
            UPDATE {adapter.quote_identifier(cls._meta.table_name)} 
            SET {', '.join(set_clause)} 
            WHERE {' AND '.join(where_clause)}
        """
        return db.execute(sql, tuple(set_params + where_params), close_after=True)

# ------------------------------ 7. 数据库核心类 + 事务 ------------------------------
class Transaction:
    def __init__(self, db):
        self.db = db
        self.has_active_conn = False  # 标记是否有活跃连接

    def __enter__(self):
        try:
            self.db.begin()
            self.has_active_conn = True  # 连接创建成功
        except Exception as e:
            logger.error(f"事务开启失败：{e}")
            self.has_active_conn = False
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 只有存在活跃连接时才执行回滚/提交
        if self.has_active_conn:
            try:
                if exc_type:
                    self.db.rollback()
                    logger.warning(f"事务回滚：{exc_val}")
                else:
                    self.db.commit()
                    logger.info("事务提交成功")
            except Exception as e:
                logger.error(f"事务提交/回滚失败：{e}")
        return False  # 不抑制异常

class Database:
    def __init__(self, db_type: str, pool_enable: bool = False,** kwargs):
        self.type = db_type
        self.adapter = get_db_adapter(db_type)
        self.pool = ConnectionPool(db_type, kwargs, pool_enable)
        self.conn = None
        self.cursor = None

    def connect(self):
        """确保连接和游标存在（带异常处理）"""
        try:
            if not self.conn or (hasattr(self.conn, 'closed') and self.conn.closed):
                self.conn = self.pool.get_conn()
            if not self.cursor or (hasattr(self.cursor, 'closed') and self.cursor.closed):
                self.cursor = self.conn.cursor()
            return True
        except Exception as e:
            logger.error(f"连接创建失败：{e}")
            self.close()  # 清理无效连接
            return False

    def close(self):
        """安全关闭游标和连接（归还到连接池）"""
        if self.cursor:
            try:
                self.cursor.close()
            except Exception as e:
                logger.warning(f"游标关闭失败：{e}")
            self.cursor = None
        if self.conn:
            try:
                self.pool.release(self.conn)
            except Exception as e:
                logger.warning(f"连接释放失败：{e}")
            self.conn = None

    def begin(self):
        """开启事务（带连接校验）"""
        if not self.connect():
            raise RuntimeError("无法创建数据库连接，事务开启失败")
        try:
            self.cursor.execute("BEGIN;")
            self.conn.autocommit = False
        except Exception as e:
            self.close()
            raise RuntimeError(f"事务开启失败：{e}")

    def commit(self):
        """提交事务（带空值校验）"""
        if not self.conn:
            logger.warning("无活跃连接，跳过事务提交")
            return
        try:
            self.conn.commit()
            self.conn.autocommit = True
        except Exception as e:
            logger.error(f"事务提交失败：{e}")
            raise
        finally:
            self.close()  # 事务结束后关闭连接

    def rollback(self):
        """回滚事务（带空值校验）"""
        if not self.conn:
            logger.warning("无活跃连接，跳过事务回滚")
            return
        try:
            self.conn.rollback()
            self.conn.autocommit = True
        except Exception as e:
            logger.error(f"事务回滚失败：{e}")
            raise
        finally:
            self.close()  # 事务结束后关闭连接

    def transaction(self):
        """创建事务上下文管理器"""
        return Transaction(self)

    def execute(self, sql, params=(), return_id=False, close_after=False):
        """
        执行SQL语句
        :param sql: SQL语句
        :param params: 参数
        :param return_id: 是否返回自增ID
        :param close_after: 执行后是否立即关闭连接（非查询操作建议设为True）
        """
        result = None
        try:
            if not self.connect():  # 确保连接/游标存在
                raise RuntimeError("无法创建数据库连接，SQL执行失败")
            
            self.cursor.execute(sql, params)
            
            if self.conn.autocommit:
                self.conn.commit()
            
            # 获取自增ID
            if return_id:
                if self.type == "mysql":
                    result = self.cursor.lastrowid
                elif self.type == "postgresql":
                    # PostgreSQL使用RETURNING子句返回ID
                    result = self.cursor.fetchone()[0] if self.cursor.rowcount > 0 else None
            else:
                result = self.cursor.rowcount
            
            return result
        except Exception as e:
            self.rollback()
            logger.error(f"SQL执行失败：{e}")
            raise
        finally:
            # 仅在非查询操作且指定close_after时关闭，查询操作由fetch_one/fetch_all处理
            if close_after and self.conn and self.conn.autocommit:
                self.close()

    def fetch_one(self, sql, params=()):
        """执行查询并返回单行结果（自动处理连接关闭）"""
        try:
            self.execute(sql, params, close_after=False)  # 不立即关闭
            return self.cursor.fetchone() if self.cursor else None
        finally:
            self.close()  # 读取结果后关闭

    def fetch_all(self, sql, params=()):
        """执行查询并返回所有结果（自动处理连接关闭）"""
        try:
            self.execute(sql, params, close_after=False)  # 不立即关闭
            return self.cursor.fetchall() if self.cursor else []
        finally:
            self.close()  # 读取结果后关闭

    def get_table_meta(self, table):
        """获取表元数据（内部调用fetch_all，自动处理连接）"""
        sql = self.adapter.get_table_metadata_sql(table)
        return {r["name"]: r for r in self.fetch_all(sql, (table,))}

# 快捷初始化函数（对齐Peewee）
def MySQLDatabase(database: str, user: str, password: str, host="127.0.0.1", port=3306, pool_enable=True):
    return Database("mysql", pool_enable, host=host, port=port, user=user, password=password, database=database, charset="utf8mb4")

def PostgresqlDatabase(database: str, user: str, password: str, host="127.0.0.1", port=5432, pool_enable=True):
    return Database("postgresql", pool_enable, host=host, port=port, user=user, password=password, database=database)

# ------------------------------ 8. 全场景使用用例 ------------------------------
if __name__ == "__main__":
    # ======================================
    # 配置区域：修改为你的数据库信息
    # ======================================                     
    DB = PostgresqlDatabase(
        database="admin_system",
        host="127.0.0.1",
        port=5432,
        user="postgres",
        password="postgres",
        pool_enable=True
    )
    try:
        # ========== 步骤1：定义数据模型 ==========
        class UserModel(Model):
            id = IntField(primary_key=True)
            username = CharField(nullable=False, max_length=32)
            email = CharField(nullable=True, default="")
            class Meta:
                table_name = "sys_user"

        class OrderModel(Model):
            id = IntField(primary_key=True)
            order_no = CharField(nullable=False, max_length=32)  # 现在能正常通过校验
            amount = IntField(nullable=False, default=0)
            user_id = ForeignKeyField(to_model=UserModel, on_delete="CASCADE")
            class Meta:
                table_name = "sys_order"

        # ========== 步骤2：建表 + 模型迁移 ==========
        UserModel.create_table(DB)
        OrderModel.create_table(DB)
        # 模拟字段变更：给用户表添加手机号字段
        class UserModel(Model):
            id = IntField(primary_key=True)
            username = CharField(nullable=False, max_length=32)
            email = CharField(nullable=True, default="")
            phone = CharField(nullable=True, max_length=11)  # 新增字段
            class Meta:
                table_name = "sys_user"
        UserModel.migrate_table(DB)
        logger.info("表结构初始化/迁移完成")

        # ========== 步骤3：事务批量插入数据 ==========
        with DB.transaction():
            # 新增用户
            user1 = UserModel(username="admin", email="admin@test.com", phone="13800138000")
            user1_id = user1.save(DB)
            user1.id = user1_id  # 补充自增ID
            user2 = UserModel(username="test", email="test@test.com", phone="13900139000")
            user2_id = user2.save(DB)
            user2.id = user2_id  # 补充自增ID

            # 新增订单
            order1 = OrderModel(order_no="ORD20260001", amount=99, user_id=user1.id)
            order1.save(DB)
            order2 = OrderModel(order_no="ORD20260002", amount=199, user_id=user2.id)
            order2.save(DB)
        logger.info("事务插入数据完成")

        # ========== 步骤4：基础CRUD查询 ==========
        # 单条查询
        user = UserModel.get(DB, username="admin")
        logger.info(f"查询用户：{user.username} | {user.phone}")
        # 条件查询
        order = OrderModel.get_or_none(DB, amount=199)
        if order:
            logger.info(f"查询订单：{order.order_no}")

        # ========== 步骤5：数据更新 ==========
        UserModel.update(DB, {"phone": "13899998888"}, username="admin")
        updated_user = UserModel.get(DB, username="admin")
        logger.info(f"更新后手机号：{updated_user.phone}")

        # ========== 步骤6：资源释放 ==========
    except Exception as e:
        logger.error(f"执行异常：{e}")
        import traceback
        traceback.print_exc()  # 打印详细堆栈信息
    finally:
        DB.close()
        DB.pool.close_pool()
        logger.info("数据库连接与连接池已安全关闭")