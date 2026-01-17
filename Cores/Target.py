import os,json,logging,hashlib,re,sqlite3,html,base64
from logging.handlers import RotatingFileHandler
from datetime import datetime,timezone
from PyQt6.QtCore import Qt,QSize,QTimer
from PyQt6.QtGui import QColor,QIcon,QIntValidator
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QToolButton,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QComboBox,QTabWidget,QAbstractItemView,QDialog,QApplication,QScrollArea,QGridLayout,QInputDialog,QTextEdit,QPlainTextEdit,QCheckBox
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("Target");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"Target_log.log"))
    for h in list(lg.handlers):
        try:
            if getattr(h,"baseFilename","") and os.path.abspath(h.baseFilename)==fp:return lg
        except:pass
    h=RotatingFileHandler(fp,maxBytes=1024*1024,backupCount=5,encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s","%Y-%m-%d %H:%M:%S"))
    lg.addHandler(h);return lg
_LOG=None
def _log(tag,msg):
    global _LOG
    if _LOG is None:_LOG=_log_setup()
    try:_LOG.info(f"{tag} {msg}")
    except:pass
def _data_dir():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True);return d
def _db_path():
    d=_data_dir()
    return os.path.join(d,"Note_LOYA_V1.db")
def _paths():
    d=_data_dir()
    vp=os.path.join(d,"target_values.json")
    p_new=os.path.join(d,"Targets.json")
    p_old=os.path.join(d,"Targes.json")
    tp=p_new if os.path.isfile(p_new) or not os.path.isfile(p_old) else p_old
    return vp,tp
def _now():return datetime.now(timezone.utc).isoformat()
def _norm(s):return (str(s) if s is not None else "").strip()
def _kci(s):return _norm(s).lower()
def _sid(s):return hashlib.sha256(_norm(s).lower().encode("utf-8")).hexdigest()[:16]
def _clamp_u16(n):
    try:n=int(n)
    except:return 0
    if n<0:n=0
    if n>65535:n=65535
    return n
_SETTINGS_CACHE=None
_SETTINGS_MTIME=None
_KEY_RE_STRICT=re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_KEY_RE_EXT=re.compile(r"^[A-Za-z_][A-Za-z0-9_\-.:]*$")
def _settings_path():
    d=_data_dir()
    return os.path.join(d,"settings.json")
def _read_settings():
    global _SETTINGS_CACHE,_SETTINGS_MTIME
    p=_settings_path()
    try:m=os.path.getmtime(p)
    except:m=None
    if _SETTINGS_CACHE is not None and m==_SETTINGS_MTIME:return _SETTINGS_CACHE
    try:
        if not p or not os.path.isfile(p):
            _SETTINGS_CACHE={}
            _SETTINGS_MTIME=m
            return _SETTINGS_CACHE
        with open(p,"r",encoding="utf-8") as f:
            d=json.load(f)
            if not isinstance(d,dict):d={}
            _SETTINGS_CACHE=d
            _SETTINGS_MTIME=m
            return d
    except Exception:
        _SETTINGS_CACHE={}
        _SETTINGS_MTIME=m
        return _SETTINGS_CACHE
def _write_settings(data):
    global _SETTINGS_CACHE,_SETTINGS_MTIME
    p=_settings_path()
    t=p+".tmp"
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(t,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(t,p)
        _SETTINGS_CACHE=data if isinstance(data,dict) else {}
        try:_SETTINGS_MTIME=os.path.getmtime(p)
        except:_SETTINGS_MTIME=None
        return True
    except Exception as e:
        _log("[!]",f"Write settings failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _allow_dots_colons():
    s=_read_settings()
    t=s.get("targets",{}) if isinstance(s,dict) else {}
    return bool(t.get("allow_dots_colons",False))
def _set_allow_dots_colons(val):
    s=_read_settings()
    if not isinstance(s,dict):s={}
    t=s.get("targets",{}) if isinstance(s.get("targets",{}),dict) else {}
    t["allow_dots_colons"]=bool(val)
    s["targets"]=t
    return _write_settings(s)
def _is_valid_key(k):
    if not k:return False
    rx=_KEY_RE_EXT if _allow_dots_colons() else _KEY_RE_STRICT
    if not rx.match(k):return False
    return any(ch.isalpha() for ch in k)
_TOKEN_RE=re.compile(r"(cmdedit:|cmddelete:)([A-Za-z0-9_-]+)")
def _table_cols(cur,t):
    try:cur.execute(f"PRAGMA table_info({t})");return [r[1] for r in cur.fetchall()]
    except:return []
def _extract_keys_from_text(text):
    out=[]
    if not text:return out
    raw=html.unescape(str(text))
    for m in re.finditer(r"\{([^{}\r\n]+)\}",raw):
        k=_norm(m.group(1))
        if k and _is_valid_key(k):out.append(k)
    return out
def _extract_keys_from_db(dbp):
    keys=[]
    seen=set()
    if not dbp or not os.path.isfile(dbp):return keys
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        for table,col in (("Commands","command"),):
            try:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
                if not cur.fetchone():continue
                cols=set(_table_cols(cur,table))
                if col not in cols:continue
                q="SELECT {col} FROM {table} WHERE {col} LIKE '%{{%' AND {col} LIKE '%}}%'".format(col=col,table=table)
                cur.execute(q)
                for (text,) in cur.fetchall():
                    for k in _extract_keys_from_text(text):
                        lk=_kci(k)
                        if lk in seen:continue
                        seen.add(lk)
                        keys.append(k)
            except Exception:
                continue
        return keys
    except Exception as e:
        _log("[!]",f"Read keys from DB failed ({e})")
        return keys
    finally:
        try:
            if con:con.close()
        except:pass
def _command_links_map(dbp,include_unlinked=False):
    links={}
    if not dbp or not os.path.isfile(dbp):return links
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        tables=("CommandsNotes","Commands") if include_unlinked else ("Commands",)
        for table in tables:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
            if not cur.fetchone():continue
            cols=set(_table_cols(cur,table))
            if "command" not in cols:continue
            q=f"SELECT command FROM {table} WHERE command LIKE '%{{%' AND command LIKE '%}}%'"
            cur.execute(q)
            for (text,) in cur.fetchall():
                if not text:continue
                keys=set(_extract_keys_from_text(text))
                for k in keys:
                    lk=_kci(k)
                    links[lk]=links.get(lk,0)+1
        return links
    except Exception as e:
        _log("[!]",f"Read links from DB failed ({e})")
        return links
    finally:
        try:
            if con:con.close()
        except:pass
def _parse_dt(s):
    try:
        if not s:return None
        v=str(s).replace("Z","+00:00")
        return datetime.fromisoformat(v)
    except Exception:
        return None
def _command_last_seen_map(dbp,include_unlinked=False):
    out={}
    if not dbp or not os.path.isfile(dbp):return out
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        tables=("CommandsNotes","Commands") if include_unlinked else ("Commands",)
        for table in tables:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
            if not cur.fetchone():continue
            cols=set(_table_cols(cur,table))
            if "command" not in cols:continue
            time_col="updated_at" if "updated_at" in cols else ("created_at" if "created_at" in cols else "")
            if not time_col:continue
            q=f"SELECT command,{time_col} FROM {table} WHERE command LIKE '%{{%' AND command LIKE '%}}%'"
            cur.execute(q)
            for cmd,ts in cur.fetchall():
                if not cmd:continue
                dt=_parse_dt(ts)
                if not dt:continue
                keys=set(_extract_keys_from_text(cmd))
                for k in keys:
                    lk=_kci(k)
                    cur_dt=out.get(lk)
                    if cur_dt is None or dt>cur_dt:
                        out[lk]=dt
        return out
    except Exception as e:
        _log("[!]",f"Read last seen from DB failed ({e})")
        return out
    finally:
        try:
            if con:con.close()
        except:pass
def _save_last_seen_map(dbp,last_seen_map):
    if not dbp or not os.path.isfile(dbp):return False
    if not isinstance(last_seen_map,dict):return False
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS TargetKeyStats(key TEXT PRIMARY KEY,last_seen TEXT)")
        for k,dt in last_seen_map.items():
            if not k or not dt:continue
            cur.execute("INSERT INTO TargetKeyStats(key,last_seen) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET last_seen=excluded.last_seen",(str(k),dt.isoformat()))
        con.commit()
        return True
    except Exception as e:
        _log("[!]",f"Save last seen failed ({e})")
        try:
            if con:con.rollback()
        except:pass
        return False
    finally:
        try:
            if con:con.close()
        except:pass
def _delete_key_stats(dbp,key):
    if not dbp or not os.path.isfile(dbp):return False
    k=_norm(key)
    if not k:return False
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS TargetKeyStats(key TEXT PRIMARY KEY,last_seen TEXT)")
        cur.execute("DELETE FROM TargetKeyStats WHERE lower(key)=?",(k.lower(),))
        con.commit()
        return bool(cur.rowcount)
    except Exception as e:
        _log("[!]",f"Delete key stats failed ({e})")
        try:
            if con:con.rollback()
        except:pass
        return False
    finally:
        try:
            if con:con.close()
        except:pass
def _rename_key_stats(dbp,old_key,new_key):
    if not dbp or not os.path.isfile(dbp):return False
    ok=_norm(old_key);nk=_norm(new_key)
    if not ok or not nk:return False
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS TargetKeyStats(key TEXT PRIMARY KEY,last_seen TEXT)")
        cur.execute("SELECT last_seen FROM TargetKeyStats WHERE lower(key)=?",(ok.lower(),))
        r=cur.fetchone()
        if not r:return False
        last_seen=r[0]
        cur.execute("DELETE FROM TargetKeyStats WHERE lower(key)=?",(ok.lower(),))
        cur.execute("INSERT INTO TargetKeyStats(key,last_seen) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET last_seen=excluded.last_seen",(nk,last_seen))
        con.commit()
        return True
    except Exception as e:
        _log("[!]",f"Rename key stats failed ({e})")
        try:
            if con:con.rollback()
        except:pass
        return False
    finally:
        try:
            if con:con.close()
        except:pass
def _commands_for_key(dbp,key,include_unlinked=False):
    out=[]
    if not dbp or not os.path.isfile(dbp):return out
    lk=_kci(key)
    if not lk:return out
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        tables=[("Commands","Linked")]
        if include_unlinked:tables.append(("CommandsNotes","Unlinked"))
        for table,label in tables:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
            if not cur.fetchone():continue
            cols=set(_table_cols(cur,table))
            if "command" not in cols:continue
            field="note_name" if "note_name" in cols else "''"
            q=f"SELECT {field},command FROM {table} WHERE lower(command) LIKE ?"
            cur.execute(q,(f"%{{{lk}}}%",))
            for note,cmd in cur.fetchall():
                if not cmd:continue
                out.append({"note":_norm(note) or "Unlinked","command":_clean_cmd_text(cmd),"src":label})
        return out
    except Exception:
        return out
    finally:
        try:
            if con:con.close()
        except:pass
def _replace_placeholders(text,old_keys,new_key):
    if not text:return text
    out=str(text)
    for old in old_keys:
        if not old:continue
        pat=re.compile(r"\{"+re.escape(old)+r"\}",re.I)
        out=pat.sub("{%s}"%new_key,out)
    return out
def _clean_cmd_text(text):
    if text is None:return ""
    raw=html.unescape(str(text))
    low=raw.lower()
    if "<span" in low or "<pre" in low or "<p" in low or "<div" in low or "<br" in low or "style=" in low or "-qt-" in low:
        raw=re.sub(r"<[^>]+>"," ",raw)
    raw=raw.replace("\xa0"," ")
    raw=re.sub(r"[ \t\r\f\v]+"," ",raw)
    raw=re.sub(r"\n\s+","\n",raw)
    raw=re.sub(r"\s+\n","\n",raw)
    return raw.strip()
def _decode_cmd_token(token):
    t=_norm(token)
    if not t:return {}
    pad="="*((4-len(t)%4)%4)
    try:
        raw=base64.urlsafe_b64decode(t+pad).decode("utf-8")
        d=json.loads(raw)
        return d if isinstance(d,dict) else {}
    except Exception:
        return {}
def _encode_cmd_token(data):
    if not isinstance(data,dict):return ""
    raw=json.dumps(data,ensure_ascii=False)
    b=base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
    return b.rstrip("=")
def _update_note_tokens(html_text,old_keys,new_key):
    if not html_text:return html_text
    def repl(m):
        prefix=m.group(1);token=m.group(2)
        d=_decode_cmd_token(token)
        if not d:return m.group(0)
        cmd=d.get("command","")
        new_cmd=_replace_placeholders(cmd,old_keys,new_key)
        if new_cmd==cmd:return m.group(0)
        d["command"]=new_cmd
        nt=_encode_cmd_token(d)
        if not nt:return m.group(0)
        return prefix+nt
    return _TOKEN_RE.sub(repl,html_text)
def _rename_placeholders_db(dbp,old_keys,new_key):
    res={"commands":0,"commands_notes":0,"notes":0}
    if not dbp or not os.path.isfile(dbp):return res
    if not isinstance(old_keys,(list,tuple,set)):old_keys=[old_keys]
    old_keys=[_norm(k) for k in old_keys if _norm(k)]
    if not old_keys:return res
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        for table,label in (("Commands","commands"),("CommandsNotes","commands_notes")):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
            if not cur.fetchone():continue
            cols=set(_table_cols(cur,table))
            if "command" not in cols:continue
            q=f"SELECT id,command FROM {table} WHERE command LIKE '%{{%' AND command LIKE '%}}%'"
            cur.execute(q)
            for rid,cmd in cur.fetchall():
                new_cmd=_replace_placeholders(cmd,old_keys,new_key)
                if new_cmd!=cmd:
                    cur.execute(f"UPDATE {table} SET command=? WHERE id=?",(new_cmd,int(rid)))
                    res[label]+=1
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Notes'")
        if cur.fetchone():
            cols=set(_table_cols(cur,"Notes"))
            if "content" in cols:
                q="SELECT id,content FROM Notes WHERE content LIKE '%{{%' AND content LIKE '%}}%'"
                cur.execute(q)
                for rid,htmls in cur.fetchall():
                    new_html=_replace_placeholders(htmls,old_keys,new_key)
                    new_html=_update_note_tokens(new_html,old_keys,new_key)
                    if new_html!=htmls:
                        cur.execute("UPDATE Notes SET content=? WHERE id=?",(new_html,int(rid)))
                        res["notes"]+=1
        con.commit()
        return res
    except Exception as e:
        _log("[!]",f"Rename placeholders failed ({e})")
        try:
            if con:con.rollback()
        except:pass
        return res
    finally:
        try:
            if con:con.close()
        except:pass
def _priority_from(v):
    if isinstance(v,dict):
        return v.get("priority",v.get("value",0))
    return v
def _manual_from(v):
    if isinstance(v,dict):
        return bool(v.get("manual",False))
    return False
def _serialize_values(values):
    out={}
    if not isinstance(values,dict):return out
    for k,v in values.items():
        nk=_norm(k)
        if not nk:continue
        entry={"priority":_clamp_u16(_priority_from(v))}
        if _manual_from(v):entry["manual"]=True
        out[nk]=entry
    return out
def _read_json(p,default):
    try:
        if not os.path.isfile(p):return default
        with open(p,"r",encoding="utf-8") as f:
            v=json.load(f)
            return v if v is not None else default
    except Exception as e:
        _log("[!]",f"Read JSON failed: {p} ({e})")
        return default
def _write_json(p,obj):
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        t=p+".tmp"
        with open(t,"w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(t,p)
        return True
    except Exception as e:
        _log("[!]",f"Write JSON failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _pretty(obj):return json.dumps(obj,ensure_ascii=False,indent=2)
def _asset_icon(*names):
    for n in names:
        p=_abs("..","Assets",n)
        if os.path.isfile(p):return QIcon(p)
    return QIcon()
class Store:
    def __init__(self):
        self.values_path,self.targets_path=_paths()
        self.values=self._load_values()
        self.targets=self._load_targets()
        self._auto_add_values_from_db()
        self._prune_targets_to_current_keys(save=True)
    def ordered_keys(self):
        items=[(k,_clamp_u16(_priority_from(v))) for k,v in self.values.items()]
        items.sort(key=lambda x:(x[1],x[0].lower()))
        return [k for k,_ in items]
    def _load_values(self):
        exists=os.path.isfile(self.values_path)
        d=_read_json(self.values_path,{})
        out={}
        seen=set()
        dupe=False
        invalid=False
        def addk(k,val,manual=False):
            nonlocal dupe
            nonlocal invalid
            nk=_norm(k)
            if not nk:return
            if not _is_valid_key(nk):
                invalid=True
                return
            lk=_kci(nk)
            if lk in seen:
                dupe=True
                return
            seen.add(lk)
            out[nk]={"priority":_clamp_u16(val),"manual":bool(manual)}
        if isinstance(d,list):
            for it in d:
                if isinstance(it,str):addk(it,0)
                elif isinstance(it,dict):
                    k=it.get("key") if "key" in it else it.get("name")
                    addk(k,it.get("priority",it.get("value",0)),it.get("manual",False))
        elif isinstance(d,dict):
            for k,v in d.items():
                if isinstance(v,dict):addk(k,v.get("priority",v.get("value",0)),v.get("manual",False))
                elif isinstance(v,int):addk(k,v,False)
                else:addk(k,0,False)
        if not out:out={}
        changed=dupe or invalid or (not exists)
        for k,v in out.items():
            if not isinstance(v,dict) or "priority" not in v:
                out[k]={"priority":_clamp_u16(_priority_from(v)),"manual":False};changed=True
            else:
                vv=_clamp_u16(v.get("priority",0))
                if vv!=v.get("priority"):out[k]["priority"]=vv;changed=True
                mm=bool(v.get("manual",False))
                if v.get("manual",False)!=mm:out[k]["manual"]=mm;changed=True
        if changed or not (isinstance(d,dict) and all(isinstance(v,dict) and "priority" in v for v in d.values())):_write_json(self.values_path,_serialize_values(out))
        _log("[+]",f"Values loaded: {len(out)}")
        return out
    def _load_targets(self):
        d=_read_json(self.targets_path,[])
        if not isinstance(d,list):d=[]
        out=[]
        for t in d:
            if not isinstance(t,dict):continue
            name=_norm(t.get("name",""))
            if not name:continue
            st=_kci(t.get("status","not_used"))
            st="live" if st=="live" else "not_used"
            vals=t.get("values",{})
            if not isinstance(vals,dict):vals={}
            out.append({"id":t.get("id") or _sid(name),"name":name,"status":st,"values":{str(k):("" if v is None else str(v)) for k,v in vals.items()},"created":t.get("created") or _now(),"updated":t.get("updated") or _now()})
        _log("[+]",f"Targets loaded: {len(out)}")
        return out
    def _auto_add_values_from_db(self):
        keys=_extract_keys_from_db(_db_path())
        if not keys:return 0
        existing={_kci(k) for k in self.values.keys()}
        added=0
        for k in keys:
            lk=_kci(k)
            if lk in existing:continue
            self.values[k]={"priority":0,"manual":False}
            existing.add(lk)
            added+=1
        if added:
            if self.save_values():_log("[+]",f"Auto-added target values: {added}")
        return added
    def save_values(self):return _write_json(self.values_path,_serialize_values(self.values))
    def save_targets(self):
        for t in self.targets:
            v=t.get("values",{})
            if not isinstance(v,dict):v={}
            t["values"]={k:_norm(vv) for k,vv in v.items() if _norm(k) and _norm(vv)}
        return _write_json(_abs("..","Data","Targets.json"),self.targets)
    def _sync_targets_keys(self,save=False):
        keys=self.ordered_keys()
        kset_ci={_kci(k) for k in keys}
        changed=False
        for t in self.targets:
            v=t.get("values",{})
            if not isinstance(v,dict):v={}
            nv={}
            for k in keys:nv[k]="" if v.get(k) is None else str(v.get(k,""))
            for k0,val0 in v.items():
                if _kci(k0) in kset_ci and k0 not in nv:
                    for kk in keys:
                        if _kci(kk)==_kci(k0):nv[kk]="" if val0 is None else str(val0);break
            if nv!=v:
                t["values"]=nv
                t["updated"]=_now()
                changed=True
        if save and changed:self.save_targets()
    def add_key(self,k,val,manual=True):
        nk=_norm(k)
        if not nk:return False,"Key is empty"
        lk=_kci(nk)
        if lk in {_kci(x) for x in self.values.keys()}:return False,"Key already exists (case-insensitive)"
        self.values[nk]={"priority":_clamp_u16(val),"manual":bool(manual)}
        if not self.save_values():return False,"Save failed"
        return True,"Added"
    def sync_manual_flags(self,links_map=None,save=True):
        links=links_map if isinstance(links_map,dict) else _command_links_map(_db_path(),include_unlinked=True)
        changed=False
        for k,v in self.values.items():
            if isinstance(v,dict) and v.get("manual") and links.get(_kci(k),0)>0:
                v["manual"]=False
                changed=True
        if changed and save:self.save_values()
        return changed
    def bulk_rename(self,old_keys,new_key):
        nk=_norm(new_key)
        if not nk:return False,"New key is empty"
        if not _is_valid_key(nk):return False,"Invalid key"
        if not isinstance(old_keys,(list,tuple,set)):return False,"No keys to merge"
        cleaned=[]
        seen=set()
        for k in old_keys:
            kk=_norm(k)
            if kk.startswith("{"):kk=kk[1:]
            if kk.endswith("}"):kk=kk[:-1]
            kk=_norm(kk)
            if not kk:continue
            lk=_kci(kk)
            if lk==_kci(nk):continue
            if lk in seen:continue
            seen.add(lk);cleaned.append(kk)
        if not cleaned:return False,"No keys to merge"
        res=_rename_placeholders_db(_db_path(),cleaned,nk)
        old_set={_kci(k) for k in cleaned}
        old_actuals=[k for k in list(self.values.keys()) if _kci(k) in old_set]
        new_actual=None
        for k in self.values.keys():
            if _kci(k)==_kci(nk):new_actual=k;break
        if new_actual:
            new_pr=_clamp_u16(_priority_from(self.values.get(new_actual)))
        elif old_actuals:
            new_pr=min(_clamp_u16(_priority_from(self.values.get(k))) for k in old_actuals)
        else:
            new_pr=0
        for k in old_actuals:self.values.pop(k,None)
        if new_actual and new_actual!=nk:self.values.pop(new_actual,None)
        self.values[nk]={"priority":new_pr,"manual":False}
        for k in cleaned:_delete_key_stats(_db_path(),k)
        if new_actual and new_actual!=nk:_rename_key_stats(_db_path(),new_actual,nk)
        if not self.save_values():return False,"Save failed"
        self._prune_targets_to_current_keys(save=True)
        msg=f"Updated commands:{res.get('commands',0)} notes:{res.get('notes',0)}"
        if res.get("commands_notes",0):msg+=f" unlinked:{res.get('commands_notes',0)}"
        return True,msg
    def rename_key(self,old_key,new_key):
        ok_key=_norm(old_key)
        nk=_norm(new_key)
        if not ok_key:return False,"Key is empty"
        if not nk:return False,"New key is empty"
        if not _is_valid_key(nk):return False,"Invalid key"
        old_actual=None
        for k in self.values.keys():
            if _kci(k)==_kci(ok_key):old_actual=k;break
        if not old_actual:return False,"Key not found"
        new_actual=None
        for k in self.values.keys():
            if _kci(k)==_kci(nk):new_actual=k;break
        res=_rename_placeholders_db(_db_path(),old_actual,nk)
        _rename_key_stats(_db_path(),old_actual,nk)
        if new_actual and _kci(new_actual)==_kci(old_actual):
            if old_actual!=nk:
                val=self.values.pop(old_actual)
                self.values[nk]=val
        elif new_actual:
            self.values.pop(old_actual,None)
        else:
            val=self.values.pop(old_actual)
            self.values[nk]=val
        if not self.save_values():return False,"Save failed"
        self._prune_targets_to_current_keys(save=True)
        msg=f"Updated commands:{res.get('commands',0)} notes:{res.get('notes',0)}"
        if res.get("commands_notes",0):
            msg+=f" unlinked:{res.get('commands_notes',0)}"
        return True,msg
    def remove_key(self,k):
        lk=_kci(k)
        found=None
        for kk in list(self.values.keys()):
            if _kci(kk)==lk:found=kk;break
        if not found:return False,"Key not found"
        links=_command_links_map(_db_path(),include_unlinked=True).get(lk,0)
        if links>0:return False,f"Key is used in {links} command(s). Remove it from commands first."
        self.values.pop(found,None)
        _delete_key_stats(_db_path(),found)
        if not self.save_values():return False,"Save failed"
        self._prune_targets_to_current_keys(save=True)
        return True,"Removed"
    def apply_values_json(self,raw):
        out={}
        def addk(k,val,manual=False):
            nk=_norm(k)
            if not nk:return
            lk=_kci(nk)
            for ex in list(out.keys()):
                if _kci(ex)==lk:return
            out[nk]={"priority":_clamp_u16(val),"manual":bool(manual)}
        if isinstance(raw,dict):
            for k,v in raw.items():
                if isinstance(v,dict):addk(k,v.get("priority",v.get("value",0)),v.get("manual",False))
                elif isinstance(v,int):addk(k,v,False)
                else:addk(k,0,False)
        elif isinstance(raw,list):
            for it in raw:
                if isinstance(it,dict):addk(it.get("key") if "key" in it else it.get("name"),it.get("priority",it.get("value",0)),it.get("manual",False))
                elif isinstance(it,str):addk(it,0,False)
        else:return False,"JSON must be an object or a list"
        if not out:return False,"At least one key is required"
        self.values=out
        if not self.save_values():return False,"Save failed"
        self._prune_targets_to_current_keys(save=True)
        return True,"Applied"
    def upsert_target(self,tid,name,status,vals):
        name=_norm(name)
        if not name:return False,"Target name is required"
        keys=self.ordered_keys()
        nv={}
        if isinstance(vals,dict):
            for k in keys:
                vv=_norm(vals.get(k,""))
                if vv:nv[k]=vv
            for k0,val0 in vals.items():
                for kk in keys:
                    if _kci(kk)==_kci(k0) and kk not in nv:
                        vv=_norm(val0)
                        if vv:nv[kk]=vv
                        break
        now=_now()
        if tid:
            for t in self.targets:
                if t["id"]==tid:
                    t["name"]=name
                    t["values"]=nv
                    t["updated"]=now
                    return (True,"Updated") if self.save_targets() else (False,"Save failed")
        if _kci(name) in {_kci(t["name"]) for t in self.targets}:return False,"Target name already exists (case-insensitive)"
        self.targets.append({"id":_sid(name+now),"name":name,"status":"not_used","values":nv,"created":now,"updated":now})
        return (True,"Created") if self.save_targets() else (False,"Save failed")
    def delete_target(self,tid):
        before=len(self.targets)
        self.targets=[t for t in self.targets if t["id"]!=tid]
        if len(self.targets)==before:return False,"Not found"
        return (True,"Deleted") if self.save_targets() else (False,"Save failed")
    def set_live_target(self,tid):
        tid=_norm(tid)
        if not tid:return False,"Missing id"
        found=None
        for t in self.targets:
            if t.get("id")==tid:found=t;break
        if not found:return False,"Not found"
        was_live=_kci(found.get("status","not_used"))=="live"
        changed=False
        now=_now()
        if was_live:
            for t in self.targets:
                cur=_kci(t.get("status","not_used"))
                if cur!="not_used":
                    t["status"]="not_used"
                    t["updated"]=now
                    changed=True
            if not changed:return True,"No change"
            return (True,"Cleared") if self.save_targets() else (False,"Save failed")
        for t in self.targets:
            cur=_kci(t.get("status","not_used"))
            want="live" if t.get("id")==tid else "not_used"
            if cur!=want:
                t["status"]=want
                t["updated"]=now
                changed=True
        if not changed:return True,"No change"
        return (True,"Using") if self.save_targets() else (False,"Save failed")
    def _prune_targets_to_current_keys(self,save=False):
        keys_ci={_kci(k) for k in self.ordered_keys()}
        changed=False
        for t in self.targets:
            v=t.get("values",{})
            if not isinstance(v,dict):v={}
            nv={}
            for k,val in v.items():
                kk=_norm(k)
                vv=_norm(val)
                if not kk or not vv:continue
                if _kci(kk) in keys_ci:nv[kk]=vv
            if nv!=v:
                t["values"]=nv
                t["updated"]=_now()
                changed=True
        if save and changed:self.save_targets()
    def set_target_status(self,tid,status):
        st="live" if _kci(status)=="live" else "not_used"
        now=_now()
        for t in self.targets:
            if t.get("id")==tid:
                t["status"]=st
                t["updated"]=now
                return (True,"Updated") if self.save_targets() else (False,"Save failed")
        return False,"Not found"
class _Toast(QFrame):
    def __init__(self,parent,msg=""):
        super().__init__(None)
        self._parent=parent
        self.setObjectName("Toast")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
        v=QVBoxLayout(self);v.setContentsMargins(14,12,14,12);v.setSpacing(0)
        self.lbl=QLabel(msg,self);self.lbl.setObjectName("ToastMsg");self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl,1)
        self._t=QTimer(self);self._t.setSingleShot(True);self._t.timeout.connect(self.close)
    def show_msg(self,msg,ms=3000):
        self.lbl.setText(msg)
        self.adjustSize()
        self._center()
        self.show()
        self.raise_()
        self._t.start(ms)
    def _center(self):
        try:
            p=self._parent.window() if self._parent and self._parent.window() else self._parent
            if not p:return
            g=p.frameGeometry()
            x=g.x()+(g.width()-self.width())//2
            y=g.y()+(g.height()-self.height())//2
            self.move(max(0,x),max(0,y))
        except:pass
class TargetEditorDialog(QDialog):
    def __init__(self,owner,store,target=None):
        super().__init__(owner)
        self.store=store
        self.target=target if isinstance(target,dict) else None
        self._editing_id=(self.target.get("id") if self.target else None)
        self.setObjectName("TargetDialog")
        self.setWindowTitle("Edit Target" if self.target else "Add Target")
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        self.resize(900,640)
        lay=QVBoxLayout(self);lay.setContentsMargins(14,14,14,14);lay.setSpacing(12)
        box=QFrame(self);box.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(box);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        head=QHBoxLayout();head.setSpacing(10)
        self.title=QLabel("Edit Target" if self.target else "Add Target",box);self.title.setObjectName("TargetFormTitle")
        head.addWidget(self.title,1)
        v.addLayout(head)
        r1=QHBoxLayout();r1.setSpacing(10)
        self.in_name=QLineEdit(box);self.in_name.setObjectName("TargetName");self.in_name.setPlaceholderText("Target name")
        r1.addWidget(QLabel("Name:",box),0);r1.addWidget(self.in_name,1)
        v.addLayout(r1)
        r2=QHBoxLayout();r2.setSpacing(10)
        self.find=QLineEdit(box);self.find.setObjectName("TargetFieldSearch");self.find.setPlaceholderText("Search field (e.g., IP, URL, MAC) ...")
        self.find.textChanged.connect(self._on_find_preview)
        self.find.returnPressed.connect(self._focus_first_match)
        r2.addWidget(QLabel("Find:",box),0);r2.addWidget(self.find,1)
        v.addLayout(r2)
        self.scroll=QScrollArea(box);self.scroll.setObjectName("TargetFieldsScroll");self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.wrap=QFrame(self.scroll);self.wrap.setObjectName("TargetFieldsWrap")
        self.grid=QGridLayout(self.wrap);self.grid.setContentsMargins(0,0,0,0);self.grid.setHorizontalSpacing(12);self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(1,1);self.grid.setColumnStretch(3,1)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.wrap)
        v.addWidget(self.scroll,1)
        fb=QHBoxLayout();fb.setSpacing(10)
        self.btn_save=QToolButton(box);self.btn_save.setObjectName("TargetSaveBtn");self.btn_save.setText("Save");self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel=QToolButton(box);self.btn_cancel.setObjectName("TargetCancelBtn");self.btn_cancel.setText("Cancel");self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(self.reject)
        fb.addStretch(1);fb.addWidget(self.btn_save,0);fb.addWidget(self.btn_cancel,0)
        v.addLayout(fb)
        lay.addWidget(box,1)
        self._fields={}
        self._labels={}
        self._rows={}
        self._order=[]
        self._rebuild_fields(self.target.get("values",{}) if self.target else {})
        if self.target:self.in_name.setText(_norm(self.target.get("name","")))
        self.in_name.setFocus()
    def _clear_grid(self):
        while self.grid.count():
            it=self.grid.takeAt(0)
            w=it.widget()
            if w:w.deleteLater()
    def _rebuild_fields(self,preserve):
        preserve=preserve if isinstance(preserve,dict) else {}
        self._fields={};self._labels={};self._rows={};self._order=[]
        self._clear_grid()
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        keys=self.store.ordered_keys()
        r=0;c=0
        for k in keys:
            le=QLineEdit(self.wrap);le.setObjectName("TargetField");le.setPlaceholderText(f"{k} value")
            le.setText("" if preserve.get(k) is None else str(preserve.get(k,"")))
            lab=QLabel(k+":",self.wrap)
            base=c*2
            self.grid.addWidget(lab,r,base,1,1)
            self.grid.addWidget(le,r,base+1,1,1)
            self._fields[k]=le
            self._labels[k]=lab
            self._rows[k]=r
            self._order.append(k)
            c+=1
            if c==2:c=0;r+=1
        used_rows=(len(keys)+1)//2
        self.grid.setRowStretch(used_rows,1)
    def _match_key(self,txt):
        q=_kci(txt)
        if not q:return None
        for k in self._order:
            if _kci(k)==q:return k
        for k in self._order:
            if q in _kci(k):return k
        return None
    def _scroll_to_key(self,k):
        try:
            r=self._rows.get(k,0)
            y=max(0,(r*44)-10)
            self.scroll.verticalScrollBar().setValue(y)
        except:pass
    def _focus_key(self,k):
        w=self._fields.get(k)
        if not w:return False
        self._scroll_to_key(k)
        w.setFocus()
        w.selectAll()
        return True
    def _on_find_preview(self,t):
        q=_kci(t)
        toks=[x for x in re.split(r"[,\s]+",q) if x]
        if not toks:
            for k in self._order:
                self._labels[k].setVisible(True)
                self._fields[k].setVisible(True)
            return
        first=None
        for k in self._order:
            kk=_kci(k)
            ok=any(x in kk for x in toks)
            self._labels[k].setVisible(ok)
            self._fields[k].setVisible(ok)
            if ok and first is None:first=k
        if first:self._scroll_to_key(first)
    def _focus_first_match(self):
        k=self._match_key(self.find.text())
        if k:self._focus_key(k)
    def _on_find(self,t):
        q=_norm(t)
        if not q:
            try:self.in_name.setFocus()
            except:pass
            return
        k=self._match_key(q)
        if k:self._focus_key(k)
    def _save(self):
        name=_norm(self.in_name.text())
        vals={k:w.text() for k,w in self._fields.items()}
        ok,msg=self.store.upsert_target(self._editing_id,name,None,vals)
        if not ok:
            QMessageBox.warning(self,"Save Target",msg)
            return
        self.accept()
class Widget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.store=Store()
        self._toast=_Toast(self)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("TargetFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        self.tabs=QTabWidget(self.frame);self.tabs.setObjectName("TargetTabs")
        v.addWidget(self.tabs,1)
        self.tab_targets=QWidget();self.tab_targets.setObjectName("Page")
        self.tab_elements=QWidget();self.tab_elements.setObjectName("Page")
        self.tabs.addTab(self.tab_targets,"Targets")
        self.tabs.addTab(self.tab_elements,"Set Elements")
        self._build_targets_tab()
        self._build_elements_tab()
        QTimer.singleShot(0,self._render_targets)
        QTimer.singleShot(0,self._render_keys)
        _log("[+]",f"Target ready")
    def _build_targets_tab(self):
        lay=QVBoxLayout(self.tab_targets);lay.setContentsMargins(0,0,0,0);lay.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.btn_add=QToolButton(self.tab_targets);self.btn_add.setObjectName("TargetAddBtn");self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.btn_add.setText("\u2003\u2003Add");self.btn_add.setIconSize(QSize(18,18))
        fa=self.btn_add.font();fa.setBold(True);fa.setWeight(800);self.btn_add.setFont(fa)
        self.btn_add.setIcon(_asset_icon("add.png","Add.png"))
        self.btn_add.clicked.connect(self._open_add)
        self.search=QLineEdit(self.tab_targets);self.search.setObjectName("TargetSearch");self.search.setPlaceholderText("Search targets...")
        self.search.textChanged.connect(lambda _:self._render_targets())
        top.addWidget(self.btn_add,0);top.addWidget(self.search,1)
        self.tbl_wrap=QFrame(self.tab_targets);self.tbl_wrap.setObjectName("TargetTableFrame")
        tw=QVBoxLayout(self.tbl_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.table=QTableWidget(self.tbl_wrap);self.table.setObjectName("TargetTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Target","Status","#","X"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.cellClicked.connect(self._on_target_cell)
        self.table.cellDoubleClicked.connect(self._on_target_double)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        fh=h.font();fh.setBold(True);fh.setWeight(800);h.setFont(fh)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2,44);self.table.setColumnWidth(3,44)
        tw.addWidget(self.table,1)
        lay.addLayout(top)
        lay.addWidget(self.tbl_wrap,1)
    def _build_elements_tab(self):
        lay=QVBoxLayout(self.tab_elements);lay.setContentsMargins(0,0,0,0);lay.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.key_in=QLineEdit(self.tab_elements);self.key_in.setObjectName("TargetKeyInput");self.key_in.setPlaceholderText("Key (e.g., IP, URL)")
        self.key_val=QLineEdit(self.tab_elements);self.key_val.setObjectName("TargetKeyInput");self.key_val.setPlaceholderText("Priority (0-65535)")
        self.key_val.setValidator(QIntValidator(0,65535,self.key_val))
        self.key_in.returnPressed.connect(self._add_key)
        self.key_val.returnPressed.connect(self._add_key)
        self.btn_key_add=QToolButton(self.tab_elements);self.btn_key_add.setObjectName("TargetMiniBtn");self.btn_key_add.setText("Add");self.btn_key_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_key_add.clicked.connect(self._add_key)
        self.btn_key_bulk=QToolButton(self.tab_elements);self.btn_key_bulk.setObjectName("TargetMiniBtn");self.btn_key_bulk.setText("Bulk Rename");self.btn_key_bulk.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_key_bulk.clicked.connect(self._open_bulk_rename)
        top.addWidget(self.key_in,2);top.addWidget(self.key_val,1);top.addWidget(self.btn_key_add,0);top.addWidget(self.btn_key_bulk,0)
        lay.addLayout(top)
        left=QFrame(self.tab_elements);left.setObjectName("TargetKeysFrame")
        lv=QVBoxLayout(left);lv.setContentsMargins(10,10,10,10);lv.setSpacing(10)
        self.key_filter=QLineEdit(left);self.key_filter.setObjectName("TargetKeyFilter");self.key_filter.setPlaceholderText("Filter keys...")
        self.key_filter.textChanged.connect(self._render_keys)
        self.key_pattern_toggle=QCheckBox("Allow dots/colons in keys",left)
        self.key_pattern_toggle.setObjectName("TargetKeyPatternToggle")
        self.key_pattern_toggle.setChecked(_allow_dots_colons())
        self.key_pattern_toggle.toggled.connect(self._toggle_key_pattern)
        self.key_filter_manual=QCheckBox("Manual Only",left)
        self.key_filter_manual.setObjectName("TargetKeyManualFilter")
        self.key_filter_manual.toggled.connect(self._render_keys)
        self.key_filter_unused=QCheckBox("Unused (links=0)",left)
        self.key_filter_unused.setObjectName("TargetKeyUnusedFilter")
        self.key_filter_unused.toggled.connect(self._render_keys)
        self.keys_table=QTableWidget(left);self.keys_table.setObjectName("TargetKeysTable")
        self.keys_table.setColumnCount(5)
        self.keys_table.setHorizontalHeaderLabels(["Key","Priority","Links","Show","X"])
        self.keys_table.verticalHeader().setVisible(False)
        self.keys_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked|QTableWidget.EditTrigger.SelectedClicked|QTableWidget.EditTrigger.EditKeyPressed)
        self.keys_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.keys_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.keys_table.setSortingEnabled(False)
        self.keys_table.setAlternatingRowColors(False)
        self.keys_table.setShowGrid(True)
        self.keys_table.cellClicked.connect(self._on_key_cell)
        self.keys_table.cellChanged.connect(self._on_key_cell_changed)
        self.keys_table.setWordWrap(False)
        try:self.keys_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        except Exception:pass
        kh=self.keys_table.horizontalHeader()
        kh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        kf=kh.font();kf.setBold(True);kf.setWeight(800);kh.setFont(kf)
        kh.setStretchLastSection(False)
        kh.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        kh.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        kh.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        kh.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        kh.setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.keys_table.setColumnWidth(3,70);self.keys_table.setColumnWidth(4,44)
        lv.addWidget(self.key_filter,0)
        filt_row=QHBoxLayout();filt_row.setSpacing(10)
        filt_row.addWidget(self.key_pattern_toggle,0)
        sep=QLabel("|",left)
        sep.setObjectName("TargetKeyFilterSep")
        filt_row.addWidget(sep,0)
        show_lbl=QLabel("Show:",left)
        show_lbl.setObjectName("TargetKeyFilterShow")
        filt_row.addWidget(show_lbl,0)
        filt_row.addWidget(self.key_filter_manual,0)
        filt_row.addWidget(self.key_filter_unused,0)
        filt_row.addStretch(1)
        lv.addLayout(filt_row)
        lv.addWidget(self.keys_table,1)
        lay.addWidget(left,1)
    def _show_toast(self,msg,ms=3000):
        try:self._toast.show_msg(msg,ms)
        except:pass
    def _toggle_key_pattern(self,checked):
        _set_allow_dots_colons(bool(checked))
        self.store=Store()
        self._reload_elements()
    def _highlight_cmd(self,cmd,key):
        if not cmd:return ""
        esc=html.escape(str(cmd))
        if not key:return esc
        pat=re.compile(r"\{"+re.escape(key)+r"\}",re.I)
        return pat.sub(lambda m:f"<span style=\"color:#4dabf7;font-weight:700;\">{m.group(0)}</span>",esc)
    def _show_commands_for_key(self,key):
        k=_norm(key)
        if not k:return
        cmds=_commands_for_key(_db_path(),k,include_unlinked=True)
        dlg=QDialog(self);dlg.setObjectName("TargetDialog")
        dlg.setWindowTitle(f"Commands for {k}")
        g=QApplication.primaryScreen().availableGeometry()
        dlg.resize(min(860,int(g.width()*0.9)),min(560,int(g.height()*0.9)))
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):dlg.setWindowIcon(QIcon(ico))
        lay=QVBoxLayout(dlg);lay.setContentsMargins(14,14,14,14);lay.setSpacing(12)
        frame=QFrame(dlg);frame.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(frame);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        t=QLabel(f"Commands referencing {{{k}}} ({len(cmds)})",frame);t.setObjectName("TargetFormTitle")
        v.addWidget(t,0)
        box=QTextEdit(frame);box.setObjectName("CardDetailCmd");box.setReadOnly(True);box.setAcceptRichText(False)
        if not cmds:
            box.setPlainText("No commands found.")
        else:
            rows=[]
            for c in cmds:
                note=_norm(c.get("note","")) or "Unlinked"
                cmd=_norm(c.get("command",""))
                rows.append(f"{note} : {cmd}")
            box.setPlainText("\n".join(rows))
        v.addWidget(box,1)
        bh=QHBoxLayout();bh.setContentsMargins(0,0,0,0);bh.setSpacing(10)
        ok=QToolButton(frame);ok.setObjectName("TargetSaveBtn");ok.setCursor(Qt.CursorShape.PointingHandCursor);ok.setText("OK");ok.setMinimumHeight(30)
        ok.clicked.connect(dlg.accept)
        bh.addStretch(1);bh.addWidget(ok,0);bh.addStretch(1)
        v.addLayout(bh,0)
        lay.addWidget(frame,1)
        dlg.exec()
    def _parse_bulk_keys(self,text):
        raw=str(text or "")
        parts=re.split(r"[,\s]+",raw)
        keys=[]
        invalid=[]
        seen=set()
        for part in parts:
            k=_norm(part)
            if not k:continue
            if k.startswith("{"):k=k[1:]
            if k.endswith("}"):k=k[:-1]
            k=_norm(k)
            if not k:continue
            if not _is_valid_key(k):
                invalid.append(k)
                continue
            lk=_kci(k)
            if lk in seen:continue
            seen.add(lk);keys.append(k)
        return keys,invalid
    def _open_bulk_rename(self):
        dlg=QDialog(self);dlg.setObjectName("TargetDialog")
        dlg.setWindowTitle("Bulk Rename / Merge")
        g=QApplication.primaryScreen().availableGeometry()
        dlg.resize(min(720,int(g.width()*0.8)),min(520,int(g.height()*0.8)))
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):dlg.setWindowIcon(QIcon(ico))
        lay=QVBoxLayout(dlg);lay.setContentsMargins(14,14,14,14);lay.setSpacing(12)
        frame=QFrame(dlg);frame.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(frame);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        title=QLabel("Merge multiple keys into one",frame);title.setObjectName("TargetFormTitle")
        v.addWidget(title,0)
        self.bulk_new_key=QLineEdit(frame);self.bulk_new_key.setObjectName("TargetKeyInput");self.bulk_new_key.setPlaceholderText("New key (e.g., TARGET_IP)")
        self.bulk_old_keys=QPlainTextEdit(frame);self.bulk_old_keys.setObjectName("TargetBulkKeys");self.bulk_old_keys.setPlaceholderText("Old keys (one per line or comma-separated)")
        v.addWidget(QLabel("New key:",frame),0)
        v.addWidget(self.bulk_new_key,0)
        v.addWidget(QLabel("Old keys:",frame),0)
        v.addWidget(self.bulk_old_keys,1)
        bh=QHBoxLayout();bh.setContentsMargins(0,0,0,0);bh.setSpacing(10)
        apply_btn=QToolButton(frame);apply_btn.setObjectName("TargetSaveBtn");apply_btn.setCursor(Qt.CursorShape.PointingHandCursor);apply_btn.setText("Apply")
        cancel_btn=QToolButton(frame);cancel_btn.setObjectName("TargetCancelBtn");cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor);cancel_btn.setText("Cancel")
        bh.addStretch(1);bh.addWidget(apply_btn,0);bh.addWidget(cancel_btn,0)
        v.addLayout(bh,0)
        lay.addWidget(frame,1)
        def do_apply():
            nk=_norm(self.bulk_new_key.text())
            if nk.startswith("{") and nk.endswith("}"):nk=_norm(nk[1:-1])
            if not nk:
                QMessageBox.warning(self,"Bulk Rename","New key is empty.")
                return
            if not _is_valid_key(nk):
                QMessageBox.warning(self,"Bulk Rename","Invalid new key format.")
                return
            keys,invalid=self._parse_bulk_keys(self.bulk_old_keys.toPlainText())
            keys=[k for k in keys if _kci(k)!=_kci(nk)]
            if invalid:
                QMessageBox.warning(self,"Bulk Rename","Invalid keys: "+", ".join(invalid))
                return
            if not keys:
                QMessageBox.warning(self,"Bulk Rename","Add at least one old key to merge.")
                return
            msg=f"Merge {len(keys)} key(s) into {nk}? This updates commands and notes."
            if QMessageBox.question(self,"Bulk Rename",msg,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
                return
            ok,info=self.store.bulk_rename(keys,nk)
            if not ok:
                QMessageBox.warning(self,"Bulk Rename",info)
                return
            dlg.accept()
            self._reload_elements()
            self._show_toast(f"Bulk rename: {info}",3000)
        apply_btn.clicked.connect(do_apply)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()
    def _rename_key_prompt(self,old_key):
        okd=_norm(old_key)
        if not okd:return
        w=self.window() if self.window() else self
        new_raw,ok=QInputDialog.getText(w,"Rename Key",f"Rename {okd} to:",QLineEdit.EchoMode.Normal,okd)
        if not ok:return
        nk=_norm(new_raw)
        if nk.startswith("{") and nk.endswith("}"):nk=_norm(nk[1:-1])
        if not nk:
            QMessageBox.warning(w,"Rename Key","New key is empty.")
            return
        if not _is_valid_key(nk):
            QMessageBox.warning(w,"Rename Key","Invalid key format.")
            return
        merge=False
        for k in self.store.values.keys():
            if _kci(k)==_kci(nk) and _kci(k)!=_kci(okd):
                merge=True
                break
        msg=f"Rename {okd} to {nk}?"
        if merge:msg+=" This will merge keys."
        if QMessageBox.question(w,"Rename Key",msg,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        ok2,info=self.store.rename_key(okd,nk)
        if not ok2:
            QMessageBox.warning(w,"Rename Key",info)
            return
        self._reload_elements()
        self._show_toast(f"Renamed: {info}",3000)
    def _on_key_cell_changed(self,row,col):
        if getattr(self,"_table_updating",False):return
        if col==1:
            it=self.keys_table.item(row,1)
            kitem=self.keys_table.item(row,0)
            if not it or not kitem:return
            k=_norm(kitem.text())
            raw=_norm(it.text())
            if raw=="" or not raw.isdigit():
                prev=it.data(Qt.ItemDataRole.UserRole)
                self._table_updating=True
                it.setText(str(prev if prev is not None else 0))
                self._table_updating=False
                return
            val=_clamp_u16(raw)
            if k in self.store.values:
                cur=self.store.values.get(k,{})
                manual=bool(cur.get("manual",False)) if isinstance(cur,dict) else False
                self.store.values[k]={"priority":val,"manual":manual}
            else:
                for kk in self.store.values.keys():
                    if _kci(kk)==_kci(k):
                        cur=self.store.values.get(kk,{})
                        manual=bool(cur.get("manual",False)) if isinstance(cur,dict) else False
                        self.store.values[kk]={"priority":val,"manual":manual}
                        k=kk
                        break
            if not self.store.save_values():
                self._table_updating=True
                it.setText(str(it.data(Qt.ItemDataRole.UserRole)))
                self._table_updating=False
                return
            it.setData(Qt.ItemDataRole.UserRole,val)
            return
        if col!=0:return
        if not hasattr(self,"_renaming"):self._renaming=False
        if self._renaming:return
        it=self.keys_table.item(row,0)
        if not it:return
        old_key=_norm(it.data(Qt.ItemDataRole.UserRole))
        new_key=_norm(it.text())
        if not old_key or not new_key or old_key==new_key:return
        w=self.window() if self.window() else self
        if new_key.startswith("{") and new_key.endswith("}"):new_key=_norm(new_key[1:-1])
        if not new_key:
            QMessageBox.warning(w,"Rename Key","New key is empty.")
            self._renaming=True
            it.setText(old_key)
            self._renaming=False
            return
        if not _is_valid_key(new_key):
            QMessageBox.warning(w,"Rename Key","Invalid key format.")
            self._renaming=True
            it.setText(old_key)
            self._renaming=False
            return
        merge=False
        for k in self.store.values.keys():
            if _kci(k)==_kci(new_key) and _kci(k)!=_kci(old_key):
                merge=True
                break
        msg=f"Update {old_key} to {new_key}?"
        if merge:msg+=" This will merge keys."
        if QMessageBox.question(w,"Rename Key",msg,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            self._renaming=True
            it.setText(old_key)
            self._renaming=False
            return
        ok,info=self.store.rename_key(old_key,new_key)
        if not ok:
            QMessageBox.warning(w,"Rename Key",info)
            self._renaming=True
            it.setText(old_key)
            self._renaming=False
            return
        self._reload_elements()
        self._show_toast(f"Renamed: {info}",3000)
    def reload(self):
        self.store=Store()
        self._reload_elements()
    def refresh(self):
        self.reload()
    def _reload_elements(self):
        self._render_keys()
        self._render_targets()
    def _render_keys(self):
        self._table_updating=True
        self._links_map=_command_links_map(_db_path(),include_unlinked=True)
        self.store.sync_manual_flags(self._links_map,save=True)
        items=[(k,_clamp_u16(_priority_from(v))) for k,v in self.store.values.items()]
        items.sort(key=lambda x:(x[1],x[0].lower()))
        flt=_kci(self.key_filter.text()) if hasattr(self,"key_filter") else ""
        if flt:items=[it for it in items if flt in _kci(it[0])]
        manual_only=bool(self.key_filter_manual.isChecked()) if hasattr(self,"key_filter_manual") else False
        unused_only=bool(self.key_filter_unused.isChecked()) if hasattr(self,"key_filter_unused") else False
        if manual_only:
            items=[it for it in items if bool((self.store.values.get(it[0],{}) or {}).get("manual",False))]
        elif unused_only:
            items=[it for it in items if self._links_map.get(_kci(it[0]),0)==0 and not bool((self.store.values.get(it[0],{}) or {}).get("manual",False))]
        self.keys_table.setRowCount(len(items))
        self._last_seen_map=_command_last_seen_map(_db_path(),include_unlinked=True)
        _save_last_seen_map(_db_path(),self._last_seen_map)
        for r,(k,val) in enumerate(items):
            it=QTableWidgetItem(k);it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsEditable);it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            it.setToolTip(k)
            it.setData(Qt.ItemDataRole.UserRole,k)
            v=QTableWidgetItem(str(val));v.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsEditable);v.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setData(Qt.ItemDataRole.UserRole,val)
            ln=QTableWidgetItem(str(self._links_map.get(_kci(k),0)));ln.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);ln.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            sh=QTableWidgetItem("Show");sh.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);sh.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            x=QTableWidgetItem("X");x.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);x.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            f=x.font();f.setBold(True);f.setWeight(800);x.setFont(f);sh.setFont(f)
            self.keys_table.setItem(r,0,it);self.keys_table.setItem(r,1,v);self.keys_table.setItem(r,2,ln);self.keys_table.setItem(r,3,sh);self.keys_table.setItem(r,4,x)
            self.keys_table.setRowHeight(r,44)
        self.keys_table.clearSelection()
        self._table_updating=False
        _log("[*]",f"Keys rendered: {len(items)}")
    def _on_key_cell(self,row,col):
        if col==3:
            it=self.keys_table.item(row,0)
            if not it:return
            self._show_commands_for_key(_norm(it.text()))
            return
        if col!=4:return
        it=self.keys_table.item(row,0)
        if not it:return
        k=_norm(it.text())
        links=_command_links_map(_db_path(),include_unlinked=True).get(_kci(k),0)
        if links>0:
            QMessageBox.information(self,"Remove Key",f"Key '{k}' is used in {links} command(s).\nRemove it from commands first.")
            return
        mods=QApplication.keyboardModifiers()
        if not (mods & Qt.KeyboardModifier.ShiftModifier):
            w=self.window() if self.window() else self
            if QMessageBox.question(w,"Remove Key",f"Remove key: {k}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        ok,msg=self.store.remove_key(k)
        if not ok:
            QMessageBox.warning(self,"Remove Key",msg)
            return
        self._reload_elements()
    def _add_key(self):
        k=_norm(self.key_in.text())
        vv=_norm(self.key_val.text())
        val=_clamp_u16(vv if vv!="" else 0)
        ok,msg=self.store.add_key(k,val)
        if not ok:
            QMessageBox.warning(self,"Add Key",msg)
            return
        self.key_in.clear();self.key_val.clear()
        self._reload_elements()
    def _status_text(self,st):
        st=_kci(st)
        return ("● Live",QColor(50,220,140)) if st=="live" else ("Not Used",QColor(220,220,220))
    def _render_targets(self):
        q=_kci(self.search.text())
        rows=[]
        for t in self.store.targets:
            blob=(t.get("name","")+" "+json.dumps(t.get("values",{}),ensure_ascii=False)).lower()
            if q and q not in blob:continue
            rows.append(t)
        rows.sort(key=lambda x:x.get("name","").lower())
        self.table.setRowCount(len(rows))
        for r,t in enumerate(rows):
            name=QTableWidgetItem(_norm(t.get("name","")));name.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);name.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            fn=name.font();fn.setBold(True);fn.setWeight(800);name.setFont(fn)
            name.setData(Qt.ItemDataRole.UserRole,t)
            st_txt,st_col=self._status_text(t.get("status","not_used"))
            st=QTableWidgetItem(st_txt);st.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);st.setTextAlignment(Qt.AlignmentFlag.AlignCenter);st.setForeground(st_col)
            ed=QTableWidgetItem("#");ed.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);ed.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            xd=QTableWidgetItem("X");xd.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);xd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fe=ed.font();fe.setBold(True);fe.setWeight(800);ed.setFont(fe);xd.setFont(fe)
            self.table.setItem(r,0,name);self.table.setItem(r,1,st);self.table.setItem(r,2,ed);self.table.setItem(r,3,xd)
            self.table.setRowHeight(r,44)
        self.table.clearSelection()
        _log("[*]",f"Targets rendered: {len(rows)}")
    def _row_target(self,row):
        it=self.table.item(row,0)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _open_add(self):
        dlg=TargetEditorDialog(self,self.store,None)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.store=dlg.store
            self._render_targets()
            _log("[+]",f"Target added")
    def _edit_target(self,t):
        dlg=TargetEditorDialog(self,self.store,t)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.store=dlg.store
            self._render_targets()
            _log("[+]",f"Target updated")
    def _delete_target(self,t,skip_confirm=False):
        name=_norm(t.get("name",""))
        if not skip_confirm:
            w=self.window() if self.window() else self
            if QMessageBox.question(w,"Delete",f"Delete target: {name}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        ok,msg=self.store.delete_target(t.get("id"))
        if not ok:
            QMessageBox.critical(self,"Delete",msg)
            return
        _log("[+]",f"Deleted target: {name}")
        self._render_targets()
    def _on_target_cell(self,row,col):
        t=self._row_target(row)
        if not t:return
        if col in (0,1):
            was_live=_kci(t.get("status","not_used"))=="live"
            ok,msg=self.store.set_live_target(t.get("id"))
            if not ok:QMessageBox.warning(self,"Use Target",msg);return
            self._render_targets()
            if was_live:self._show_toast("No target in use now",3000)
            else:self._show_toast(f"Using target: {t.get('name','')}",3000)
            return
        if col==2:return self._edit_target(t)
        if col==3:
            mods=QApplication.keyboardModifiers()
            return self._delete_target(t,skip_confirm=bool(mods & Qt.KeyboardModifier.ShiftModifier))
    def _on_target_double(self,row,col):
        t=self._row_target(row)
        if not t:return
        self._edit_target(t)
