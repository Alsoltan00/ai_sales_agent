import os
from sqlalchemy import create_engine, text
import json

# جلب رابط قاعدة البيانات من المتغيرات البيئية
# يدعم Aiven MySQL أو Aiven PostgreSQL
DB_URL = os.getenv("DATABASE_URL", "")

if DB_URL:
    if DB_URL.startswith("mysql://"):
        DB_URL = DB_URL.replace("mysql://", "mysql+pymysql://", 1)
    elif DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DB_URL.startswith("postgresql://") and not DB_URL.startswith("postgresql+psycopg2://"):
        DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None

class MockResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if isinstance(data, list) else 0)

class QueryBuilder:
    """يحاكي واجهة Supabase للعمل مع أي قاعدة بيانات علائقية مدعومة (Aiven)"""
    def __init__(self, table_name):
        self.table_name = table_name
        self._action = None
        self._select_cols = "*"
        self._where = []
        self._data = None
        self._limit = None
        self._single = False
        self._order_by = []

    def select(self, cols="*"):
        self._action = "SELECT"
        self._select_cols = cols
        return self

    def order(self, col, desc=False):
        self._order_by.append((col, "DESC" if desc else "ASC"))
        return self

    def insert(self, data):
        self._action = "INSERT"
        self._data = data
        return self

    def update(self, data):
        self._action = "UPDATE"
        self._data = data
        return self

    def delete(self):
        self._action = "DELETE"
        return self

    def eq(self, col, val):
        self._where.append((col, '=', val))
        return self

    def neq(self, col, val):
        self._where.append((col, '!=', val))
        return self

    def limit(self, limit_val):
        self._limit = limit_val
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        if not engine:
            print("WARNING: Database engine not initialized. Check DATABASE_URL")
            return MockResponse(None if self._single else [])

        with engine.begin() as conn:
            params = {}
            where_clauses = []
            
            for i, (col, op, val) in enumerate(self._where):
                p_name = f"p_where_{i}"
                where_clauses.append(f"{col} {op} :{p_name}")
                params[p_name] = val
                
            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            if self._action == "SELECT":
                order_sql = ""
                if self._order_by:
                    clauses = [f"{col} {direction}" for col, direction in self._order_by]
                    order_sql = " ORDER BY " + ", ".join(clauses)
                
                query = f"SELECT {self._select_cols} FROM {self.table_name}{where_sql}{order_sql}"
                if self._limit:
                    query += f" LIMIT {self._limit}"
                
                # print(f"[DB] {query} | Params: {params}")
                result = conn.execute(text(query), params)
                rows = [dict(mapping) for mapping in result.mappings()]
                
                if self._single:
                    return MockResponse(rows[0] if rows else None)
                return MockResponse(rows)

            elif self._action == "INSERT":
                if isinstance(self._data, list):
                    if len(self._data) > 0:
                        data = self._data[0]
                    else:
                        return MockResponse([])
                else:
                    data = self._data
                    
                cols = ", ".join(data.keys())
                vals = ", ".join([f":p_ins_{k}" for k in data.keys()])
                for k, v in data.items():
                    if isinstance(v, (dict, list)):
                        params[f"p_ins_{k}"] = json.dumps(v, ensure_ascii=False)
                    else:
                        params[f"p_ins_{k}"] = v
                    
                is_postgres = "postgres" in str(engine.url) or "postgresql" in str(engine.url)
                
                if is_postgres:
                    query = f"INSERT INTO {self.table_name} ({cols}) VALUES ({vals}) RETURNING *"
                    result = conn.execute(text(query), params)
                    inserted_rows = [dict(mapping) for mapping in result.mappings()]
                    return MockResponse(inserted_rows)
                else:
                    query = f"INSERT INTO {self.table_name} ({cols}) VALUES ({vals})"
                    result = conn.execute(text(query), params)
                    # محاولة جلب المعرف الجديد في حال كان الترقيم تلقائياً
                    try:
                        last_id = result.lastrowid
                        if last_id: data["id"] = last_id
                    except: pass
                    return MockResponse([data])

            elif self._action == "UPDATE":
                set_clauses = []
                for k, v in self._data.items():
                    set_clauses.append(f"{k} = :p_upd_{k}")
                    if isinstance(v, (dict, list)):
                        params[f"p_upd_{k}"] = json.dumps(v, ensure_ascii=False)
                    else:
                        params[f"p_upd_{k}"] = v
                
                set_sql = ", ".join(set_clauses)
                query = f"UPDATE {self.table_name} SET {set_sql}{where_sql}"
                # print(f"[DB] {query} | Params: {params}")
                res = conn.execute(text(query), params)
                # print(f"[DB] Rows affected: {res.rowcount}")
                return MockResponse([self._data])

            elif self._action == "DELETE":
                query = f"DELETE FROM {self.table_name}{where_sql}"
                # print(f"[DB] {query} | Params: {params}")
                conn.execute(text(query), params)
                return MockResponse([])

class DBClient:
    def table(self, table_name: str):
        return QueryBuilder(table_name)

_db_client_instance = None

def get_db_client():
    global _db_client_instance
    if _db_client_instance is None:
        _db_client_instance = DBClient()
    return _db_client_instance

def get_db_engine():
    return engine

# للأكواد القديمة التي كانت تستدعي get_supabase_client
get_supabase_client = get_db_client
