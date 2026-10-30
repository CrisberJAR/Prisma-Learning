"""Supabase en memoria para tests: tablas, auth.admin y storage, sin red."""
import uuid
from types import SimpleNamespace


class _Resultado:
    def __init__(self, data):
        self.data = data


class _Consulta:
    def __init__(self, db: "FakeDb", tabla: str):
        self.db = db
        self.tabla = tabla
        self.op = "select"
        self.payload = None
        self.filtros = []
        self.tope = None
        self.on_conflict = "id"

    def _columna(self, col: str) -> None:
        if col in self.db.faltantes.get(self.tabla, set()):
            raise Exception(f'column "{col}" of relation "{self.tabla}" does not exist')

    def select(self, *_a, **_k):
        return self

    def eq(self, col, valor):
        self._columna(col)
        self.filtros.append(lambda f: f.get(col) == valor)
        return self

    def in_(self, col, valores):
        valores = list(valores)
        self.filtros.append(lambda f: f.get(col) in valores)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.tope = n
        return self

    def insert(self, fila):
        self.op, self.payload = "insert", dict(fila)
        return self

    def update(self, campos):
        self.op, self.payload = "update", dict(campos)
        return self

    def upsert(self, fila, on_conflict="id"):
        if isinstance(fila, list):
            # Varias filas: se aplican una a una y se devuelven todas juntas.
            self.op, self.lote, self.on_conflict = "upsert_lote", [dict(f) for f in fila], on_conflict
            return self
        self.op, self.payload, self.on_conflict = "upsert", dict(fila), on_conflict
        return self

    def delete(self):
        self.op = "delete"
        return self

    def execute(self):
        self.db.consultas.append((self.tabla, self.op))
        filas = self.db.tablas.setdefault(self.tabla, [])
        for col in (self.payload or {}):
            self._columna(col)
        coinciden = [f for f in filas if all(p(f) for p in self.filtros)]
        if self.op == "select":
            out = coinciden[: self.tope] if self.tope else coinciden
            return _Resultado([dict(f) for f in out])
        if self.op == "insert":
            fila = {"id": str(uuid.uuid4()), **self.payload}
            filas.append(fila)
            return _Resultado([dict(fila)])
        if self.op == "upsert_lote":
            out = []
            for fila in self.lote:
                sub = _Consulta(self.db, self.tabla).upsert(fila, on_conflict=self.on_conflict)
                out += sub.execute().data
            return _Resultado(out)
        if self.op == "upsert":
            clave = self.payload.get(self.on_conflict)
            existente = next((f for f in filas if f.get(self.on_conflict) == clave), None)
            if existente:
                existente.update(self.payload)
                return _Resultado([dict(existente)])
            filas.append(dict(self.payload))
            return _Resultado([dict(self.payload)])
        if self.op == "update":
            for f in coinciden:
                f.update(self.payload)
            return _Resultado([dict(f) for f in coinciden])
        if self.op == "delete":
            self.db.tablas[self.tabla] = [f for f in filas if f not in coinciden]
            return _Resultado([dict(f) for f in coinciden])
        raise AssertionError(self.op)


class _Admin:
    def __init__(self, db: "FakeDb"):
        self.db = db
        self.usuarios: list[SimpleNamespace] = []
        self.claves: dict[str, str] = {}
        self.error_crear: Exception | None = None

    def agregar(self, email: str) -> SimpleNamespace:
        u = SimpleNamespace(id=str(uuid.uuid4()), email=email)
        self.usuarios.append(u)
        return u

    def create_user(self, attrs):
        if self.error_crear:
            raise self.error_crear
        if any(u.email == attrs["email"] for u in self.usuarios):
            raise Exception("A user with this email address has already been registered")
        u = self.agregar(attrs["email"])
        self.claves[u.id] = attrs["password"]
        return SimpleNamespace(user=u)

    def list_users(self, page=1, per_page=50):
        inicio = (page - 1) * per_page
        return self.usuarios[inicio : inicio + per_page]

    def update_user_by_id(self, uid, attrs):
        if "password" in attrs:
            self.claves[uid] = attrs["password"]
        return SimpleNamespace(user=SimpleNamespace(id=uid))

    def get_user_by_id(self, uid):
        u = next(u for u in self.usuarios if u.id == uid)
        return SimpleNamespace(user=u)


class _Bucket:
    def __init__(self, db):
        self.db = db

    def remove(self, rutas):
        self.db.borrados.extend(rutas)


class FakeDb:
    def __init__(self, faltantes: dict[str, set[str]] | None = None):
        self.tablas: dict[str, list[dict]] = {}
        self.faltantes = faltantes or {}
        self.consultas: list[tuple[str, str]] = []
        self.borrados: list[str] = []
        self.auth = SimpleNamespace(admin=_Admin(self))
        self.storage = SimpleNamespace(from_=lambda _bucket: _Bucket(self))

    def table(self, nombre: str) -> _Consulta:
        return _Consulta(self, nombre)


def usar(monkeypatch, db: FakeDb) -> FakeDb:
    """Hace que todos los servicios usen esta base falsa."""
    for modulo in ("services.cursos", "services.cuentas", "services.storage", "services.materiales", "services.auth"):
        monkeypatch.setattr(f"{modulo}.get_service_client", lambda: db, raising=False)
    return db
