import os
import sqlite3
from datetime import datetime,timezone
DB_SCHEMA_VERSION=6
def _abs(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def data_dir():
    d=_abs("..","Data")
    os.makedirs(d,exist_ok=True)
    return d
def db_path():
    return os.path.join(data_dir(),"Note_LOYA_V1.db")
def table_cols(cur,table):
    try:
        cur.execute(f"PRAGMA table_info({table})")
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []
def _ensure_columns(cur,table,columns):
    cols=set(table_cols(cur,table))
    for name,spec in columns:
        if name not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
def _record_migration(cur,version,applied_at):
    try:
        cur.execute(
            "INSERT OR IGNORE INTO SchemaMigrations(version,applied_at) VALUES(?,?)",
            (int(version),str(applied_at)),
        )
    except Exception:
        pass
def _dedupe_notes_for_unique_name(cur,con):
    try:
        cur.execute("SELECT note_name,MAX(id) FROM Notes GROUP BY note_name HAVING COUNT(*)>1")
        rows=cur.fetchall()
    except Exception:
        rows=[]
    for note_name,keep_id in rows:
        try:
            if note_name is None:
                cur.execute("DELETE FROM Notes WHERE note_name IS NULL AND id<>?",(keep_id,))
            else:
                cur.execute("DELETE FROM Notes WHERE note_name=? AND id<>?",(note_name,keep_id))
        except Exception:
            continue
    try:
        con.commit()
    except Exception:
        pass
def apply_migrations(con):
    try:
        cur=con.cursor()
    except Exception:
        return
    try:
        cur.execute("PRAGMA user_version")
        row=cur.fetchone()
        ver=int(row[0]) if row and str(row[0]).isdigit() else 0
    except Exception:
        ver=0
    now=datetime.now(timezone.utc).isoformat()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS SchemaMigrations(version INTEGER PRIMARY KEY,applied_at TEXT)")
    except Exception:
        pass
    if ver<1:
        _record_migration(cur,1,now)
        ver=1
    if ver<2:
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS NotesHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,group_name TEXT,content TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_hist_note_id ON NotesHistory(note_id)")
        except Exception:
            pass
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS CommandsNotesHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,cmd_id INTEGER,note_name TEXT,category TEXT,sub_category TEXT,command TEXT,tags TEXT,description TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_hist_cmd_id ON CommandsNotesHistory(cmd_id)")
        except Exception:
            pass
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS CommandsHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,cmd_id INTEGER,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_hist_cmd_id ON CommandsHistory(cmd_id)")
        except Exception:
            pass
        _record_migration(cur,2,now)
        ver=2
    if ver<3:
        try:
            _ensure_columns(cur,"Notes",(
                ("note_name","TEXT"),
                ("content","TEXT"),
                ("created_at","TEXT"),
                ("updated_at","TEXT"),
            ))
        except Exception:
            pass
        try:
            _ensure_columns(cur,"CommandsNotes",(
                ("note_name","TEXT"),
                ("category","TEXT"),
                ("sub_category","TEXT"),
                ("command","TEXT"),
                ("tags","TEXT"),
                ("description","TEXT"),
                ("created_at","TEXT"),
                ("updated_at","TEXT"),
            ))
        except Exception:
            pass
        try:
            _ensure_columns(cur,"Commands",(
                ("note_id","INTEGER"),
                ("note_name","TEXT"),
                ("cmd_note_title","TEXT"),
                ("category","TEXT"),
                ("sub_category","TEXT"),
                ("description","TEXT"),
                ("tags","TEXT"),
                ("command","TEXT"),
                ("created_at","TEXT"),
                ("updated_at","TEXT"),
            ))
        except Exception:
            pass
        _record_migration(cur,3,now)
        ver=3
    if ver<4:
        _dedupe_notes_for_unique_name(cur,con)
        try:
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_notes_name ON Notes(note_name)")
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_note_name ON Notes(note_name)")
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated ON Notes(updated_at)")
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_note_name ON CommandsNotes(note_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_category ON CommandsNotes(category)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_sub_category ON CommandsNotes(sub_category)")
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_note_id ON Commands(note_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_note_name ON Commands(note_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_category ON Commands(category)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_sub_category ON Commands(sub_category)")
        except Exception:
            pass
        _record_migration(cur,4,now)
        ver=4
    if ver<5:
        try:
            _ensure_columns(cur,"Notes",(
                ("group_name","TEXT"),
            ))
        except Exception:
            pass
        try:
            _ensure_columns(cur,"NotesHistory",(
                ("group_name","TEXT"),
            ))
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_group_name ON Notes(group_name)")
        except Exception:
            pass
        _record_migration(cur,5,now)
        ver=5
    if ver<6:
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS RecycleBin(id INTEGER PRIMARY KEY AUTOINCREMENT,entity_type TEXT NOT NULL,entity_key TEXT,label TEXT,payload TEXT NOT NULL,source TEXT,deleted_at TEXT NOT NULL,expires_at TEXT NOT NULL)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recycle_type ON RecycleBin(entity_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recycle_deleted_at ON RecycleBin(deleted_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recycle_expires_at ON RecycleBin(expires_at)")
        except Exception:
            pass
        _record_migration(cur,6,now)
        ver=6
    try:
        cur.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
    except Exception:
        pass
    try:
        con.commit()
    except Exception:
        pass
def ensure_schema(con):
    cur=con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS Notes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT,group_name TEXT,content TEXT,created_at TEXT,updated_at TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS CommandsNotes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT,category TEXT,sub_category TEXT,command TEXT,tags TEXT,description TEXT,created_at TEXT,updated_at TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS Commands(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,created_at TEXT,updated_at TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS RecycleBin(id INTEGER PRIMARY KEY AUTOINCREMENT,entity_type TEXT NOT NULL,entity_key TEXT,label TEXT,payload TEXT NOT NULL,source TEXT,deleted_at TEXT NOT NULL,expires_at TEXT NOT NULL)")
    apply_migrations(con)
    try:
        con.commit()
    except Exception:
        pass
