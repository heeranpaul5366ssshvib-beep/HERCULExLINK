from __future__ import annotations
"""
HERCULE AI Operating System
Module: Database Ability
Author: Heeran Paul
License: MIT

Real implementation: SQLite, PostgreSQL, MySQL database operations.
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from abilities.base_ability import BaseAbility


@dataclass
class DBConfig:
    type: str = "sqlite"  # sqlite, postgresql, mysql
    host: str = ""
    port: int = 0
    database: str = ""
    user: str = ""
    password: str = ""
    path: str = ""  # for sqlite


class DatabaseAbility(BaseAbility):

    def __init__(self):
        super().__init__(
            "database",
            "Database operations: query, insert, update, delete, schema",
            capability="DATABASE_READ",
            inputs={
                "operation": "query|execute|schema|tables|connect|disconnect",
                "config": "database connection config",
                "sql": "SQL query/statement",
                "params": "parameters for parameterized queries",
                "fetch": "one|all|many (default: all)",
            },
            outputs={
                "rows": "query results",
                "rowcount": "affected rows",
                "schema": "table schema info",
                "tables": "list of tables",
            },
            permissions=["DATABASE_READ", "DATABASE_WRITE"],
            environments={"default"},
            verification="query executed, results returned",
            timeout_s=60,
            risk="HIGH",
        )
        self._connections: Dict[str, Any] = {}
        self._default_config: Optional[DBConfig] = None

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            op = task.get("operation", "")
            if not op:
                return "operation is required"
            if op in ("query", "execute") and not task.get("sql"):
                return f"{op} requires sql"
            if op == "connect" and not task.get("config"):
                return "connect requires config"
            return ""
        text = str(task or "")
        if not text.strip():
            return "empty database request"
        return ""

    def execute(self, task, context=None, **kwargs) -> Dict[str, Any]:
        if isinstance(task, dict):
            operation = str(task.get("operation", "")).lower()
            config = task.get("config")
            sql = task.get("sql", "")
            params = task.get("params") or []
            fetch = task.get("fetch", "all")
        else:
            text = str(task or "").strip()
            if text.upper().startswith("SELECT") or text.upper().startswith("WITH"):
                operation = "query"
                sql = text
                params = []
                fetch = "all"
                config = None
            else:
                return {"status": "failed", "error": "specify operation and sql"}

        try:
            if operation == "connect":
                return self._connect(config)
            elif operation == "disconnect":
                return self._disconnect(config.get("name", "default") if config else "default")
            elif operation == "query":
                return self._query(sql, params, fetch, config)
            elif operation == "execute":
                return self._execute(sql, params, config)
            elif operation == "schema":
                return self._schema(config)
            elif operation == "tables":
                return self._tables(config)
            else:
                return {"status": "failed", "error": f"unknown operation: {operation}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:500]}

    def _get_connection(self, config: Optional[DBConfig]) -> Any:
        if not config:
            if not self._default_config:
                self._default_config = DBConfig(type="sqlite", path=":memory:")
            config = self._default_config

        key = f"{config.type}://{config.host}:{config.port}/{config.database}" if config.type != "sqlite" else f"sqlite://{config.path}"
        if key in self._connections:
            conn = self._connections[key]
            try:
                conn.execute("SELECT 1")
                return conn
            except Exception:
                pass  # connection dead, recreate

        if config.type == "sqlite":
            path = config.path or ":memory:"
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
        elif config.type == "postgresql":
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=config.host, port=config.port,
                    database=config.database, user=config.user, password=config.password
                )
            except ImportError:
                raise RuntimeError("psycopg2 not installed")
        elif config.type == "mysql":
            try:
                import pymysql
                conn = pymysql.connect(
                    host=config.host, port=config.port,
                    database=config.database, user=config.user, password=config.password
                )
            except ImportError:
                raise RuntimeError("pymysql not installed")
        else:
            raise ValueError(f"unsupported database type: {config.type}")

        self._connections[key] = conn
        return conn

    def _connect(self, config: Dict[str, Any]) -> Dict[str, Any]:
        db_config = DBConfig(
            type=config.get("type", "sqlite"),
            host=config.get("host", ""),
            port=config.get("port", 0),
            database=config.get("database", ""),
            user=config.get("user", ""),
            password=config.get("password", ""),
            path=config.get("path", ""),
        )
        name = config.get("name", "default")
        key = f"{db_config.type}://{db_config.host}:{db_config.port}/{db_config.database}" if db_config.type != "sqlite" else f"sqlite://{db_config.path}"
        try:
            conn = self._get_connection(db_config)
            conn.execute("SELECT 1")
            self._connections[key] = conn
            return {"status": "success", "operation": "connect", "name": name, "type": db_config.type}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _disconnect(self, name: str) -> Dict[str, Any]:
        for key, conn in list(self._connections.items()):
            if name in key:
                try:
                    conn.close()
                except Exception:
                    pass
                del self._connections[key]
                return {"status": "success", "operation": "disconnect", "name": name}
        return {"status": "failed", "error": f"no connection named: {name}"}

    def _query(self, sql: str, params: List[Any], fetch: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        db_config = None
        if config:
            db_config = DBConfig(
                type=config.get("type", "sqlite"),
                host=config.get("host", ""),
                port=config.get("port", 0),
                database=config.get("database", ""),
                user=config.get("user", ""),
                password=config.get("password", ""),
                path=config.get("path", ""),
            )
        conn = self._get_connection(db_config)
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            if fetch == "one":
                row = cursor.fetchone()
                rows = [dict(row)] if row else []
            elif fetch == "many":
                rows = [dict(r) for r in cursor.fetchmany(100)]
            else:
                rows = [dict(r) for r in cursor.fetchall()]
            return {
                "status": "success",
                "operation": "query",
                "rows": rows,
                "rowcount": len(rows),
            }
        finally:
            cursor.close()

    def _execute(self, sql: str, params: List[Any], config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        db_config = None
        if config:
            db_config = DBConfig(
                type=config.get("type", "sqlite"),
                host=config.get("host", ""),
                port=config.get("port", 0),
                database=config.get("database", ""),
                user=config.get("user", ""),
                password=config.get("password", ""),
                path=config.get("path", ""),
            )
        conn = self._get_connection(db_config)
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            conn.commit()
            return {
                "status": "success",
                "operation": "execute",
                "rowcount": cursor.rowcount,
                "lastrowid": cursor.lastrowid,
            }
        finally:
            cursor.close()

    def _schema(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        db_config = None
        if config:
            db_config = DBConfig(
                type=config.get("type", "sqlite"),
                host=config.get("host", ""),
                port=config.get("port", 0),
                database=config.get("database", ""),
                user=config.get("user", ""),
                password=config.get("password", ""),
                path=config.get("path", ""),
            )
        conn = self._get_connection(db_config)
        cursor = conn.cursor()
        try:
            if db_config and db_config.type == "sqlite":
                cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                schema = {}
                for table in tables:
                    name = table[0]
                    cursor.execute(f"PRAGMA table_info({name})")
                    cols = cursor.fetchall()
                    schema[name] = {
                        "create_sql": table[1],
                        "columns": [{"name": c[1], "type": c[2], "notnull": c[3], "default": c[4], "pk": c[5]} for c in cols]
                    }
                return {"status": "success", "operation": "schema", "schema": schema}
            else:
                return {"status": "failed", "error": "schema only implemented for sqlite"}
        finally:
            cursor.close()

    def _tables(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        db_config = None
        if config:
            db_config = DBConfig(
                type=config.get("type", "sqlite"),
                host=config.get("host", ""),
                port=config.get("port", 0),
                database=config.get("database", ""),
                user=config.get("user", ""),
                password=config.get("password", ""),
                path=config.get("path", ""),
            )
        conn = self._get_connection(db_config)
        cursor = conn.cursor()
        try:
            if db_config and db_config.type == "sqlite":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                return {"status": "success", "operation": "tables", "tables": tables}
            else:
                return {"status": "failed", "error": "tables only implemented for sqlite"}
        finally:
            cursor.close()