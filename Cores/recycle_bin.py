import hashlib,json,os,sqlite3
from datetime import datetime,timedelta,timezone
from Cores import common_db
RETENTION_DAYS=30
TYPE_NOTE="note"
TYPE_COMMAND="command"
TYPE_TARGET="target"
TYPE_LABELS={TYPE_NOTE:"Note",TYPE_COMMAND:"Command",TYPE_TARGET:"Target"}
def _norm(v):return str(v or "").strip()
def _utc_now():return datetime.now(timezone.utc)
def _iso(dt):return dt.astimezone(timezone.utc).isoformat()
def now_text():return _iso(_utc_now())
def expires_text(days=RETENTION_DAYS):return _iso(_utc_now()+timedelta(days=max(1,int(days or RETENTION_DAYS))))
def _read_json(path,default):
    try:
        if not path or not os.path.isfile(path):return default
        with open(path,"r",encoding="utf-8") as fh:
            data=json.load(fh)
            return data if data is not None else default
    except Exception:
        return default
def _write_json(path,obj):
    tmp=path+".tmp"
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(tmp,"w",encoding="utf-8") as fh:json.dump(obj,fh,ensure_ascii=False,indent=2)
    os.replace(tmp,path)
def _targets_path():return os.path.join(common_db.data_dir(),"Targets.json")
def _target_id_seed(name):return hashlib.sha256(_norm(name).lower().encode("utf-8")).hexdigest()[:16]
def _payload_text(payload):return json.dumps(payload or {},ensure_ascii=False)
def _payload_obj(text):
    try:
        data=json.loads(text or "{}")
        return data if isinstance(data,dict) else {}
    except Exception:
        return {}
def put_entry_cur(cur,entity_type,label,payload,source="",entity_key="",deleted_at="",expires_at=""):
    deleted=_norm(deleted_at) or now_text()
    expires=_norm(expires_at) or expires_text()
    cur.execute("INSERT INTO RecycleBin(entity_type,entity_key,label,payload,source,deleted_at,expires_at) VALUES(?,?,?,?,?,?,?)",(_norm(entity_type),_norm(entity_key),_norm(label),_payload_text(payload),_norm(source),deleted,expires))
    try:return int(cur.lastrowid or 0)
    except Exception:return 0
def put_entry(entity_type,label,payload,source="",entity_key="",dbp=None,deleted_at="",expires_at=""):
    try:
        with sqlite3.connect(dbp or common_db.db_path(),timeout=5) as con:
            common_db.ensure_schema(con)
            rid=put_entry_cur(con.cursor(),entity_type,label,payload,source=source,entity_key=entity_key,deleted_at=deleted_at,expires_at=expires_at)
            con.commit()
            return True,rid
    except Exception as e:
        return False,str(e)
def purge_expired(dbp=None,now_value=""):
    try:
        with sqlite3.connect(dbp or common_db.db_path(),timeout=5) as con:
            common_db.ensure_schema(con)
            cur=con.cursor()
            cur.execute("DELETE FROM RecycleBin WHERE expires_at<>'' AND expires_at<=?",(_norm(now_value) or now_text(),))
            con.commit()
            return int(cur.rowcount or 0)
    except Exception:
        return 0
def list_entries(dbp=None,entity_type=""):
    purge_expired(dbp)
    rows=[]
    try:
        with sqlite3.connect(dbp or common_db.db_path(),timeout=5) as con:
            common_db.ensure_schema(con)
            cur=con.cursor()
            et=_norm(entity_type)
            if et:cur.execute("SELECT id,entity_type,entity_key,label,source,payload,deleted_at,expires_at FROM RecycleBin WHERE entity_type=? ORDER BY deleted_at DESC,id DESC",(et,))
            else:cur.execute("SELECT id,entity_type,entity_key,label,source,payload,deleted_at,expires_at FROM RecycleBin ORDER BY deleted_at DESC,id DESC")
            for r in cur.fetchall():
                rows.append({"id":int(r[0]),"entity_type":_norm(r[1]),"entity_key":_norm(r[2]),"label":_norm(r[3]),"source":_norm(r[4]),"payload":_payload_obj(r[5]),"deleted_at":_norm(r[6]),"expires_at":_norm(r[7])})
    except Exception:
        return []
    return rows
def delete_entry(entry_id,dbp=None):
    try:
        with sqlite3.connect(dbp or common_db.db_path(),timeout=5) as con:
            common_db.ensure_schema(con)
            cur=con.cursor()
            cur.execute("DELETE FROM RecycleBin WHERE id=?",(int(entry_id),))
            con.commit()
            return (True,"Deleted permanently") if cur.rowcount else (False,"Not found")
    except Exception as e:
        return False,str(e)
def _restore_note(cur,payload):
    note=payload.get("note",{}) if isinstance(payload,dict) else {}
    commands=payload.get("commands",[]) if isinstance(payload.get("commands",[]),list) else []
    note_name=_norm(note.get("note_name",""))
    if not note_name:raise ValueError("Recycle Bin note payload is invalid.")
    cur.execute("SELECT 1 FROM Notes WHERE note_name=?",(note_name,))
    if cur.fetchone():raise ValueError("A note with the same name already exists.")
    group_name=_norm(note.get("group_name",""))
    content=note.get("content","") or ""
    created_at=_norm(note.get("created_at","")) or now_text()
    updated_at=_norm(note.get("updated_at","")) or created_at
    cur.execute("INSERT INTO Notes(note_name,group_name,content,created_at,updated_at) VALUES(?,?,?,?,?)",(note_name,group_name,content,created_at,updated_at))
    note_id=int(cur.lastrowid or 0)
    stamp=now_text()
    try:cur.execute("INSERT INTO NotesHistory(note_id,note_name,group_name,content,action,action_at) VALUES(?,?,?,?,?,?)",(note_id,note_name,group_name,content,"restore",stamp))
    except Exception:pass
    for row in commands:
        if not isinstance(row,dict):continue
        ttl=_norm(row.get("cmd_note_title","")) or note_name
        cat=_norm(row.get("category",""))
        sub=_norm(row.get("sub_category",""))
        desc=_norm(row.get("description",""))
        tags=_norm(row.get("tags",""))
        command=row.get("command","") or ""
        c_created=_norm(row.get("created_at","")) or stamp
        c_updated=_norm(row.get("updated_at","")) or c_created
        cur.execute("INSERT INTO Commands(note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(note_id,note_name,ttl,cat,sub,desc,tags,command,c_created,c_updated))
        cmd_id=int(cur.lastrowid or 0)
        try:cur.execute("INSERT INTO CommandsHistory(cmd_id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,action,action_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(cmd_id,note_id,note_name,ttl,cat,sub,desc,tags,command,"restore",stamp))
        except Exception:pass
def _restore_command(cur,payload):
    row=payload.get("command",{}) if isinstance(payload,dict) else {}
    note_name=_norm(row.get("note_name",""))
    category=_norm(row.get("category",""))
    sub=_norm(row.get("sub_category",""))
    command=row.get("command","") or ""
    tags=_norm(row.get("tags",""))
    desc=_norm(row.get("description",""))
    created_at=_norm(row.get("created_at","")) or now_text()
    updated_at=_norm(row.get("updated_at","")) or created_at
    cur.execute("INSERT INTO CommandsNotes(note_name,category,sub_category,command,tags,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(note_name,category,sub,command,tags,desc,created_at,updated_at))
    cmd_id=int(cur.lastrowid or 0)
    stamp=now_text()
    try:cur.execute("INSERT INTO CommandsNotesHistory(cmd_id,note_name,category,sub_category,command,tags,description,action,action_at) VALUES(?,?,?,?,?,?,?,?,?)",(cmd_id,note_name,category,sub,command,tags,desc,"restore",stamp))
    except Exception:pass
def _restore_target(payload):
    row=payload.get("target",{}) if isinstance(payload,dict) else {}
    name=_norm(row.get("name",""))
    if not name:raise ValueError("Recycle Bin target payload is invalid.")
    targets=_read_json(_targets_path(),[])
    if not isinstance(targets,list):targets=[]
    if any(_norm(t.get("name","")).lower()==name.lower() for t in targets if isinstance(t,dict)):raise ValueError("A target with the same name already exists.")
    tid=_norm(row.get("id","")) or _target_id_seed(name+now_text())
    if any(_norm(t.get("id",""))==tid for t in targets if isinstance(t,dict)):tid=_target_id_seed(name+now_text())
    status=_norm(row.get("status","not_used")).lower()
    if status=="live" and any(_norm(t.get("status","not_used")).lower()=="live" for t in targets if isinstance(t,dict)):status="not_used"
    if status!="live":status="not_used"
    vals=row.get("values",{})
    values={_norm(k):_norm(v) for k,v in (vals.items() if isinstance(vals,dict) else []) if _norm(k) and _norm(v)}
    created_at=_norm(row.get("created","")) or now_text()
    updated_at=_norm(row.get("updated","")) or created_at
    targets.append({"id":tid,"name":name,"status":status,"values":values,"created":created_at,"updated":updated_at})
    _write_json(_targets_path(),targets)
def restore_entry(entry_id,dbp=None):
    purge_expired(dbp)
    db_path=dbp or common_db.db_path()
    with sqlite3.connect(db_path,timeout=5) as con:
        common_db.ensure_schema(con)
        cur=con.cursor()
        cur.execute("SELECT id,entity_type,payload FROM RecycleBin WHERE id=?",(int(entry_id),))
        row=cur.fetchone()
        if not row:return False,"Not found"
        entity_type=_norm(row[1]);payload=_payload_obj(row[2])
        try:
            if entity_type==TYPE_NOTE:_restore_note(cur,payload)
            elif entity_type==TYPE_COMMAND:_restore_command(cur,payload)
            elif entity_type==TYPE_TARGET:_restore_target(payload)
            else:return False,"Unsupported Recycle Bin item."
            cur.execute("DELETE FROM RecycleBin WHERE id=?",(int(entry_id),))
            con.commit()
            return True,"Restored"
        except Exception as e:
            con.rollback()
            return False,str(e)
