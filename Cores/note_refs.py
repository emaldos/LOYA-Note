import os
import sqlite3
from Cores import common_db as _common_db
def _norm(s):
    return (str(s) if s is not None else "").strip()
def note_ref_id(value=None, note_id=None):
    raw=note_id
    if raw is None and isinstance(value,dict):
        raw=value.get("note_id",value.get("id",None))
    try:
        return int(str(raw).strip())
    except Exception:
        return None
def note_ref_name(value=None, note_name="", fallback=""):
    raw=note_name
    if not raw and isinstance(value,dict):
        raw=value.get("note_name",value.get("note",value.get("name","")))
    elif not raw and value is not None and not isinstance(value,dict):
        raw=value
    name=_norm(raw)
    return name or _norm(fallback)
def normalize_note_ref(value=None, note_id=None, note_name=""):
    nid=note_ref_id(value,note_id=note_id)
    name=note_ref_name(value,note_name=note_name)
    return {"note_id":nid,"note_name":name}
def serialize_note_ref(value=None, note_id=None, note_name=""):
    ref=normalize_note_ref(value,note_id=note_id,note_name=note_name)
    out={"note_name":ref.get("note_name","")}
    if ref.get("note_id") is not None:
        out["note_id"]=int(ref["note_id"])
    return out
def note_ref_key(value=None, note_id=None, note_name=""):
    ref=normalize_note_ref(value,note_id=note_id,note_name=note_name)
    nid=ref.get("note_id")
    if nid is not None:
        return f"id:{int(nid)}"
    name=ref.get("note_name","")
    if name:
        return f"name:{name.lower()}"
    return ""
def dedupe_note_refs(items):
    out=[];seen=set()
    for item in items or []:
        ref=serialize_note_ref(item)
        key=note_ref_key(ref)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out
def _db_path(value):
    if value:
        return value
    return _common_db.db_path()
def list_note_refs(db_path=""):
    path=_db_path(db_path)
    if not path or not os.path.isfile(path):
        return []
    try:
        with sqlite3.connect(path,timeout=5) as con:
            _common_db.ensure_schema(con)
            cur=con.cursor()
            cur.execute("SELECT id,note_name FROM Notes ORDER BY note_name COLLATE NOCASE,id ASC")
            rows=cur.fetchall()
        return [serialize_note_ref(note_id=r[0],note_name=r[1] or "") for r in rows if _norm(r[1])]
    except Exception:
        return []
def resolve_note_ref(db_path="", value=None, note_id=None, note_name=""):
    path=_db_path(db_path)
    ref=normalize_note_ref(value,note_id=note_id,note_name=note_name)
    if not path or not os.path.isfile(path):
        return serialize_note_ref(ref) if note_ref_key(ref) else None
    try:
        with sqlite3.connect(path,timeout=5) as con:
            _common_db.ensure_schema(con)
            cur=con.cursor()
            nid=ref.get("note_id")
            if nid is not None:
                cur.execute("SELECT id,note_name FROM Notes WHERE id=?",(int(nid),))
                row=cur.fetchone()
                if row:
                    return serialize_note_ref(note_id=row[0],note_name=row[1] or ref.get("note_name",""))
            name=ref.get("note_name","")
            if name:
                cur.execute("SELECT id,note_name FROM Notes WHERE lower(trim(note_name))=lower(trim(?))",(name,))
                row=cur.fetchone()
                if row:
                    return serialize_note_ref(note_id=row[0],note_name=row[1] or name)
    except Exception:
        return serialize_note_ref(ref) if note_ref_key(ref) else None
    return None
