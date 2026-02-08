#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
from core.orm.pool import get_db_pool
# from config.settings import POOL_INSTANCE_NAME
from utils.logger import logger

class Field:
    """ORM字段基类"""
    def __init__(self, primary_key=False, default=None, nullable=True, unique=False, comment=""):
        self.name = None  # 字段名（由Model元类设置）
        self.model = None  # 所属模型（由Model元类设置）
        self.primary_key = primary_key
        self.default = default
        self.nullable = nullable
        self.unique = unique
        self.comment = comment

    def get_default(self):
        """获取字段默认值"""
        if callable(self.default):
            return self.default()
        return self.default

    def to_db_value(self, value):
        """Python值转数据库值"""
        if value is None:
            return None
        return self._to_db(value)

    def from_db_value(self, value):
        """数据库值转Python值"""
        if value is None:
            return None
        return self._from_db(value)

    def _to_db(self, value):
        """子类实现具体转换"""
        return value

    def _from_db(self, value):
        """子类实现具体转换"""
        return value

class ModelMeta(type):
    """Model元类：自动收集字段，生成表结构相关信息"""
    def __new__(cls, name, bases, attrs):
        # 跳过基类Model本身
        if name == "Model":
            return super().__new__(cls, name, bases, attrs)
        
        new_cls = super().__new__(cls, name, bases, attrs)
        new_cls._meta = {
            "table_name": attrs.get("__table_name__", name.lower()),  # 表名（默认类名小写）
            "fields": {},  # 所有字段 {字段名: 字段实例}
            "primary_key": None  # 主键字段
        }

        # 收集所有字段
        for attr_name, attr_value in attrs.items():
            if isinstance(attr_value, Field):
                # 设置字段名和所属模型
                attr_value.name = attr_name
                attr_value.model = new_cls
                new_cls._meta["fields"][attr_name] = attr_value
                # 标记主键
                if attr_value.primary_key:
                    if new_cls._meta["primary_key"] is not None:
                        raise ValueError(f"Model {name} can only have one primary key")
                    new_cls._meta["primary_key"] = attr_name

        # 检查主键
        if new_cls._meta["primary_key"] is None:
            raise ValueError(f"Model {name} must have a primary key field")
        
        logger.debug(f"[ORM] Initialize model {name}, table: {new_cls._meta['table_name']}, fields: {list(new_cls._meta['fields'].keys())}")
        return new_cls

class Model(metaclass=ModelMeta):
    """ORM模型基类：提供CRUD核心方法"""
    __table_name__ = None  # 自定义表名（可选）

    def __init__(self, **kwargs):
        """初始化模型实例：给字段赋值"""
        self._dirty_fields = set()  # 脏字段（已修改未保存）
        meta = self._meta
        for field_name, field in meta["fields"].items():
            value = kwargs.get(field_name, field.get_default())
            setattr(self, field_name, value)

    def __repr__(self):
        pk_name = self._meta["primary_key"]
        pk_value = getattr(self, pk_name, None)
        return f"<{self.__class__.__name__} {pk_name}={pk_value}>"

    @property
    def _pk_value(self):
        """获取主键值"""
        return getattr(self, self._meta["primary_key"])

    def _mark_dirty(self, field_name):
        """标记字段为脏字段"""
        self._dirty_fields.add(field_name)

    def __setattr__(self, name, value):
        """重写赋值：自动标记脏字段"""
        if name in self._meta["fields"] and hasattr(self, name) and getattr(self, name) != value:
            self._mark_dirty(name)
        super().__setattr__(name, value)

    @classmethod
    def _get_cursor(cls):
        """获取数据库游标（从连接池）"""
        pool = get_db_pool(POOL_INSTANCE_NAME)
        conn = pool.get_connection()
        cursor = conn.cursor()
        return conn, cursor

    @classmethod
    def _release_cursor(cls, conn, cursor, commit=False):
        """释放游标和连接"""
        try:
            cursor.close()
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"[ORM] Database operation error: {str(e)}", exc_info=True)
            raise
        finally:
            conn.close()

    @classmethod
    def get(cls, **kwargs):
        """根据条件获取单条记录"""
        if not kwargs:
            raise ValueError("get() requires at least one condition")
        
        # 构建查询条件
        where_clause = " AND ".join([f"{k} = %s" for k in kwargs.keys()])
        params = [cls._meta["fields"][k].to_db_value(v) for k, v in kwargs.items()]
        sql = f"SELECT * FROM {cls._meta['table_name']} WHERE {where_clause} LIMIT 1"

        conn, cursor = cls._get_cursor()
        try:
            cursor.execute(sql, params)
            result = cursor.fetchone()
            if not result:
                return None
            # 获取字段名列表
            fields = [desc[0] for desc in cursor.description]
            # 转换为模型实例
            data = dict(zip(fields, result))
            instance = cls()
            for field_name, field in cls._meta["fields"].items():
                setattr(instance, field_name, field.from_db_value(data.get(field_name)))
            instance._dirty_fields.clear()  # 新实例无脏字段
            return instance
        finally:
            cls._release_cursor(conn, cursor)

    @classmethod
    def filter(cls, **kwargs):
        """根据条件获取多条记录（支持简单条件）"""
        where_clause = "1=1"
        params = []
        if kwargs:
            where_clause = " AND ".join([f"{k} = %s" for k in kwargs.keys()])
            params = [cls._meta["fields"][k].to_db_value(v) for k, v in kwargs.items()]
        sql = f"SELECT * FROM {cls._meta['table_name']} WHERE {where_clause}"

        conn, cursor = cls._get_cursor()
        try:
            cursor.execute(sql, params)
            results = cursor.fetchall()
            fields = [desc[0] for desc in cursor.description]
            instances = []
            for row in results:
                data = dict(zip(fields, row))
                instance = cls()
                for field_name, field in cls._meta["fields"].items():
                    setattr(instance, field_name, field.from_db_value(data.get(field_name)))
                instance._dirty_fields.clear()
                instances.append(instance)
            return instances
        finally:
            cls._release_cursor(conn, cursor)

    @classmethod
    def paginate(cls, page=1, page_size=10, **kwargs):
        """分页查询"""
        if page < 1:
            page = 1
        offset = (page - 1) * page_size

        # 总数查询
        count_where = "1=1"
        count_params = []
        if kwargs:
            count_where = " AND ".join([f"{k} = %s" for k in kwargs.keys()])
            count_params = [cls._meta["fields"][k].to_db_value(v) for k, v in kwargs.items()]
        count_sql = f"SELECT COUNT(*) FROM {cls._meta['table_name']} WHERE {count_where}"

        # 列表查询
        list_where = count_where
        list_params = count_params.copy()
        list_sql = f"SELECT * FROM {cls._meta['table_name']} WHERE {list_where} LIMIT %s OFFSET %s"
        list_params.extend([page_size, offset])

        conn, cursor = cls._get_cursor()
        try:
            # 获取总数
            cursor.execute(count_sql, count_params)
            total = cursor.fetchone()[0]
            # 获取列表
            cursor.execute(list_sql, list_params)
            results = cursor.fetchall()
            fields = [desc[0] for desc in cursor.description]
            instances = []
            for row in results:
                data = dict(zip(fields, row))
                instance = cls()
                for field_name, field in cls._meta["fields"].items():
                    setattr(instance, field_name, field.from_db_value(data.get(field_name)))
                instance._dirty_fields.clear()
                instances.append(instance)
            # 分页信息
            total_pages = (total + page_size - 1) // page_size
            return {
                "list": instances,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        finally:
            cls._release_cursor(conn, cursor)

    def save(self):
        """保存实例：新增或更新（根据主键是否存在）"""
        if self._pk_value is None:
            return self._insert()
        else:
            return self._update()

    def _insert(self):
        """新增记录"""
        fields = [f for f in self._meta["fields"] if f != self._meta["primary_key"]]
        if not fields:
            raise ValueError("No fields to insert")
        
        field_names = ", ".join(fields)
        placeholders = ", ".join(["%s"] * len(fields))
        sql = f"INSERT INTO {self._meta['table_name']} ({field_names}) VALUES ({placeholders}) RETURNING {self._meta['primary_key']}"
        params = [self._meta["fields"][f].to_db_value(getattr(self, f)) for f in fields]

        conn, cursor = self._get_cursor()
        try:
            cursor.execute(sql, params)
            # 获取自增主键值
            pk_value = cursor.fetchone()[0]
            setattr(self, self._meta["primary_key"], self._meta["fields"][self._meta["primary_key"]].from_db_value(pk_value))
            self._dirty_fields.clear()
            logger.debug(f"[ORM] Insert {self.__class__.__name__} {self._pk_value} success")
            return self
        finally:
            self._release_cursor(conn, cursor, commit=True)

    def _update(self):
        """更新记录（仅更新脏字段）"""
        if not self._dirty_fields:
            logger.debug(f"[ORM] No dirty fields to update for {self.__class__.__name__} {self._pk_value}")
            return self
        
        set_clause = ", ".join([f"{f} = %s" for f in self._dirty_fields])
        sql = f"UPDATE {self._meta['table_name']} SET {set_clause} WHERE {self._meta['primary_key']} = %s"
        params = [self._meta["fields"][f].to_db_value(getattr(self, f)) for f in self._dirty_fields]
        params.append(self._meta["fields"][self._meta["primary_key"]].to_db_value(self._pk_value))

        conn, cursor = self._get_cursor()
        try:
            cursor.execute(sql, params)
            if cursor.rowcount == 0:
                raise ValueError(f"{self.__class__.__name__} {self._pk_value} not found")
            self._dirty_fields.clear()
            logger.debug(f"[ORM] Update {self.__class__.__name__} {self._pk_value} success, affected rows: {cursor.rowcount}")
            return self
        finally:
            self._release_cursor(conn, cursor, commit=True)

    def delete(self):
        """删除记录"""
        if self._pk_value is None:
            raise ValueError("Cannot delete unsaved instance")
        
        sql = f"DELETE FROM {self._meta['table_name']} WHERE {self._meta['primary_key']} = %s"
        params = [self._meta["fields"][self._meta["primary_key"]].to_db_value(self._pk_value)]

        conn, cursor = self._get_cursor()
        try:
            cursor.execute(sql, params)
            if cursor.rowcount == 0:
                raise ValueError(f"{self.__class__.__name__} {self._pk_value} not found")
            logger.debug(f"[ORM] Delete {self.__class__.__name__} {self._pk_value} success")
            return True
        finally:
            self._release_cursor(conn, cursor, commit=True)

    def to_dict(self, desensitize_fields=None):
        """转换为字典，支持敏感字段脱敏"""
        data = {}
        desensitize = desensitize_fields or []
        for field_name, field in self._meta["fields"].items():
            value = getattr(self, field_name)
            # 敏感数据脱敏
            if field_name in desensitize:
                if field_name == "phone" and value and len(value) == 11:
                    value = f"{value[:3]}****{value[-4:]}"
                elif field_name == "email" and value and "@" in value:
                    prefix, suffix = value.split("@", 1)
                    if len(prefix) > 2:
                        prefix = f"{prefix[:2]}****"
                    value = f"{prefix}@{suffix}"
            data[field_name] = value
        return data