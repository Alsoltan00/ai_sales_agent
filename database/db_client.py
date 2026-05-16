import os
from sqlalchemy import create_engine, text
import json
import uuid
from datetime import datetime, date

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

connect_args = {}
if "postgresql" in DB_URL:
    connect_args = {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "options": "-c statement_timeout=5000"
    }

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_timeout=10,
    echo=False,
    connect_args=connect_args
) if DB_URL else None

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
        self._or_raw = None
        self._data = None
        self._limit = None
        self._single = False
        self._order_by = []
        self._count_mode = None
        self._single = False

    def _process_rows(self, mappings):
        rows = []
        for mapping in mappings:
            row = dict(mapping)
            for k, v in row.items():
                if isinstance(v, uuid.UUID):
                    row[k] = str(v)
                elif isinstance(v, (datetime, date)):
                    row[k] = v.isoformat()
            rows.append(row)
        return rows

    def select(self, cols="*", count=None):
        self._action = "SELECT"
        self._select_cols = cols
        self._count_mode = count
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

    def upsert(self, data):
        self._action = "UPSERT"
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

    def or_(self, raw_filter: str):
        """Supports simple OR filter: 'col.eq.val,col.eq.val' format"""
        self._or_raw = raw_filter
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

        print(f"[DB] Executing {self._action} on {self.table_name}")
        with engine.begin() as conn:
            params = {}
            where_clauses = []
            
            for i, (col, op, val) in enumerate(self._where):
                p_name = f"p_where_{i}"
                where_clauses.append(f"{col} {op} :{p_name}")
                params[p_name] = val

            # Handle .or_() filter (format: "col.eq.val,col.eq.val")
            if self._or_raw:
                or_parts = []
                for part in self._or_raw.split(","):
                    segments = part.strip().split(".")
                    if len(segments) >= 3:
                        or_col = segments[0]
                        or_op = segments[1]
                        or_val = ".".join(segments[2:])
                        op_map = {"eq": "=", "neq": "!=", "like": "LIKE", "ilike": "ILIKE"}
                        sql_op = op_map.get(or_op, "=")
                        p_name = f"p_or_{len(or_parts)}"
                        or_parts.append(f"{or_col} {sql_op} :{p_name}")
                        params[p_name] = or_val
                if or_parts:
                    or_clause = "(" + " OR ".join(or_parts) + ")"
                    where_clauses.append(or_clause)

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
                rows = self._process_rows(result.mappings())
                
                count_val = None
                if self._count_mode == "exact":
                    count_query = f"SELECT COUNT(*) FROM {self.table_name}{where_sql}"
                    count_val = conn.execute(text(count_query), params).scalar()

                if self._single:
                    return MockResponse(rows[0] if rows else None, count=count_val)
                return MockResponse(rows, count=count_val)

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
                    inserted_rows = self._process_rows(result.mappings())
                    return MockResponse(inserted_rows)
                else:
                    query = f"INSERT INTO {self.table_name} ({cols}) VALUES ({vals})"
                    result = conn.execute(text(query), params)
                    try:
                        last_id = result.lastrowid
                        if last_id: data["id"] = last_id
                    except: pass
                    return MockResponse([data])

            elif self._action == "UPSERT":
                if isinstance(self._data, list):
                    data = self._data[0] if len(self._data) > 0 else {}
                else:
                    data = self._data
                
                if not data: return MockResponse([])

                cols = ", ".join(data.keys())
                vals = ", ".join([f":p_upd_{k}" for k in data.keys()])
                for k, v in data.items():
                    params[f"p_upd_{k}"] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                
                is_postgres = "postgres" in str(engine.url) or "postgresql" in str(engine.url)
                
                if is_postgres:
                    # Postgres upsert (assuming client_id or id is the conflict key)
                    conflict_key = "client_id" if "client_id" in data else "id"
                    update_cols = ", ".join([f"{k} = EXCLUDED.{k}" for k in data.keys() if k != conflict_key])
                    query = f"INSERT INTO {self.table_name} ({cols}) VALUES ({vals}) ON CONFLICT ({conflict_key}) DO UPDATE SET {update_cols} RETURNING *"
                    result = conn.execute(text(query), params)
                    rows = self._process_rows(result.mappings())
                    return MockResponse(rows)
                else:
                    # MySQL upsert
                    update_cols = ", ".join([f"{k} = VALUES({k})" for k in data.keys() if k != "id"])
                    query = f"INSERT INTO {self.table_name} ({cols}) VALUES ({vals}) ON DUPLICATE KEY UPDATE {update_cols}"
                    conn.execute(text(query), params)
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
