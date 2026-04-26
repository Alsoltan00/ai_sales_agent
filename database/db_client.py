import os
from sqlalchemy import create_engine, text

# جلب رابط قاعدة البيانات من المتغيرات البيئية
# يدعم Aiven MySQL أو Aiven PostgreSQL
DB_URL = os.getenv("DATABASE_URL", "")

if DB_URL.startswith("mysql://"):
    DB_URL = DB_URL.replace("mysql://", "mysql+pymysql://")
elif DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+psycopg2://")

engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None

class MockResponse:
    def __init__(self, data):
        self.data = data

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

    def select(self, cols="*"):
        self._action = "SELECT"
        self._select_cols = cols
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
                where_clauses.append(f"{col} = :{p_name}")
                params[p_name] = val
                
            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            if self._action == "SELECT":
                query = f"SELECT {self._select_cols} FROM {self.table_name}{where_sql}"
                if self._limit:
                    query += f" LIMIT {self._limit}"
                
                result = conn.execute(text(query), params)
                rows = [dict(mapping) for mapping in result.mappings()]
                
                if self._single:
                    return MockResponse(rows[0] if rows else None)
                return MockResponse(rows)

            elif self._action == "INSERT":
                if isinstance(self._data, list):
                    # Not fully implemented for lists yet, fallback to single
                    if len(self._data) > 0:
                        data = self._data[0]
                    else:
                        return MockResponse([])
                else:
                    data = self._data
                    
                cols = ", ".join(data.keys())
                vals = ", ".join([f":p_ins_{k}" for k in data.keys()])
                for k, v in data.items():
                    params[f"p_ins_{k}"] = v
                    
                query = f"INSERT INTO {self.table_name} ({cols}) VALUES ({vals})"
                
                # Check for return id (postgres syntax only, ignore for now)
                conn.execute(text(query), params)
                return MockResponse([data]) # mock return

            elif self._action == "UPDATE":
                set_clauses = []
                for k, v in self._data.items():
                    set_clauses.append(f"{k} = :p_upd_{k}")
                    params[f"p_upd_{k}"] = v
                
                set_sql = ", ".join(set_clauses)
                query = f"UPDATE {self.table_name} SET {set_sql}{where_sql}"
                conn.execute(text(query), params)
                return MockResponse([self._data])

            elif self._action == "DELETE":
                query = f"DELETE FROM {self.table_name}{where_sql}"
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

# للأكواد القديمة التي كانت تستدعي get_supabase_client
get_supabase_client = get_db_client
