import os,sqlite3,json,csv,zipfile,shutil,tempfile,logging,re,time,base64,hashlib,hmac,html,sys,subprocess,importlib.util
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtGui import QAction,QFontMetrics,QTextDocument
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QToolButton,QStackedWidget,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QComboBox,QDialog,QFileDialog,QMessageBox,QMenu,QProgressBar,QCheckBox,QApplication,QLineEdit,QInputDialog,QScrollArea
try:
    from cryptography.fernet import Fernet,InvalidToken
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    _HAS_CRYPTO=True
except Exception:
    Fernet=None;InvalidToken=None;PBKDF2HMAC=None;hashes=None
    _HAS_CRYPTO=False
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _norm(s):return (str(s) if s is not None else "").replace("\x00","").strip()
def _l(s):return _norm(s).lower()
def _now():return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("Settings");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"Settings_log.log"))
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
def _data_dir():d=_abs("..","Data");os.makedirs(d,exist_ok=True);return d
def _backups_dir():d=_abs("..","Backups");os.makedirs(d,exist_ok=True);return d
def _db_path():return os.path.join(_data_dir(),"Note_LOYA_V1.db")
DB_SCHEMA_VERSION=2
def _targets_values_path():return os.path.join(_data_dir(),"target_values.json")
def _targets_path():return os.path.join(_data_dir(),"Targets.json")
def _read_json(p,default):
    try:
        if not p or not os.path.isfile(p):return default
        with open(p,"r",encoding="utf-8") as f:
            v=json.load(f)
            return v if v is not None else default
    except:return default
def _write_json(p,obj):
    t=p+".tmp"
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(t,"w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(t,p);return True
    except Exception as e:
        _log("[!]",f"Write JSON failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _settings_path():return os.path.join(_data_dir(),"settings.json")
def _read_settings():return _read_json(_settings_path(),{})
def _write_settings(data):return _write_json(_settings_path(),data or {})
def _project_root():return os.path.abspath(_abs(".."))
def _expand_project_path(p):
    p=_norm(p)
    if not p:return ""
    if os.path.isabs(p):return p
    return os.path.abspath(os.path.join(_project_root(),p))
def _rel_project_path(p):
    p=_norm(p)
    if not p:return ""
    try:ap=os.path.abspath(p)
    except Exception:return p
    root=_project_root()
    if ap==root:return "."
    if ap.startswith(root+os.sep):
        try:return os.path.relpath(ap,root)
        except Exception:return p
    return p
def _normalize_weight_input(weight,ckpt_path):
    w=_norm(weight)
    if not w:return ""
    if os.path.isabs(w):
        ckpt=_expand_project_path(ckpt_path)
        if ckpt and os.path.isdir(ckpt):
            try:
                ap=os.path.abspath(w);croot=os.path.abspath(ckpt)
                if ap.startswith(croot+os.sep):
                    try:return os.path.relpath(ap,croot)
                    except Exception:return os.path.basename(ap)
            except Exception:pass
        return w
    return w
def _get_backup_settings():
    d=_read_settings()
    b=d.get("backup",{}) if isinstance(d,dict) else {}
    try:interval=int(b.get("interval_hours",24))
    except:interval=24
    try:keep=int(b.get("keep",20))
    except:keep=20
    return {"auto_enabled":bool(b.get("auto_enabled",False)),"interval_hours":max(1,interval),"keep":max(1,keep)}
def _save_backup_settings(cfg):
    d=_read_settings()
    if not isinstance(d,dict):d={}
    cur=d.get("backup",{}) if isinstance(d.get("backup",{}),dict) else {}
    cur.update({"auto_enabled":bool(cfg.get("auto_enabled",False)),"interval_hours":int(cfg.get("interval_hours",24)),"keep":int(cfg.get("keep",20))})
    d["backup"]=cur
    return _write_settings(d)
def _get_ai_eveluotion_settings():
    d=_read_settings()
    a=d.get("ai_eveluotion",{}) if isinstance(d,dict) else {}
    return {"enabled":bool(a.get("enabled",False)),"self_update_enabled":bool(a.get("self_update_enabled",False))}
def _save_ai_eveluotion_settings(cfg):
    d=_read_settings()
    if not isinstance(d,dict):d={}
    cur=d.get("ai_eveluotion",{}) if isinstance(d.get("ai_eveluotion",{}),dict) else {}
    cur.update({"enabled":bool(cfg.get("enabled",False)),"self_update_enabled":bool(cfg.get("self_update_enabled",False))})
    d["ai_eveluotion"]=cur
    return _write_settings(d)
def _get_chat_output_settings():
    d=_read_settings()
    c=d.get("chat_output",{}) if isinstance(d,dict) else {}
    return {"structured_output":bool(c.get("structured_output",False))}
def _save_chat_output_settings(cfg):
    d=_read_settings()
    if not isinstance(d,dict):d={}
    cur=d.get("chat_output",{}) if isinstance(d.get("chat_output",{}),dict) else {}
    cur.update({"structured_output":bool(cfg.get("structured_output",False))})
    d["chat_output"]=cur
    return _write_settings(d)
def _to_int(v,default):
    try:return int(str(v).strip())
    except Exception:return default
def _to_float(v,default):
    try:return float(str(v).strip())
    except Exception:return default
def _deepseek_platform_issue():
    if os.name=="nt":
        try:
            if importlib.util.find_spec("triton") is not None:return ""
        except Exception:
            pass
        return "Triton not available on Windows; using fallback (slower)."
    return ""
def _deepseek_req_specs():
    specs=["torch>=2.6.0","triton>=3.0.0","transformers>=4.46.3","safetensors>=0.4.5"]
    if os.name=="nt":specs=[s for s in specs if not s.startswith("triton")]
    return specs
def _deepseek_missing():
    missing=[]
    checks=[("torch","torch>=2.6.0"),("triton","triton>=3.0.0"),("transformers","transformers>=4.46.3"),("safetensors","safetensors>=0.4.5")]
    for mod,spec in checks:
        if os.name=="nt" and mod=="triton":continue
        try:
            ok=importlib.util.find_spec(mod) is not None
        except Exception:
            ok=False
        if not ok:missing.append(spec)
    return missing
def _deepseek_gpu_ok():
    try:
        cmd=[sys.executable,"-c","import torch;print('1' if torch.cuda.is_available() else '0')"]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if p.returncode!=0:return False
        out=(p.stdout or "").strip().splitlines()
        return bool(out and out[-1].strip()=="1")
    except Exception:
        return False
def _probe_nvidia_gpu():
    if os.name=="nt":
        try:
            p=subprocess.run(["nvidia-smi","-L"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            if p.returncode==0 and (p.stdout or "").strip():return True
        except FileNotFoundError:
            pass
        except Exception:
            pass
        try:
            p=subprocess.run(["wmic","path","win32_VideoController","get","name"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            if p.returncode==0:
                txt=(p.stdout or "").upper()
                if "NVIDIA" in txt:return True
                if "AMD" in txt or "RADEON" in txt or "INTEL" in txt:return False
        except Exception:
            pass
        return None
    try:
        p=subprocess.run(["nvidia-smi","-L"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if p.returncode==0 and (p.stdout or "").strip():return True
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return None
def _deepseek_gpu_state():
    torch_ok=_deepseek_gpu_ok()
    if torch_ok:return True,True
    gpu=_probe_nvidia_gpu()
    return gpu,False
def _deepseek_default_config_path():
    base=_abs("ChatAI","DeepSeek","configs")
    cand=os.path.join(base,"config_v3.1.json")
    if os.path.isfile(cand):
        return cand
    try:
        files=[f for f in os.listdir(base) if f.lower().endswith(".json")]
    except Exception:
        files=[]
    files.sort()
    return os.path.join(base,files[0]) if files else ""
def _deepseek_default_ckpt_path():
    return _abs("..")
def _deepseek_default_weights(ckpt_path):
    ckpt_path=_expand_project_path(ckpt_path)
    if not ckpt_path or not os.path.isdir(ckpt_path):
        return ""
    cand=os.path.join(ckpt_path,"model0-mp1.safetensors")
    if os.path.isfile(cand):
        return os.path.basename(cand)
    try:
        files=[f for f in os.listdir(ckpt_path) if f.lower().endswith(".safetensors")]
    except Exception:
        files=[]
    if not files:
        return ""
    files.sort()
    best=files[0]
    try:
        best=max(files,key=lambda f: os.path.getsize(os.path.join(ckpt_path,f)))
    except Exception:
        pass
    return best
def _deepseek_code_available():
    return os.path.isdir(_abs("ChatAI","DeepSeek"))
def _run_cmd(cmd,cwd=None):
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,cwd=cwd)
    out=[]
    try:
        for line in p.stdout:
            if line:out.append(line.rstrip("\n"))
    except Exception:
        pass
    rc=p.wait()
    return rc,"\n".join(out[-40:])
def _run_hidden(cmd):
    try:
        if os.name=="nt":
            return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=0x08000000)
        return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    except Exception:
        return None
def _wsl_list_distros():
    p=_run_hidden(["wsl.exe","-l","-q"])
    if not p or p.returncode!=0:return []
    return [_norm(x) for x in (p.stdout or "").splitlines() if _norm(x)]
def _ensure_wsl_installed():
    if os.name!="nt":return True,""
    distros=_wsl_list_distros()
    if distros:return True,""
    p=_run_hidden(["wsl.exe","--install","-d","Ubuntu"])
    if not p:return False,"Failed to run WSL install."
    distros=_wsl_list_distros()
    if distros:return True,""
    msg=p.stdout or "WSL install started. Reboot may be required."
    return False,_norm(msg) or "WSL install started. Reboot may be required."
def _cuda_index_urls():
    return ["https://download.pytorch.org/whl/cu121","https://download.pytorch.org/whl/cu124"]
def _install_cuda_torch():
    last=""
    for url in _cuda_index_urls():
        cmd=[sys.executable,"-m","pip","install","--upgrade","--index-url",url,"torch>=2.6.0"]
        rc,tail=_run_cmd(cmd)
        if rc==0:return True,tail
        last=tail or last
    return False,last
_SESSION_PIN=None
_PIN_ITERS=200000
def _clean_pin(pin):return ("" if pin is None else str(pin)).strip()
def _get_security_settings():
    d=_read_settings()
    s=d.get("security",{}) if isinstance(d,dict) else {}
    return {
        "app_lock_enabled":bool(s.get("app_lock_enabled",False)),
        "pin_salt":s.get("pin_salt",""),
        "pin_hash":s.get("pin_hash",""),
        "enc_enabled":bool(s.get("enc_enabled",False)),
        "enc_salt":s.get("enc_salt",""),
    }
def _save_security_settings(cfg):
    d=_read_settings()
    if not isinstance(d,dict):d={}
    cur=d.get("security",{}) if isinstance(d.get("security",{}),dict) else {}
    cur.update(cfg or {})
    d["security"]=cur
    return _write_settings(d)
def _pin_is_set(cfg=None):
    c=cfg or _get_security_settings()
    return bool(c.get("pin_salt")) and bool(c.get("pin_hash"))
def _hash_pin(pin):
    salt=os.urandom(16)
    dk=hashlib.pbkdf2_hmac("sha256",pin.encode("utf-8"),salt,_PIN_ITERS)
    return base64.b64encode(salt).decode("ascii"),base64.b64encode(dk).decode("ascii")
def _verify_pin(pin,cfg):
    try:
        salt=base64.b64decode(cfg.get("pin_salt","") or "")
        expect=base64.b64decode(cfg.get("pin_hash","") or "")
        if not salt or not expect:return False
        dk=hashlib.pbkdf2_hmac("sha256",pin.encode("utf-8"),salt,_PIN_ITERS)
        return hmac.compare_digest(dk,expect)
    except:return False
def _set_session_pin(pin):
    global _SESSION_PIN
    _SESSION_PIN=pin
def _enc_path():return _db_path()+".enc"
def _derive_key(pin,salt_b64):
    if not _HAS_CRYPTO:raise RuntimeError("cryptography not available")
    salt=base64.b64decode(salt_b64)
    kdf=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=_PIN_ITERS)
    return base64.urlsafe_b64encode(kdf.derive(pin.encode("utf-8")))
def _encrypt_db_file(pin,salt_b64):
    dbp=_db_path();encp=_enc_path()
    if not os.path.isfile(dbp):return False,"Database not found."
    try:
        key=_derive_key(pin,salt_b64)
        data=open(dbp,"rb").read()
        enc=Fernet(key).encrypt(data)
        tmp=encp+".tmp"
        with open(tmp,"wb") as f:f.write(enc)
        os.replace(tmp,encp)
        return True,"Encrypted."
    except Exception as e:
        return False,f"Encrypt failed: {e}"
def _decrypt_db_file(pin,salt_b64):
    dbp=_db_path();encp=_enc_path()
    if not os.path.isfile(encp):return False,"Encrypted file missing."
    try:
        key=_derive_key(pin,salt_b64)
        data=open(encp,"rb").read()
        plain=Fernet(key).decrypt(data)
        tmp=dbp+".tmp"
        with open(tmp,"wb") as f:f.write(plain)
        os.replace(tmp,dbp)
        return True,"Decrypted."
    except InvalidToken:
        return False,"Wrong PIN."
    except Exception as e:
        return False,f"Decrypt failed: {e}"
def _split_tags(s):
    if not s:return []
    raw=str(s).replace(";",",").split(",")
    out=[];seen=set()
    for p in raw:
        t=_norm(p)
        if not t:continue
        k=t.lower()
        if k in seen:continue
        seen.add(k);out.append(t)
    return out
def _dedupe_tags(tags):
    out=[];seen=set()
    for t in tags or []:
        tt=_norm(t)
        if not tt:continue
        k=tt.lower()
        if k in seen:continue
        seen.add(k);out.append(tt)
    return out
def _join_tags(tags):return ",".join(_dedupe_tags(tags))
def _safe_filename(name,fallback="note"):
    n=_norm(name) or fallback
    n=re.sub(r"[\\\\/:*?\"<>|]+","_",n).strip(" .")
    if not n:n=fallback
    return n[:120]
def _html_to_plain(html_text):
    doc=QTextDocument()
    doc.setHtml(html_text or "")
    return doc.toPlainText()
def _read_text_any(path):
    try:data=Path(path).read_bytes()
    except Exception:return ""
    if not data:return ""
    if data.startswith(b"\xef\xbb\xbf"):
        try:return data.decode("utf-8-sig",errors="ignore")
        except Exception:pass
    if data[:2] in (b"\xff\xfe",b"\xfe\xff"):
        try:return data.decode("utf-16",errors="ignore")
        except Exception:pass
    if b"\x00" in data[:4096]:
        try:return data.decode("utf-16",errors="ignore")
        except Exception:pass
    try:return data.decode("utf-8",errors="ignore")
    except Exception:return data.decode("latin-1",errors="ignore")
def _html_escape(s):return html.escape(s or "",quote=True)
def _markdown_to_html(md_text):
    doc=QTextDocument()
    txt=md_text or ""
    try:
        if hasattr(doc,"setMarkdown"):
            doc.setMarkdown(txt)
            return doc.toHtml()
    except:pass
    doc.setPlainText(txt)
    return doc.toHtml()
def _html_to_markdown(html_text):
    doc=QTextDocument()
    try:doc.setHtml(html_text or "")
    except:doc.setPlainText(_norm(html_text))
    if hasattr(doc,"toMarkdown"):
        try:return doc.toMarkdown()
        except:pass
    return doc.toPlainText()
def _extract_html_body(html_text):
    if not html_text:return ""
    m=re.search(r"<body[^>]*>(.*)</body>",html_text,re.I|re.S)
    return m.group(1).strip() if m else html_text
def _extract_md_title(md_text):
    lines=(md_text or "").splitlines()
    for i,line in enumerate(lines):
        if not _norm(line):continue
        m=re.match(r"^\s*#(?!#)\s+(.*)$",line)
        if not m:break
        return _norm(m.group(1)),"\n".join(lines[i+1:])
    return "",md_text or ""
def _code_fence(text):
    return "````" if "```" in (text or "") else "```"
def _wrap_c_blocks(md_text):
    if not md_text:return ""
    rx=re.compile(r"<C\s*\[.*?\]\s*>\s*.*?\s*</C>",re.S|re.I)
    def _rep(m):
        block=m.group(0)
        fence=_code_fence(block)
        return "\n\n"+fence+"\n"+block.rstrip()+"\n"+fence+"\n\n"
    return rx.sub(_rep,md_text)
def _parse_cmd_meta(meta):
    d={"cmd_note_title":"","category":"","sub_category":"","description":"","tags":""}
    for p in [x.strip() for x in (meta or "").split(",") if x.strip()]:
        if ":" not in p:continue
        k,v=p.split(":",1)
        k=_norm(k).lower();v=_norm(v)
        if "command note tittle" in k or "note title" in k:d["cmd_note_title"]=v
        elif k=="category":d["category"]=v
        elif "sub category" in k or "subcategory" in k:d["sub_category"]=v
        elif k=="description":d["description"]=v
        elif k=="tags":d["tags"]=v
    return d
def _parse_cmd_blocks(text):
    t=text or ""
    out=[]
    for m in re.finditer(r"<C\s*\[(.*?)\]\s*>\s*(.*?)\s*</C>",t,re.S|re.I):
        meta=(m.group(1) or "").strip()
        body=(m.group(2) or "").rstrip()
        d={"cmd_note_title":"","category":"","sub_category":"","description":"","tags":"","command":body}
        d.update(_parse_cmd_meta(meta))
        if _norm(d.get("command")):out.append(d)
    return out
_CMD_ANCHOR_EDIT="cmdedit:"
_CMD_ANCHOR_DEL="cmddelete:"
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
def _cmd_meta_text(data,note_name=""):
    parts=[]
    nt=_norm(data.get("cmd_note_title","")) or _norm(note_name)
    if nt:parts.append(f"Command Note Tittle:{nt}")
    cat=_norm(data.get("category",""))
    sub=_norm(data.get("sub_category",""))
    desc=_norm(data.get("description",""))
    tags=_norm(data.get("tags",""))
    if cat:parts.append(f"Category:{cat}")
    if sub:parts.append(f"Sub Category:{sub}")
    if desc:parts.append(f"Description:{desc}")
    if tags:parts.append(f"Tags:{tags}")
    return ", ".join(parts)
def _cmd_block_html(data,note_name=""):
    cmd=(data.get("command","") or "").rstrip()
    if not _norm(cmd):return ""
    meta=_html_escape(_cmd_meta_text(data,note_name))
    lines=cmd.splitlines() or [""]
    cmd_html="<br>".join(_html_escape(l) for l in lines)
    return f"&lt;C [{meta}] &gt;<br>{cmd_html}<br>&lt;/C&gt;"
def _replace_cmd_tables_with_c(html_text,note_name=""):
    if not html_text:return ""
    rx=re.compile(r"<table[^>]*>.*?</table>",re.S|re.I)
    def _rep(m):
        block=m.group(0)
        if _CMD_ANCHOR_EDIT not in block and _CMD_ANCHOR_DEL not in block:
            return block
        m2=re.search(r"cmdedit:([A-Za-z0-9_-]+)",block)
        if not m2:m2=re.search(r"cmddelete:([A-Za-z0-9_-]+)",block)
        if not m2:return block
        data=_decode_cmd_token(m2.group(1))
        if not data or not _norm(data.get("command","")):return block
        h=_cmd_block_html(data,note_name)
        return f"<p>{h}</p>" if h else block
    return rx.sub(_rep,html_text)
def _sync_note_commands(cur,note_id,note_name,html_text,now,cmd_blocks=None):
    if isinstance(cmd_blocks,list):cmds=cmd_blocks
    else:
        try:plain=_html_to_plain(html_text)
        except Exception:plain=_norm(html_text)
        cmds=_parse_cmd_blocks(plain)
    try:cur.execute("DELETE FROM Commands WHERE note_id=?",(int(note_id),))
    except Exception:return 0
    for c in cmds or []:
        try:
            cur.execute("INSERT INTO Commands(note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(int(note_id),_norm(note_name),_norm(c.get("cmd_note_title","")),_norm(c.get("category","")),_norm(c.get("sub_category","")),_norm(c.get("description","")),_norm(c.get("tags","")),(c.get("command","") or "").rstrip(),now,now))
        except Exception:
            pass
    return len(cmds or [])
def _note_to_markdown(note_name,html_text):
    name=_norm(note_name) or "Untitled"
    plain=_html_to_plain(html_text)
    rx=re.compile(r"<C\s*\[(.*?)\]\s*>\s*(.*?)\s*</C>",re.S|re.I)
    out=[f"# {name}",""]
    pos=0
    for m in rx.finditer(plain):
        pre=plain[pos:m.start()]
        if pre.strip():
            out.append(pre.rstrip())
            out.append("")
        meta=_parse_cmd_meta(m.group(1))
        cmd=(m.group(2) or "").rstrip()
        ttl=_norm(meta.get("cmd_note_title")) or name
        out.append(f"## {ttl}")
        if meta.get("category"):out.append(f"- Category: {meta.get('category')}")
        if meta.get("sub_category"):out.append(f"- Sub Category: {meta.get('sub_category')}")
        if meta.get("tags"):out.append(f"- Tags: {meta.get('tags')}")
        if meta.get("description"):out.append(f"- Description: {meta.get('description')}")
        out.append("")
        fence=_code_fence(cmd)
        out.append(f"{fence}bash")
        out.append(cmd)
        out.append(fence)
        out.append("")
        pos=m.end()
    tail=plain[pos:]
    if tail.strip():
        out.append(tail.rstrip())
        out.append("")
    return "\n".join(out).strip()+"\n"
def _commands_notes_to_markdown(rows):
    out=["# Commands Notes",""]
    for r in rows or []:
        title=_norm(r.get("note_name","")) or "Unlinked"
        cat=_norm(r.get("category",""))
        sub=_norm(r.get("sub_category",""))
        tags=_norm(r.get("tags",""))
        desc=_norm(r.get("description",""))
        cmd=_norm(r.get("command",""))
        out.append(f"## {title}")
        if cat:out.append(f"- Category: {cat}")
        if sub:out.append(f"- Sub Category: {sub}")
        if tags:out.append(f"- Tags: {tags}")
        if desc:out.append(f"- Description: {desc}")
        out.append("")
        fence=_code_fence(cmd)
        out.append(f"{fence}bash")
        out.append(cmd)
        out.append(fence)
        out.append("")
    return "\n".join(out).strip()+"\n"
def _parse_commands_notes_markdown(md_text):
    lines=(md_text or "").splitlines()
    sections=[];title=None;buf=[]
    for line in lines:
        m=re.match(r"^\s*##\s+(.*)$",line)
        if m:
            if title is not None:sections.append((title,buf))
            title=_norm(m.group(1));buf=[];continue
        if title is not None:buf.append(line)
    if title is not None:sections.append((title,buf))
    out=[]
    for title,buf in sections:
        meta={"category":"","sub_category":"","tags":"","description":""}
        cmd_lines=[];fence=None;in_code=False
        for line in buf:
            if fence is None:
                m=re.match(r"^\s*(`{3,})",line)
                if m:
                    fence=m.group(1);in_code=True;continue
            else:
                if line.strip().startswith(fence):
                    in_code=False;fence=None;continue
            if in_code:
                cmd_lines.append(line);continue
            s=line.strip()
            if not s.startswith("-"):continue
            s=s.lstrip("-").strip()
            if not s or ":" not in s:continue
            key,val=s.split(":",1)
            key=_l(key);val=_norm(val)
            if key=="category":meta["category"]=val
            elif key in ("sub category","subcategory","sub-category"):meta["sub_category"]=val
            elif key=="tags":meta["tags"]=val
            elif key=="description":meta["description"]=val
        command="\n".join(cmd_lines).rstrip()
        if not _norm(command):
            rest=[];fence=None;in_code=False
            for line in buf:
                if fence is None:
                    m=re.match(r"^\s*(`{3,})",line)
                    if m:
                        fence=m.group(1);in_code=True;continue
                else:
                    if line.strip().startswith(fence):
                        in_code=False;fence=None;continue
                if in_code:continue
                s=line.strip()
                if not s:continue
                if s.startswith("-") and ":" in s:continue
                rest.append(line)
            command="\n".join(rest).strip()
        if not _norm(command):continue
        out.append({"note_name":_norm(title) or "Unlinked","category":meta.get("category",""),"sub_category":meta.get("sub_category",""),"command":command,"tags":meta.get("tags",""),"description":meta.get("description","")})
    return out
def _cmd_key(s):
    s=_norm(s)
    if not s:return ""
    return re.sub(r"\s+"," ",s).strip().lower()
def _safe_tables(tables):
    out=[]
    for t in tables:
        tt=_norm(t)
        if not tt or tt.lower().startswith("sqlite_"):continue
        if re.fullmatch(r"[A-Za-z0-9_]+",tt):out.append(tt)
    return out
def _fmt_size(n):
    try:n=int(n)
    except:return "0 B"
    for u in ("B","KB","MB","GB","TB"):
        if n<1024:return f"{n} {u}"
        n//=1024
    return f"{n} PB"
def _progress(owner,title,subtitle):
    d=QDialog(owner);d.setObjectName("ProgressDialog");d.setWindowTitle(title);d.setModal(True);d.resize(520,140)
    v=QVBoxLayout(d);v.setContentsMargins(14,14,14,14);v.setSpacing(10)
    t=QLabel(subtitle,d);t.setObjectName("PageTitle");v.addWidget(t,0)
    s=QLabel("",d);s.setObjectName("PageSubTitle");v.addWidget(s,0)
    b=QProgressBar(d);b.setRange(0,100);b.setValue(0);v.addWidget(b,0)
    d._title=t;d._sub=s;d._bar=b
    return d
def _set_prog(d,pct,msg=""):
    try:
        d._bar.setValue(max(0,min(100,int(pct))))
        d._sub.setText(_norm(msg))
    except:pass
    try:QApplication.processEvents()
    except:pass
def _apply_migrations(con):
    try:cur=con.cursor()
    except:return
    try:
        cur.execute("PRAGMA user_version")
        row=cur.fetchone()
        ver=int(row[0]) if row and str(row[0]).isdigit() else 0
    except:ver=0
    now=datetime.utcnow().isoformat()
    try:cur.execute("CREATE TABLE IF NOT EXISTS SchemaMigrations(version INTEGER PRIMARY KEY,applied_at TEXT)")
    except:pass
    if ver<1:
        try:cur.execute("INSERT OR IGNORE INTO SchemaMigrations(version,applied_at) VALUES(1,?)",(now,))
        except:pass
        ver=1
    if ver<2:
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS NotesHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,content TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_hist_note_id ON NotesHistory(note_id)")
        except:pass
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS CommandsNotesHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,cmd_id INTEGER,note_name TEXT,category TEXT,sub_category TEXT,command TEXT,tags TEXT,description TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_hist_cmd_id ON CommandsNotesHistory(cmd_id)")
        except:pass
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS CommandsHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,cmd_id INTEGER,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_hist_cmd_id ON CommandsHistory(cmd_id)")
        except:pass
        try:cur.execute("INSERT OR IGNORE INTO SchemaMigrations(version,applied_at) VALUES(2,?)",(now,))
        except:pass
        ver=2
    try:cur.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
    except:pass
    try:con.commit()
    except:pass
class Note_LOYA_Database:
    def __init__(self,path=None):self.path=path or _db_path()
    def exists(self):return os.path.isfile(self.path)
    def connect(self):
        os.makedirs(os.path.dirname(self.path),exist_ok=True)
        return sqlite3.connect(self.path)
    def ensure(self):
        con=self.connect();cur=con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS Notes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT,content TEXT,created_at TEXT,updated_at TEXT)")
        try:cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_notes_name ON Notes(note_name)")
        except:pass
        cur.execute("CREATE TABLE IF NOT EXISTS CommandsNotes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT,category TEXT,sub_category TEXT,command TEXT,tags TEXT,description TEXT,created_at TEXT,updated_at TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS Commands(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,created_at TEXT,updated_at TEXT)")
        try:
            cur.execute("PRAGMA table_info(Commands)")
            cols=[r[1] for r in cur.fetchall()]
            if "note_id" not in cols:cur.execute("ALTER TABLE Commands ADD COLUMN note_id INTEGER")
            if "cmd_note_title" not in cols:cur.execute("ALTER TABLE Commands ADD COLUMN cmd_note_title TEXT")
            if "description" not in cols:cur.execute("ALTER TABLE Commands ADD COLUMN description TEXT")
        except:pass
        _apply_migrations(con)
        con.commit();con.close()
    def list_tables(self):
        if not self.exists():return []
        con=self.connect();cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        t=[r[0] for r in cur.fetchall()]
        con.close()
        return _safe_tables(t)
    def table_cols(self,table):
        con=self.connect();cur=con.cursor()
        try:
            cur.execute(f"PRAGMA table_info({table})")
            cols=[r[1] for r in cur.fetchall()]
        except:cols=[]
        con.close()
        return cols
    def read_table(self,table):
        con=self.connect();con.row_factory=sqlite3.Row;cur=con.cursor()
        try:
            cur.execute(f"SELECT * FROM {table}")
            rows=[dict(r) for r in cur.fetchall()]
        except:rows=[]
        con.close()
        return rows
    def list_note_names(self):
        self.ensure()
        con=self.connect();cur=con.cursor()
        try:cur.execute("SELECT note_name FROM Notes ORDER BY note_name COLLATE NOCASE")
        except:rows=[]
        else:rows=[_norm(r[0]) for r in cur.fetchall()]
        con.close()
        return [r for r in rows if r]
    def read_note_by_name(self,name):
        self.ensure()
        con=self.connect();cur=con.cursor()
        try:
            cur.execute("SELECT note_name,content FROM Notes WHERE note_name=?",(name,))
            r=cur.fetchone()
        except:r=None
        con.close()
        if not r:return None
        return {"note_name":r[0] or "","content":r[1] or ""}
    def sync_commands_from_notes(self,names=None,progress=None):
        self.ensure()
        con=self.connect();cur=con.cursor()
        total_cmds=0;done=0
        rows=[]
        if names:
            names=[_norm(x) for x in names if _norm(x)]
            if names:
                q=",".join(["?"]*len(names))
                try:cur.execute(f"SELECT id,note_name,content FROM Notes WHERE note_name IN ({q})",names)
                except Exception:rows=[]
                else:rows=cur.fetchall()
        if not rows:
            try:cur.execute("SELECT id,note_name,content FROM Notes")
            except Exception:rows=[]
            else:rows=cur.fetchall()
        total=max(1,len(rows))
        for nid,name,content in rows:
            done+=1
            if progress and done%10==0:_set_prog(progress,int((done*100)/total),"Syncing commands ...")
            plain=_html_to_plain(content or "")
            if "<C [" not in plain:continue
            cmds=_parse_cmd_blocks(plain)
            try:cur.execute("DELETE FROM Commands WHERE note_id=?",(int(nid),))
            except Exception:continue
            for c in cmds:
                try:
                    cur.execute("INSERT INTO Commands(note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(int(nid),_norm(name),_norm(c.get("cmd_note_title","")),_norm(c.get("category","")),_norm(c.get("sub_category","")),_norm(c.get("description","")),_norm(c.get("tags","")),(c.get("command","") or "").rstrip(),_norm(c.get("created_at","")) or _now(),_norm(c.get("updated_at","")) or _now()))
                    total_cmds+=1
                except Exception:
                    pass
        con.commit();con.close()
        return {"notes":len(rows),"commands":total_cmds}
    def export_json_tables(self,out_path,progress=None):
        self.ensure()
        tables=self.list_tables()
        total=max(1,len(tables))
        obj={}
        for i,t in enumerate(tables):
            if progress:_set_prog(progress,int((i*100)/total),f"Reading {t} ...")
            obj[t]=self.read_table(t)
        if progress:_set_prog(progress,95,"Writing JSON ...")
        _write_json(out_path,obj)
        if progress:_set_prog(progress,100,"Done.")
    def export_csv_zip(self,out_zip,progress=None):
        self.ensure()
        tables=self.list_tables()
        total=max(1,len(tables))
        with zipfile.ZipFile(out_zip,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for i,t in enumerate(tables):
                if progress:_set_prog(progress,int((i*100)/total),f"Exporting {t}.csv ...")
                rows=self.read_table(t)
                cols=self.table_cols(t)
                if not cols and rows:cols=list(rows[0].keys())
                import io
                buf=io.StringIO()
                w=csv.DictWriter(buf,fieldnames=cols or [])
                w.writeheader()
                for r in rows:w.writerow({k:(r.get(k,"") if r.get(k) is not None else "") for k in (cols or [])})
                z.writestr(f"{t}.csv",buf.getvalue().encode("utf-8"))
        if progress:_set_prog(progress,100,"Done.")
    def export_markdown_zip(self,out_zip,progress=None):
        self.ensure()
        con=self.connect();con.row_factory=sqlite3.Row;cur=con.cursor()
        cur.execute("SELECT id,note_name,content FROM Notes ORDER BY id ASC")
        notes=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT note_name,category,sub_category,command,tags,description FROM CommandsNotes ORDER BY id ASC")
        cmd_notes=[dict(r) for r in cur.fetchall()]
        con.close()
        total=max(1,len(notes)+1)
        used=set()
        with zipfile.ZipFile(out_zip,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for i,n in enumerate(notes):
                if progress:_set_prog(progress,int((i*100)/total),f"Writing {n.get('note_name','') or 'Note'} ...")
                base=_safe_filename(n.get("note_name",""),fallback=f"note_{n.get('id','') or i+1}")
                name=base
                suffix=2
                while name.lower() in used:
                    name=f"{base}_{suffix}"
                    suffix+=1
                used.add(name.lower())
                md=_note_to_markdown(n.get("note_name",""),n.get("content",""))
                z.writestr(f"Notes/{name}.md",md.encode("utf-8"))
            if cmd_notes:
                if progress:_set_prog(progress,int((len(notes)*100)/total),"Writing CommandsNotes ...")
                z.writestr("CommandsNotes.md",_commands_notes_to_markdown(cmd_notes).encode("utf-8"))
        if progress:_set_prog(progress,100,"Done.")
    def export_note_markdown(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        title=_norm(note.get("note_name","")) or "Untitled"
        body=_html_to_markdown(note.get("content","") or "")
        body=body.strip()
        need_title=True
        if body:
            for line in body.splitlines():
                if not _norm(line):continue
                m=re.match(r"^#\s+(.*)$",line)
                if m and _l(m.group(1))==_l(title):need_title=False
                break
        parts=[]
        if need_title:
            parts.append(f"# {title}")
            if body:parts.append("")
        if body:parts.append(body)
        with open(out_path,"w",encoding="utf-8") as f:f.write("\n".join(parts).rstrip()+"\n")
    def export_note_markdown_human(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        title=_norm(note.get("note_name","")) or "Untitled"
        html=_replace_cmd_tables_with_c(note.get("content","") or "",title)
        md=_note_to_markdown(title,html)
        with open(out_path,"w",encoding="utf-8") as f:f.write(md)
    def export_note_html(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        title=_norm(note.get("note_name","")) or "Untitled"
        body=_extract_html_body(note.get("content","") or "")
        doc=[
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset=\"utf-8\" />",
            f"<title>{_html_escape(title)}</title>",
            "</head>",
            "<body>",
            f"<h1>{_html_escape(title)}</h1>",
            body,
            "</body>",
            "</html>",
        ]
        with open(out_path,"w",encoding="utf-8") as f:f.write("\n".join(doc))
    def copy_db(self,out_path):
        self.ensure()
        shutil.copy2(self.path,out_path)
    def _unique_key(self,table,row):
        t=table.lower()
        if t=="notes":return _l(row.get("note_name",""))
        if t=="commandsnotes":return _cmd_key(row.get("command",""))
        if t=="commands":return _cmd_key(row.get("command",""))
        return ""
    def _summ(self,table,row):
        t=table.lower()
        if t=="notes":return f'{_norm(row.get("note_name",""))}'
        if t=="commandsnotes":return f'{_norm(row.get("note_name",""))} | {_norm(row.get("category",""))}/{_norm(row.get("sub_category",""))}'
        if t=="commands":return f'{_norm(row.get("note_name",""))} | {_norm(row.get("category",""))}/{_norm(row.get("sub_category",""))}'
        return _norm(json.dumps(row,ensure_ascii=False))
    def load_existing_maps(self):
        self.ensure()
        tables=self.list_tables()
        existing={}
        for t in tables:
            rows=self.read_table(t)
            m={}
            for r in rows:
                k=self._unique_key(t,r)
                if k and k not in m:m[k]=r
            existing[t]={"rows":rows,"map":m}
        return existing
    def parse_incoming_db(self,path,progress=None):
        con=sqlite3.connect(path);cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables=_safe_tables([r[0] for r in cur.fetchall()])
        out={}
        total=max(1,len(tables))
        for i,t in enumerate(tables):
            if progress:_set_prog(progress,int((i*100)/total),f"Reading {t} ...")
            try:
                cur.execute(f"SELECT * FROM {t}")
                cols=[d[0] for d in cur.description] if cur.description else []
                rows=[dict(zip(cols,r)) for r in cur.fetchall()]
            except:rows=[]
            out[t]=rows
        con.close()
        return out
    def parse_incoming_json(self,path,progress=None):
        if progress:_set_prog(progress,25,"Reading JSON ...")
        d=_read_json(path,{})
        if isinstance(d,dict):return { _norm(k): (v if isinstance(v,list) else []) for k,v in d.items() if _norm(k)}
        if isinstance(d,list):return {"CommandsNotes":[x for x in d if isinstance(x,dict)]}
        return {}
    def parse_incoming_markdown(self,path,progress=None):
        if progress:_set_prog(progress,15,"Reading Markdown ...")
        text=_read_text_any(path)
        if not text:return {}
        title,body=_extract_md_title(text)
        if _l(title)=="commands notes" and re.search(r"^\s*##\s+",body or "",re.M):
            if progress:_set_prog(progress,60,"Parsing Commands Notes ...")
            rows=_parse_commands_notes_markdown(body)
            return {"CommandsNotes":rows}
        if progress:_set_prog(progress,60,"Parsing Notes ...")
        name=_norm(title)
        if not name:
            base=os.path.splitext(os.path.basename(path))[0]
            name=_safe_filename(base,fallback="Imported Note")
        html_text=_markdown_to_html(_wrap_c_blocks(text))
        cmd_blocks=_parse_cmd_blocks(text)
        row={"note_name":name,"content":html_text}
        if cmd_blocks:row["cmd_blocks"]=cmd_blocks
        return {"Notes":[row]}
    def parse_incoming_csv_zip(self,path,progress=None):
        out={}
        if not path.lower().endswith(".zip"):
            with open(path,"r",encoding="utf-8",newline="") as f:
                rd=csv.DictReader(f)
                out["CommandsNotes"]=[{k:v for k,v in (r or {}).items()} for r in rd]
            return out
        with zipfile.ZipFile(path,"r") as z:
            names=[n for n in z.namelist() if n.lower().endswith(".csv")]
            total=max(1,len(names))
            for i,n in enumerate(names):
                if progress:_set_prog(progress,int((i*100)/total),f"Reading {n} ...")
                try:
                    with z.open(n,"r") as f:
                        txt=f.read().decode("utf-8","ignore").splitlines()
                        rd=csv.DictReader(txt)
                        t=os.path.splitext(os.path.basename(n))[0]
                        out[_norm(t)]=[{k:v for k,v in (r or {}).items()} for r in rd]
                except:pass
        return out
    def _normalize_row(self,table,row):
        t=table.lower()
        r={k:("" if v is None else v) for k,v in (row or {}).items()} if isinstance(row,dict) else {}
        if t=="notes":
            out={"note_name":_norm(r.get("note_name",r.get("title",""))),"content":r.get("content","") or "", "created_at":_norm(r.get("created_at","")), "updated_at":_norm(r.get("updated_at",""))}
            if isinstance(r.get("cmd_blocks"),list):out["cmd_blocks"]=r.get("cmd_blocks")
            return out
        if t=="commandsnotes":
            return {"note_name":_norm(r.get("note_name",r.get("title",""))),"category":_norm(r.get("category","")),"sub_category":_norm(r.get("sub_category",r.get("sub",""))),"command":_norm(r.get("command","")),"tags":_norm(r.get("tags","")),"description":_norm(r.get("description","")),"created_at":_norm(r.get("created_at","")),"updated_at":_norm(r.get("updated_at",""))}
        if t=="commands":
            return {"note_id":r.get("note_id",""),"note_name":_norm(r.get("note_name",r.get("title",""))),"cmd_note_title":_norm(r.get("cmd_note_title","")),"category":_norm(r.get("category","")),"sub_category":_norm(r.get("sub_category",r.get("sub",""))),"command":_norm(r.get("command","")),"tags":_norm(r.get("tags","")),"description":_norm(r.get("description","")),"created_at":_norm(r.get("created_at","")),"updated_at":_norm(r.get("updated_at",""))}
        return {k:(_norm(v) if isinstance(v,str) else v) for k,v in r.items()}
    def build_import_plan(self,incoming,existing,progress=None):
        plan={"new":[],"dups":[],"skip":[]}
        tables=[t for t in incoming.keys() if _norm(t)]
        total=max(1,sum(len(incoming.get(t,[]) or []) for t in tables))
        done=0
        for t in tables:
            in_rows=incoming.get(t,[]) or []
            ex_map=(existing.get(t,{}).get("map") if existing.get(t) else {}) or {}
            for rr in in_rows:
                done+=1
                if progress and done%20==0:_set_prog(progress,int((done*100)/total),f"Scanning {t} ...")
                r=self._normalize_row(t,rr)
                k=self._unique_key(t,r)
                if not k:
                    plan["skip"].append({"table":t,"incoming":r})
                    continue
                if k in ex_map:
                    plan["dups"].append({"table":t,"key":k,"existing":ex_map[k],"incoming":r})
                else:
                    plan["new"].append({"table":t,"key":k,"incoming":r})
        return plan
    def apply_plan(self,plan,decisions,progress=None):
        self.ensure()
        con=self.connect();cur=con.cursor()
        now=datetime.utcnow().isoformat()
        def ins(t,r):
            tl=t.lower()
            if tl=="notes":
                cur.execute("INSERT INTO Notes(note_name,content,created_at,updated_at) VALUES(?,?,?,?)",(_norm(r.get("note_name","")),r.get("content","") or "",r.get("created_at") or now,r.get("updated_at") or now))
                try:
                    nid=int(cur.lastrowid)
                    _sync_note_commands(cur,nid,_norm(r.get("note_name","")),r.get("content","") or "",now,r.get("cmd_blocks"))
                except Exception:
                    pass
            elif tl=="commandsnotes":
                cur.execute("INSERT INTO CommandsNotes(note_name,category,sub_category,command,tags,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(_norm(r.get("note_name","")),_norm(r.get("category","")),_norm(r.get("sub_category","")),_norm(r.get("command","")),_norm(r.get("tags","")),_norm(r.get("description","")),r.get("created_at") or now,r.get("updated_at") or now))
            elif tl=="commands":
                nid=r.get("note_id",None)
                try:nid=int(nid) if str(nid).isdigit() else None
                except:nid=None
                cur.execute("INSERT INTO Commands(note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(nid,_norm(r.get("note_name","")),_norm(r.get("cmd_note_title","")),_norm(r.get("category","")),_norm(r.get("sub_category","")),_norm(r.get("description","")),_norm(r.get("tags","")),_norm(r.get("command","")),r.get("created_at") or now,r.get("updated_at") or now))
            else:
                cols=list((r or {}).keys())
                if not cols:return
                if not re.fullmatch(r"[A-Za-z0-9_]+",t):return
                cur.execute(f"CREATE TABLE IF NOT EXISTS {t}({','.join([c+' TEXT' for c in cols])})")
                cur.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join(['?']*len(cols))})",[str(r.get(c,"")) for c in cols])
        def upd(t,old,r):
            tl=t.lower()
            if tl=="notes":
                cur.execute("UPDATE Notes SET content=?,updated_at=? WHERE note_name=?",(r.get("content","") or "",now,_norm(old.get("note_name",""))))
                try:
                    cur.execute("SELECT id FROM Notes WHERE note_name=?",( _norm(old.get("note_name","")),))
                    row=cur.fetchone()
                    nid=int(row[0]) if row else None
                    if nid:_sync_note_commands(cur,nid,_norm(old.get("note_name","")),r.get("content","") or "",now,r.get("cmd_blocks"))
                except Exception:
                    pass
            elif tl=="commandsnotes":
                cmd=_cmd_key(old.get("command",""))
                cur.execute("UPDATE CommandsNotes SET note_name=?,category=?,sub_category=?,command=?,tags=?,description=?,updated_at=? WHERE lower(trim(command))=?",(r.get("note_name",""),r.get("category",""),r.get("sub_category",""),r.get("command",""),r.get("tags",""),r.get("description",""),now,cmd))
            elif tl=="commands":
                cmd=_cmd_key(old.get("command",""))
                nid=r.get("note_id",None)
                try:nid=int(nid) if str(nid).isdigit() else None
                except:nid=None
                cur.execute("UPDATE Commands SET note_id=?,note_name=?,cmd_note_title=?,category=?,sub_category=?,description=?,tags=?,command=?,updated_at=? WHERE lower(trim(command))=?",(nid,r.get("note_name",""),r.get("cmd_note_title",""),r.get("category",""),r.get("sub_category",""),r.get("description",""),r.get("tags",""),r.get("command",""),now,cmd))
        def del_by_unique(t,old):
            tl=t.lower()
            if tl=="notes":cur.execute("DELETE FROM Notes WHERE note_name=?",( _norm(old.get("note_name","")),))
            elif tl=="commandsnotes":cur.execute("DELETE FROM CommandsNotes WHERE lower(trim(command))=?",( _cmd_key(old.get("command","")),))
            elif tl=="commands":cur.execute("DELETE FROM Commands WHERE lower(trim(command))=?",( _cmd_key(old.get("command","")),))
        new_rows=plan.get("new",[]) or []
        dups=plan.get("dups",[]) or []
        total=max(1,len(new_rows)+len(dups))
        done=0
        added=0;replaced=0;overwritten=0;skipped=0;bad=0
        for it in new_rows:
            done+=1
            if progress and done%25==0:_set_prog(progress,int((done*100)/total),f"Importing {it.get('table','')} ...")
            try:ins(it["table"],it["incoming"]);added+=1
            except:bad+=1
        for idx,it in enumerate(dups):
            done+=1
            act=decisions.get(idx,"Skip")
            if act=="Skip":skipped+=1;continue
            try:
                if act=="Replace":
                    upd(it["table"],it["existing"],it["incoming"]);replaced+=1
                else:
                    del_by_unique(it["table"],it["existing"])
                    ins(it["table"],it["incoming"]);overwritten+=1
            except:bad+=1
            if progress and done%25==0:_set_prog(progress,int((done*100)/total),f"Applying duplicates ...")
        con.commit();con.close()
        return {"added":added,"replaced":replaced,"overwritten":overwritten,"skipped":skipped,"bad":bad,"dups":len(dups),"new":len(new_rows),"unknown_skipped":len(plan.get("skip",[]) or [])}
    def summarize_dup(self,it):
        return {"table":it.get("table",""),"key":it.get("key",""),"existing":self._summ(it.get("table",""),it.get("existing") or {}),"incoming":self._summ(it.get("table",""),it.get("incoming") or {}),"ex_cmd":_norm((it.get("existing") or {}).get("command","")),"in_cmd":_norm((it.get("incoming") or {}).get("command",""))}
class TargetValues:
    def __init__(self,path=None):self.path=path or _targets_values_path()
    def load(self):
        d=_read_json(self.path,{})
        out={}
        if isinstance(d,dict):
            for k,v in d.items():
                kk=_norm(k)
                if not kk:continue
                vv=v.get("priority",v.get("value",0)) if isinstance(v,dict) else v
                try:vv=int(vv)
                except:vv=0
                entry={"priority":max(0,min(65535,vv))}
                if isinstance(v,dict) and v.get("manual"):entry["manual"]=True
                out[kk]=entry
        return out
    def save(self,data):
        out={}
        for k,v in (data or {}).items():
            kk=_norm(k)
            if not kk:continue
            try:vv=int((v or {}).get("priority",(v or {}).get("value",0)))
            except:vv=0
            entry={"priority":max(0,min(65535,vv))}
            if isinstance(v,dict) and v.get("manual"):entry["manual"]=True
            out[kk]=entry
        return _write_json(self.path,out)
    def export_json(self,out_path,data):
        out={}
        for k,v in (data or {}).items():
            entry={"priority":int((v or {}).get("priority",(v or {}).get("value",0)) or 0)}
            if isinstance(v,dict) and v.get("manual"):entry["manual"]=True
            out[k]=entry
        _write_json(out_path,out)
    def export_csv(self,out_path,data):
        with open(out_path,"w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=["key","priority"]);w.writeheader()
            for k,v in sorted((data or {}).items(),key=lambda x:x[0].lower()):
                w.writerow({"key":_norm(k),"priority":int((v or {}).get("priority",(v or {}).get("value",0)) or 0)})
    def parse_json(self,path):
        d=_read_json(path,{})
        if not isinstance(d,dict):return {}
        out={}
        for k,v in d.items():
            kk=_norm(k)
            if not kk:continue
            vv=v.get("priority",v.get("value",0)) if isinstance(v,dict) else v
            try:vv=int(vv)
            except:vv=0
            entry={"priority":max(0,min(65535,vv))}
            if isinstance(v,dict) and v.get("manual"):entry["manual"]=True
            out[kk]=entry
        return out
    def parse_csv(self,path):
        out={}
        with open(path,"r",encoding="utf-8",newline="") as f:
            rd=csv.DictReader(f)
            for r in rd:
                kk=_norm(r.get("key",r.get("name","")))
                if not kk:continue
                try:vv=int(_norm(r.get("priority",r.get("value","0"))) or "0")
                except:vv=0
                out[kk]={"priority":max(0,min(65535,vv))}
        return out
    def build_plan(self,incoming,base):
        dups=[];new={}
        base_ci={_l(k):k for k in (base or {}).keys()}
        for k,v in (incoming or {}).items():
            lk=_l(k)
            if lk in base_ci:
                exk=base_ci[lk]
                dups.append({"key":k,"existing_key":exk,"existing":base.get(exk,{}),"incoming":v})
            else:
                new[k]=v
        return {"new":new,"dups":dups}
    def apply_plan(self,base,plan,decisions):
        added=0;replaced=0;overwritten=0;skipped=0
        for k,v in (plan.get("new") or {}).items():
            entry={"priority":int((v or {}).get("priority",(v or {}).get("value",0)) or 0)}
            if isinstance(v,dict) and v.get("manual"):entry["manual"]=True
            base[_norm(k)]=entry;added+=1
        for idx,d in enumerate(plan.get("dups") or []):
            act=decisions.get(idx,"Skip")
            if act=="Skip":skipped+=1;continue
            exk=d.get("existing_key","")
            if act=="Replace":
                incoming=d.get("incoming") or {}
                existing=base.get(exk,{})
                entry={"priority":int((incoming.get("priority",incoming.get("value",0)) or 0))}
                if isinstance(incoming,dict) and "manual" in incoming:
                    if incoming.get("manual"):entry["manual"]=True
                elif isinstance(existing,dict) and existing.get("manual"):
                    entry["manual"]=True
                base[exk]=entry;replaced+=1
            else:
                del base[exk]
                incoming=d.get("incoming") or {}
                entry={"priority":int((incoming.get("priority",incoming.get("value",0)) or 0))}
                if isinstance(incoming,dict) and incoming.get("manual"):entry["manual"]=True
                base[_norm(d.get("key",""))]=entry;overwritten+=1
        return {"added":added,"replaced":replaced,"overwritten":overwritten,"skipped":skipped,"dups":len(plan.get("dups") or [])}
class Targets:
    def __init__(self,path=None):self.path=path or _targets_path()
    def load(self):
        d=_read_json(self.path,[])
        if isinstance(d,list):return d
        if isinstance(d,dict):return [d]
        return []
    def save(self,data):
        arr=[x for x in (data or []) if isinstance(x,(dict,list,str,int,float,bool)) or x is None]
        return _write_json(self.path,arr)
    def export_json(self,out_path,data):_write_json(out_path,data if isinstance(data,list) else [data] if isinstance(data,dict) else [])
    def parse_json(self,path):
        d=_read_json(path,[])
        if isinstance(d,list):return d
        if isinstance(d,dict):return [d]
        return []
    def _key(self,item):
        if isinstance(item,dict):
            if _norm(item.get("id","")):return "id:"+_l(item.get("id",""))
            if _norm(item.get("name","")):return "name:"+_l(item.get("name",""))
        return "raw:"+_l(json.dumps(item,ensure_ascii=False,sort_keys=True))
    def _summ(self,item):
        if isinstance(item,dict):
            a=_norm(item.get("id",""));b=_norm(item.get("name",""));c=_norm(item.get("status",""))
            if a or b:return f"{a} {b} {c}".strip()
        return _norm(json.dumps(item,ensure_ascii=False))[:120]
    def build_plan(self,incoming,base):
        base_map={}
        for it in (base or []):
            k=self._key(it)
            if k and k not in base_map:base_map[k]=it
        dups=[];new=[]
        for it in (incoming or []):
            k=self._key(it)
            if k in base_map:dups.append({"key":k,"existing":base_map[k],"incoming":it})
            else:new.append(it)
        return {"new":new,"dups":dups}
    def apply_plan(self,base,plan,decisions):
        added=0;replaced=0;overwritten=0;skipped=0
        for it in (plan.get("new") or []):
            base.append(it);added+=1
        for idx,d in enumerate(plan.get("dups") or []):
            act=decisions.get(idx,"Skip")
            if act=="Skip":skipped+=1;continue
            ek=d.get("key","")
            if act=="Replace":
                for i,cur in enumerate(list(base)):
                    if self._key(cur)==ek:
                        base[i]=d.get("incoming");replaced+=1;break
            else:
                base=[x for x in base if self._key(x)!=ek]
                base.append(d.get("incoming"));overwritten+=1
        return base,{"added":added,"replaced":replaced,"overwritten":overwritten,"skipped":skipped,"dups":len(plan.get("dups") or [])}
class Backup:
    def __init__(self,dir_path=None):self.dir=dir_path or _backups_dir()
    def list(self):
        rows=[]
        try:
            for n in os.listdir(self.dir):
                if not n.lower().endswith(".zip"):continue
                p=os.path.join(self.dir,n)
                try:
                    st=os.stat(p)
                    rows.append((p,st.st_mtime,st.st_size))
                except:pass
        except:pass
        rows.sort(key=lambda x:x[1],reverse=True)
        return rows
    def latest(self):
        rows=self.list()
        return rows[0] if rows else (None,None,None)
    def trim(self,keep):
        try:keep=max(1,int(keep))
        except:keep=20
        rows=self.list()
        ok=0;bad=0
        for p,_,_ in rows[keep:]:
            try:
                if p and os.path.isfile(p) and os.path.dirname(os.path.abspath(p))==os.path.abspath(self.dir):
                    os.remove(p);ok+=1
                else:bad+=1
            except:bad+=1
        return ok,bad
    def create(self,progress=None):
        os.makedirs(self.dir,exist_ok=True)
        name=f"Backup_{_now()}.zip"
        out=os.path.join(self.dir,name)
        tmp=tempfile.mkdtemp(prefix="loya_backup_")
        try:
            if progress:_set_prog(progress,10,"Collecting files ...")
            d=_data_dir()
            with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for root,dirs,files in os.walk(d):
                    for fn in files:
                        p=os.path.join(root,fn)
                        rel=os.path.relpath(p,d).replace("\\","/")
                        z.write(p,arcname=f"Data/{rel}")
            if progress:_set_prog(progress,100,"Done.")
        finally:
            try:shutil.rmtree(tmp,ignore_errors=True)
            except:pass
        return out
    def restore(self,zip_path,mode,progress=None):
        if not zip_path or not os.path.isfile(zip_path):return False,"Backup not found"
        if mode not in ("merge","replace"):return False,"Invalid mode"
        tmp=tempfile.mkdtemp(prefix="loya_restore_")
        try:
            if progress:_set_prog(progress,10,"Extracting ...")
            with zipfile.ZipFile(zip_path,"r") as z:z.extractall(tmp)
            src=os.path.join(tmp,"Data")
            dst=_data_dir()
            if not os.path.isdir(src):return False,"Missing Data/ in backup"
            if progress:_set_prog(progress,40,"Restoring Data/ ...")
            if mode=="replace":
                for root,dirs,files in os.walk(src):
                    rel=os.path.relpath(root,src)
                    td=os.path.join(dst,rel) if rel!="." else dst
                    os.makedirs(td,exist_ok=True)
                    for fn in files:shutil.copy2(os.path.join(root,fn),os.path.join(td,fn))
            else:
                for root,dirs,files in os.walk(src):
                    rel=os.path.relpath(root,src)
                    td=os.path.join(dst,rel) if rel!="." else dst
                    os.makedirs(td,exist_ok=True)
                    for fn in files:
                        dp=os.path.join(td,fn)
                        if os.path.exists(dp):continue
                        shutil.copy2(os.path.join(root,fn),dp)
            if progress:_set_prog(progress,100,"Done.")
            return True,"Restore done. Restart app if needed."
        except Exception as e:
            return False,f"Restore failed: {e}"
        finally:
            try:shutil.rmtree(tmp,ignore_errors=True)
            except:pass
    def delete(self,paths):
        ok=0;bad=0
        for p in (paths or []):
            try:
                if p and os.path.isfile(p) and os.path.dirname(os.path.abspath(p))==os.path.abspath(self.dir):
                    os.remove(p);ok+=1
                else:bad+=1
            except:bad+=1
        return ok,bad
def auto_backup_if_needed():
    cfg=_get_backup_settings()
    if not cfg.get("auto_enabled"):return False,"Auto backup disabled."
    try:
        back=Backup()
        _,mt,_=back.latest()
        interval=int(cfg.get("interval_hours",24))*3600
        if mt and (time.time()-float(mt))<interval:return False,"Recent backup exists."
        out=back.create()
        try:back.trim(cfg.get("keep",20))
        except:pass
        _log("[+]",f"Auto backup created: {out}")
        return True,os.path.basename(out)
    except Exception as e:
        _log("[!]",f"Auto backup failed ({e})")
        return False,f"Auto backup failed: {e}"
class _PinDialog(QDialog):
    def __init__(self,owner,title,subtitle,confirm=False):
        super().__init__(owner)
        self.setObjectName("TargetDialog")
        self.setWindowTitle(title)
        self.setFixedSize(420,240 if confirm else 200)
        lay=QVBoxLayout(self);lay.setContentsMargins(14,14,14,14);lay.setSpacing(10)
        frame=QFrame(self);frame.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(frame);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        t=QLabel(title,frame);t.setObjectName("TargetFormTitle")
        v.addWidget(t,0)
        if subtitle:
            s=QLabel(subtitle,frame);s.setObjectName("PageSubTitle");s.setWordWrap(True)
            v.addWidget(s,0)
        self.pin=QLineEdit(frame);self.pin.setObjectName("TargetKeyInput");self.pin.setPlaceholderText("PIN");self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.pin,0)
        self.pin2=None
        if confirm:
            self.pin2=QLineEdit(frame);self.pin2.setObjectName("TargetKeyInput");self.pin2.setPlaceholderText("Confirm PIN");self.pin2.setEchoMode(QLineEdit.EchoMode.Password)
            v.addWidget(self.pin2,0)
        bh=QHBoxLayout();bh.setContentsMargins(0,0,0,0);bh.setSpacing(10)
        ok=QToolButton(frame);ok.setObjectName("TargetSaveBtn");ok.setCursor(Qt.CursorShape.PointingHandCursor);ok.setText("OK");ok.setMinimumHeight(30)
        ca=QToolButton(frame);ca.setObjectName("TargetCancelBtn");ca.setCursor(Qt.CursorShape.PointingHandCursor);ca.setText("Cancel");ca.setMinimumHeight(30)
        ok.clicked.connect(self.accept);ca.clicked.connect(self.reject)
        bh.addStretch(1);bh.addWidget(ok,0);bh.addWidget(ca,0);bh.addStretch(1)
        v.addLayout(bh,0)
        lay.addWidget(frame,1)
    def pins(self):
        p1=_clean_pin(self.pin.text())
        p2=_clean_pin(self.pin2.text()) if self.pin2 else ""
        return p1,p2
def _prompt_pin(owner,title,subtitle):
    dlg=_PinDialog(owner,title,subtitle,confirm=False)
    if dlg.exec()!=QDialog.DialogCode.Accepted:return None
    p,_=dlg.pins()
    return p or None
def _prompt_new_pin(owner,title,subtitle):
    dlg=_PinDialog(owner,title,subtitle,confirm=True)
    if dlg.exec()!=QDialog.DialogCode.Accepted:return None
    p1,p2=dlg.pins()
    if not p1 or p1!=p2:
        QMessageBox.warning(owner,"PIN","PINs do not match.")
        return None
    if len(p1)<4:
        QMessageBox.warning(owner,"PIN","PIN should be at least 4 characters.")
        return None
    return p1
def _ensure_decrypted(pin,cfg):
    if not _HAS_CRYPTO:return False,"cryptography not available."
    salt=cfg.get("enc_salt","")
    if not salt:return False,"Encryption salt missing."
    encp=_enc_path();dbp=_db_path()
    if os.path.isfile(encp):
        if os.path.isfile(dbp):return True,"Database already unlocked."
        return _decrypt_db_file(pin,salt)
    if os.path.isfile(dbp):
        ok,msg=_encrypt_db_file(pin,salt)
        if ok:return True,"Encrypted copy created."
        return False,msg
    return True,"Database not found."
def security_unlock_if_needed(owner=None):
    cfg=_get_security_settings()
    if not cfg.get("app_lock_enabled") and not cfg.get("enc_enabled"):return True
    if not _pin_is_set(cfg):
        QMessageBox.warning(owner,"Security","PIN is not set. Configure it in Settings.")
        return False
    if cfg.get("enc_enabled") and not _HAS_CRYPTO:
        QMessageBox.warning(owner,"Security","cryptography is not installed. Disable encryption or install the package.")
        return False
    if cfg.get("enc_enabled") and not cfg.get("enc_salt"):
        QMessageBox.warning(owner,"Security","Encryption is enabled but missing salt. Disable and re-enable encryption.")
        return False
    for _ in range(3):
        pin=_prompt_pin(owner,"Unlock","Enter your PIN to continue.")
        if pin is None:return False
        if not _verify_pin(pin,cfg):
            QMessageBox.warning(owner,"Unlock","Wrong PIN.")
            continue
        _set_session_pin(pin)
        if cfg.get("enc_enabled"):
            ok,msg=_ensure_decrypted(pin,cfg)
            if not ok:
                QMessageBox.warning(owner,"Unlock",msg)
                continue
        return True
    return False
def security_encrypt_on_exit():
    cfg=_get_security_settings()
    if not cfg.get("enc_enabled"):return
    if not _HAS_CRYPTO:return
    pin=_SESSION_PIN
    if not pin:return
    salt=cfg.get("enc_salt","")
    if not salt:return
    if not os.path.isfile(_db_path()):return
    ok,msg=_encrypt_db_file(pin,salt)
    if ok:
        try:os.remove(_db_path())
        except:pass
        _log("[+]",f"DB encrypted on exit")
    else:
        _log("[!]",f"DB encrypt on exit failed: {msg}")
class _DupDialog(QDialog):
    def __init__(self,owner,title,rows):
        super().__init__(owner)
        self.setObjectName("ImportDupDialog")
        self.setWindowTitle(title)
        self.resize(1060,600)
        self._rows=list(rows or [])
        lay=QVBoxLayout(self);lay.setContentsMargins(14,14,14,14);lay.setSpacing(10)
        head=QHBoxLayout();head.setSpacing(10)
        t=QLabel("Duplicates detected",self);t.setObjectName("PageTitle")
        head.addWidget(t,1)
        self.apply_all=QComboBox(self);self.apply_all.setObjectName("HomePerPage")
        self.apply_all.addItems(["Per Item","Skip All","Replace All","Overwrite All"])
        self.apply_all.currentTextChanged.connect(self._apply_all)
        head.addWidget(QLabel("Apply:",self),0);head.addWidget(self.apply_all,0)
        lay.addLayout(head)
        self.table=QTableWidget(self);self.table.setObjectName("HomeTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Action","Table","Key","Existing","Incoming","Incoming Command"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5,QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table,1)
        fb=QHBoxLayout();fb.setSpacing(10)
        self.btn_ok=QToolButton(self);self.btn_ok.setObjectName("TargetSaveBtn");self.btn_ok.setText("Apply")
        self.btn_cancel=QToolButton(self);self.btn_cancel.setObjectName("TargetCancelBtn");self.btn_cancel.setText("Cancel")
        self.btn_ok.clicked.connect(self.accept);self.btn_cancel.clicked.connect(self.reject)
        fb.addStretch(1);fb.addWidget(self.btn_ok,0);fb.addWidget(self.btn_cancel,0)
        lay.addLayout(fb)
        self._render()
    def _make_combo(self):
        cb=QComboBox(self.table);cb.addItems(["Skip","Replace","Overwrite"]);cb.setCurrentText("Skip");return cb
    def _apply_all(self,t):
        if t=="Per Item":return
        want="Skip" if t=="Skip All" else ("Replace" if t=="Replace All" else "Overwrite")
        for r in range(self.table.rowCount()):
            w=self.table.cellWidget(r,0)
            if isinstance(w,QComboBox):w.setCurrentText(want)
    def _render(self):
        self.table.setRowCount(len(self._rows))
        for r,it in enumerate(self._rows):
            self.table.setCellWidget(r,0,self._make_combo())
            t=QTableWidgetItem(_norm(it.get("table","")));t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            k=QTableWidgetItem(_norm(it.get("key",""))[:180]);k.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            ex=QTableWidgetItem(_norm(it.get("existing",""))[:260]);ex.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            inc=QTableWidgetItem(_norm(it.get("incoming",""))[:260]);inc.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            cmd=QTableWidgetItem(_norm(it.get("in_cmd",""))[:260]);cmd.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r,1,t);self.table.setItem(r,2,k);self.table.setItem(r,3,ex);self.table.setItem(r,4,inc);self.table.setItem(r,5,cmd)
            self.table.setRowHeight(r,44)
        self.table.clearSelection()
    def decisions(self):
        out={}
        for r in range(self.table.rowCount()):
            w=self.table.cellWidget(r,0)
            out[r]=w.currentText() if isinstance(w,QComboBox) else "Skip"
        return out
class NCN_Import:
    def __init__(self,db):self.db=db
    def _md_name(self,path):
        base=os.path.splitext(os.path.basename(path))[0]
        name=_norm(base).replace("_"," ").strip()
        return name if name else "Imported Note"
    def _apply_md_name(self,incoming,path):
        if not isinstance(incoming,dict):return incoming
        rows=incoming.get("Notes")
        if isinstance(rows,list):
            name=self._md_name(path)
            for r in rows:
                if isinstance(r,dict):r["note_name"]=name
        return incoming
    def run(self,owner,kind,path):
        if not path:return None
        prog=_progress(owner,"Import","Preparing import ...");prog.show()
        try:
            if not self.db.exists():self.db.ensure()
            existing=self.db.load_existing_maps()
            if kind=="db":incoming=self.db.parse_incoming_db(path,progress=prog)
            elif kind=="json":incoming=self.db.parse_incoming_json(path,progress=prog)
            elif kind=="md":incoming=self._apply_md_name(self.db.parse_incoming_markdown(path,progress=prog),path)
            else:incoming=self.db.parse_incoming_csv_zip(path,progress=prog)
            _set_prog(prog,55,"Scanning duplicates ...")
            plan=self.db.build_import_plan(incoming,existing,progress=prog)
            dups=[self.db.summarize_dup(x) for x in (plan.get("dups") or [])]
            _set_prog(prog,80,"Ready.")
        finally:
            prog.close()
        decisions={}
        if dups:
            dlg=_DupDialog(owner,"Import Duplicates",dups)
            if dlg.exec()!=QDialog.DialogCode.Accepted:return None
            decisions=dlg.decisions()
        prog=_progress(owner,"Import","Applying import ...");prog.show()
        try:
            res=self.db.apply_plan(plan,decisions,progress=prog)
            if kind=="md":
                names=[]
                rows=incoming.get("Notes") if isinstance(incoming.get("Notes"),list) else []
                for r in rows:
                    if isinstance(r,dict):
                        nm=_norm(r.get("note_name",""))
                        if nm:names.append(nm)
                if names:self.db.sync_commands_from_notes(names,progress=prog)
        finally:
            prog.close()
        return res
    def run_multi_markdown(self,owner,paths):
        if not paths:return None
        prog=_progress(owner,"Import","Loading markdown files ...");prog.show()
        try:
            if not self.db.exists():self.db.ensure()
            total=max(1,len(paths))
            totals={"added":0,"replaced":0,"overwritten":0,"skipped":0,"bad":0}
            for i,p in enumerate(paths):
                _set_prog(prog,int((i*100)/total),f"Importing {i+1}/{total}: {os.path.basename(p)}")
                incoming=self._apply_md_name(self.db.parse_incoming_markdown(p,progress=prog),p)
                existing=self.db.load_existing_maps()
                _set_prog(prog,55,"Scanning duplicates ...")
                plan=self.db.build_import_plan(incoming,existing,progress=prog)
                dups=[self.db.summarize_dup(x) for x in (plan.get("dups") or [])]
                decisions={}
                if dups:
                    dlg=_DupDialog(owner,"Import Duplicates",dups)
                    if dlg.exec()!=QDialog.DialogCode.Accepted:return None
                    decisions=dlg.decisions()
                _set_prog(prog,70,"Applying import ...")
                res=self.db.apply_plan(plan,decisions,progress=prog) or {}
                names=[]
                rows=incoming.get("Notes") if isinstance(incoming.get("Notes"),list) else []
                for r in rows:
                    if isinstance(r,dict):
                        nm=_norm(r.get("note_name",""))
                        if nm:names.append(nm)
                if names:self.db.sync_commands_from_notes(names,progress=prog)
                for k in totals.keys():
                    try:totals[k]+=int(res.get(k,0))
                    except Exception:pass
            _set_prog(prog,100,"Done.")
            return totals
        finally:
            prog.close()
class NCN_Export:
    def __init__(self,db):self.db=db
    def run(self,owner,kind,out_path):
        if not out_path:return False
        prog=_progress(owner,"Export","Exporting ...");prog.show()
        try:
            if kind=="db":
                self.db.copy_db(out_path)
            elif kind=="json":
                self.db.export_json_tables(out_path,progress=prog)
            elif kind=="md":
                self.db.export_markdown_zip(out_path,progress=prog)
            else:
                self.db.export_csv_zip(out_path,progress=prog)
            _log("[+]",f"NCN export ok ({kind}) -> {out_path}")
            return True
        except Exception as e:
            _log("[!]",f"NCN export failed ({e})")
            QMessageBox.warning(owner,"Export",f"Export failed:\n{e}")
            return False
        finally:
            prog.close()
class TagManager:
    def __init__(self,db_path=None):self.db_path=db_path or _db_path()
    def _collect(self,cur,table):
        tags={}
        try:
            cur.execute(f"SELECT tags FROM {table} WHERE tags IS NOT NULL AND TRIM(tags)<>''")
        except:return tags
        for (t,) in cur.fetchall():
            for tag in _split_tags(t):
                k=tag.lower()
                if k not in tags:tags[k]={"tag":tag,"count":0}
                tags[k]["count"]+=1
        return tags
    def load_summary(self):
        if not os.path.isfile(self.db_path):return []
        with sqlite3.connect(self.db_path,timeout=5) as con:
            cur=con.cursor()
            a=self._collect(cur,"CommandsNotes")
            b=self._collect(cur,"Commands")
        keys=set(a.keys())|set(b.keys())
        rows=[]
        for k in keys:
            tag=(a.get(k) or b.get(k) or {}).get("tag",k)
            cn=(a.get(k) or {}).get("count",0)
            cl=(b.get(k) or {}).get("count",0)
            rows.append({"tag":tag,"commands_notes":cn,"linked":cl,"total":cn+cl})
        rows.sort(key=lambda x:(-x.get("total",0),x.get("tag","").lower()))
        return rows
    def _apply_change(self,tags,mode,old_set,new_tag):
        out=[]
        newt=_norm(new_tag)
        for t in tags or []:
            tl=_norm(t).lower()
            if tl in old_set:
                if mode in ("rename","merge") and newt:out.append(newt)
            else:
                out.append(t)
        return _dedupe_tags(out)
    def _update_table(self,cur,table,mode,old_set,new_tag):
        try:cur.execute(f"SELECT id,tags FROM {table}")
        except:return 0
        changed=0
        for rid,tags in cur.fetchall():
            ntags=self._apply_change(_split_tags(tags),mode,old_set,new_tag)
            new_val=_join_tags(ntags)
            if _norm(tags)!=new_val:
                cur.execute(f"UPDATE {table} SET tags=? WHERE id=?",(new_val,rid))
                changed+=1
        return changed
    def _update_note_html(self,html_text,mode,old_set,new_tag):
        changed=[False]
        rx=re.compile(r"(&lt;C\\s*\\[)(.*?)(\\]\\s*&gt;)",re.S|re.I)
        def repl(m):
            meta=m.group(2)
            m2=re.search(r"(Tags:)(.*)$",meta,re.I|re.S)
            if not m2:return m.group(0)
            tags=_split_tags(m2.group(2))
            ntags=self._apply_change(tags,mode,old_set,new_tag)
            if ntags==tags:return m.group(0)
            new_meta=re.sub(r"(Tags:)(.*)$",r"\\1"+_join_tags(ntags),meta,flags=re.I|re.S)
            changed[0]=True
            return m.group(1)+new_meta+m.group(3)
        new_html=rx.sub(repl,html_text or "")
        return new_html,changed[0]
    def update_tags(self,mode,old_tags,new_tag,include_linked=False):
        old_set=set([_norm(t).lower() for t in (old_tags or []) if _norm(t)])
        if not old_set:return {"commands_notes":0,"linked":0,"notes":0}
        if not os.path.isfile(self.db_path):return {"commands_notes":0,"linked":0,"notes":0}
        res={"commands_notes":0,"linked":0,"notes":0}
        with sqlite3.connect(self.db_path,timeout=5) as con:
            cur=con.cursor()
            res["commands_notes"]=self._update_table(cur,"CommandsNotes",mode,old_set,new_tag)
            if include_linked:
                res["linked"]=self._update_table(cur,"Commands",mode,old_set,new_tag)
                try:
                    cur.execute("SELECT id,content FROM Notes")
                    for nid,content in cur.fetchall():
                        new_html,chg=self._update_note_html(content,mode,old_set,new_tag)
                        if chg:
                            cur.execute("UPDATE Notes SET content=? WHERE id=?",(new_html,nid))
                            res["notes"]+=1
                except:pass
            con.commit()
        return res
class _BackupPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.back=Backup()
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(8)
        top=QHBoxLayout();top.setContentsMargins(14,14,14,0);top.setSpacing(10)
        t=QLabel("Backup",self);t.setObjectName("PageTitle")
        top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(14,14,14,14);v.setSpacing(10)
        self.info=QLabel("Backups Data/ and you can Select a backup then Restore.",box);self.info.setObjectName("PageSubTitle")
        v.addWidget(self.info,0)
        self.chk_auto=QCheckBox("Enable auto backup",box)
        self.cmb_freq=QComboBox(box);self.cmb_freq.setObjectName("HomePerPage")
        self.cmb_keep=QComboBox(box);self.cmb_keep.setObjectName("HomePerPage")
        self._freq_items=[("Every 6 hours",6),("Daily",24),("Weekly",168),("Monthly",720)]
        self._keep_items=[5,10,20,50,100]
        self.cmb_freq.addItems([t[0] for t in self._freq_items])
        self.cmb_keep.addItems([f"Keep {n}" for n in self._keep_items])
        auto_row=QHBoxLayout();auto_row.setSpacing(10)
        auto_row.addWidget(self.chk_auto,0)
        auto_row.addWidget(QLabel("Frequency",box),0)
        auto_row.addWidget(self.cmb_freq,0)
        auto_row.addWidget(QLabel("Retention",box),0)
        auto_row.addWidget(self.cmb_keep,0)
        auto_row.addStretch(1)
        v.addLayout(auto_row)
        row=QHBoxLayout();row.setSpacing(10)
        self.btn_backup=QToolButton(box);self.btn_backup.setObjectName("TargetAddBtn");self.btn_backup.setText("Backup Now");self.btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore=QToolButton(box);self.btn_restore.setObjectName("TargetMiniBtn");self.btn_restore.setText("Restore");self.btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete=QToolButton(box);self.btn_delete.setObjectName("TargetMiniBtn");self.btn_delete.setText("Delete");self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_delete.setEnabled(False)
        row.addWidget(self.btn_backup,0);row.addWidget(self.btn_restore,0);row.addWidget(self.btn_delete,0);row.addStretch(1)
        v.addLayout(row)
        self.table=QTableWidget(box);self.table.setObjectName("HomeTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Backup","Modified","Size","Action"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.cellDoubleClicked.connect(lambda r,c:self._restore_selected())
        self.table.itemSelectionChanged.connect(self._on_sel)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.table,1)
        self.status=QLabel("",box);self.status.setObjectName("PageSubTitle")
        v.addWidget(self.status,0)
        root.addWidget(box,1)
        self.btn_backup.clicked.connect(self._do_backup)
        self.btn_restore.clicked.connect(self._restore_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        self._load_auto_settings()
        self.chk_auto.stateChanged.connect(self._save_auto_settings)
        self.cmb_freq.currentIndexChanged.connect(self._save_auto_settings)
        self.cmb_keep.currentIndexChanged.connect(self._save_auto_settings)
        QTimer.singleShot(0,self._render)
    def _set_status(self,s):self.status.setText(_norm(s))
    def _load_auto_settings(self):
        cfg=_get_backup_settings()
        for w in (self.chk_auto,self.cmb_freq,self.cmb_keep):
            try:w.blockSignals(True)
            except:pass
        self.chk_auto.setChecked(bool(cfg.get("auto_enabled",False)))
        iv=int(cfg.get("interval_hours",24))
        keep=int(cfg.get("keep",20))
        idx=0
        for i,(_,h) in enumerate(self._freq_items):
            if int(h)==iv:idx=i;break
        self.cmb_freq.setCurrentIndex(idx)
        idx=0
        for i,n in enumerate(self._keep_items):
            if int(n)==keep:idx=i;break
        self.cmb_keep.setCurrentIndex(idx)
        for w in (self.chk_auto,self.cmb_freq,self.cmb_keep):
            try:w.blockSignals(False)
            except:pass
    def _save_auto_settings(self,*_):
        iv=self._freq_items[self.cmb_freq.currentIndex()][1] if self._freq_items else 24
        keep=self._keep_items[self.cmb_keep.currentIndex()] if self._keep_items else 20
        cfg={"auto_enabled":self.chk_auto.isChecked(),"interval_hours":iv,"keep":keep}
        _save_backup_settings(cfg)
        self._set_status("Auto backup settings saved.")
    def _on_sel(self):
        n=len(self._selected_paths())
        self.btn_delete.setEnabled(n>=2)
    def _render(self):
        rows=self.back.list()
        self.table.setRowCount(len(rows))
        for r,(p,mt,sz) in enumerate(rows):
            name=QTableWidgetItem(os.path.basename(p));name.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft);name.setData(Qt.ItemDataRole.UserRole,p)
            mod=QTableWidgetItem(datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S"));mod.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            size=QTableWidgetItem(_fmt_size(sz));size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            x=QToolButton(self.table);x.setText("X");x.setCursor(Qt.CursorShape.PointingHandCursor);x.setFixedSize(34,30)
            x.setStyleSheet("QToolButton{background:#2a1b1b;border:1px solid #4a2b2b;color:#ff5a5a;border-radius:10px;padding:0}QToolButton:hover{background:#3a1f1f}")
            x.clicked.connect(lambda _,pp=p:self._delete_one(pp))
            self.table.setItem(r,0,name);self.table.setItem(r,1,mod);self.table.setItem(r,2,size);self.table.setCellWidget(r,3,x)
            self.table.setRowHeight(r,44)
        self.table.clearSelection()
        self._on_sel()
    def _selected_paths(self):
        out=[]
        sm=self.table.selectionModel()
        if not sm:return out
        for ix in sm.selectedRows(0):
            it=self.table.item(ix.row(),0)
            if not it:continue
            p=it.data(Qt.ItemDataRole.UserRole)
            if isinstance(p,str) and p not in out:out.append(p)
        return out
    def _choose_restore_mode(self,backup_name):
        w=self.window() if self.window() else self
        mb=QMessageBox(w);mb.setWindowTitle("Restore Backup");mb.setText(f"Restore from:\n{backup_name}\nChoose mode:")
        b1=mb.addButton("Merge",QMessageBox.ButtonRole.AcceptRole)
        b2=mb.addButton("Replace",QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()==b1:return "merge"
        if mb.clickedButton()==b2:return "replace"
        return ""
    def _restore_selected(self):
        p=""
        sel=self._selected_paths()
        if sel:p=sel[0]
        if not p:
            p,_=QFileDialog.getOpenFileName(self,"Select Backup",_backups_dir(),"Backup (*.zip)")
            if not p:return
        mode=self._choose_restore_mode(os.path.basename(p))
        if not mode:return
        prog=_progress(self,"Restore","Restoring ...");prog.show()
        try:
            ok,msg=self.back.restore(p,mode,progress=prog)
        finally:
            prog.close()
        self._set_status(msg)
        if ok:_log("[+]",f"Restore ok: {p} ({mode})")
        else:_log("[!]",f"Restore failed: {p} ({msg})")
    def _do_backup(self):
        prog=_progress(self,"Backup","Creating backup ...");prog.show()
        try:
            out=self.back.create(progress=prog)
        except Exception as e:
            prog.close()
            self._set_status(f"Backup failed: {e}")
            _log("[!]",f"Backup failed ({e})")
            return
        finally:
            try:prog.close()
            except:pass
        self._set_status(f"Created: {os.path.basename(out)}")
        _log("[+]",f"Backup created: {out}")
        self._render()
    def _delete_one(self,p):
        if not p or not os.path.isfile(p):return
        mb=QMessageBox(self);mb.setWindowTitle("Delete Backup");mb.setText(f"Delete this backup?\n\n{os.path.basename(p)}")
        bdel=mb.addButton("Delete",QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()!=bdel:return
        ok,bad=self.back.delete([p])
        self._set_status(f"Deleted: {ok} | Failed: {bad}")
        _log("[+]",f"Backup row deleted ok={ok} bad={bad}")
        self._render()
    def _delete_selected(self):
        paths=self._selected_paths()
        if len(paths)<2:return
        mb=QMessageBox(self);mb.setWindowTitle("Delete Backups");mb.setText(f"Delete selected backups?\n\n{len(paths)} file(s)")
        bdel=mb.addButton("Delete",QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()!=bdel:return
        ok,bad=self.back.delete(paths)
        self._set_status(f"Deleted: {ok} | Failed: {bad}")
        _log("[+]",f"Backups deleted ok={ok} bad={bad}")
        self._render()
class _ImportExportPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.db=Note_LOYA_Database()
        self.ncn_imp=NCN_Import(self.db)
        self.ncn_exp=NCN_Export(self.db)
        self.tv=TargetValues()
        self.tg=Targets()
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,14,14,0);top.setSpacing(10)
        t=QLabel("Import & Export",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(14,14,14,14);v.setSpacing(8)
        r1=QHBoxLayout();r1.setSpacing(8)
        lbl1=QLabel("Notes & Commands Notes",box);lbl1.setObjectName("PageSubTitle")
        self.btn_ncn_imp=QToolButton(box);self.btn_ncn_imp.setObjectName("TargetAddBtn");self.btn_ncn_imp.setText("Import");self.btn_ncn_imp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_ncn_exp=QToolButton(box);self.btn_ncn_exp.setObjectName("TargetMiniBtn");self.btn_ncn_exp.setText("Export");self.btn_ncn_exp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mi=QMenu(self.btn_ncn_imp)
        a=QAction("From Database (.db)",self);a.triggered.connect(lambda:self._ncn_import("db"));mi.addAction(a)
        a=QAction("From JSON (.json)",self);a.triggered.connect(lambda:self._ncn_import("json"));mi.addAction(a)
        a=QAction("From CSV (.zip/.csv)",self);a.triggered.connect(lambda:self._ncn_import("csv"));mi.addAction(a)
        a=QAction("From Markdown (.md)",self);a.triggered.connect(lambda:self._ncn_import("md"));mi.addAction(a)
        me=QMenu(self.btn_ncn_exp)
        a=QAction("To Database (.db)",self);a.triggered.connect(lambda:self._ncn_export("db"));me.addAction(a)
        a=QAction("To JSON (.json)",self);a.triggered.connect(lambda:self._ncn_export("json"));me.addAction(a)
        a=QAction("To CSV (.zip)",self);a.triggered.connect(lambda:self._ncn_export("csv"));me.addAction(a)
        a=QAction("To Markdown (.zip)",self);a.triggered.connect(lambda:self._ncn_export("md"));me.addAction(a)
        self.btn_ncn_imp.setMenu(mi);self.btn_ncn_exp.setMenu(me)
        r1.addWidget(lbl1,1);r1.addWidget(self.btn_ncn_imp,0);r1.addWidget(self.btn_ncn_exp,0)
        self.ncn_status=QLabel("",box);self.ncn_status.setObjectName("PageSubTitle")
        r1b=QHBoxLayout();r1b.setSpacing(8)
        lbl1b=QLabel("Notes Exporting",box);lbl1b.setObjectName("PageSubTitle")
        self.btn_note_exp=QToolButton(box);self.btn_note_exp.setObjectName("TargetMiniBtn");self.btn_note_exp.setText("Export");self.btn_note_exp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        me=QMenu(self.btn_note_exp)
        a=QAction("To Markdown (.md)",self);a.triggered.connect(lambda:self._notes_export("md"));me.addAction(a)
        a=QAction("To Human Markdown (.md)",self);a.triggered.connect(lambda:self._notes_export("md_human"));me.addAction(a)
        a=QAction("To HTML (.html)",self);a.triggered.connect(lambda:self._notes_export("html"));me.addAction(a)
        self.btn_note_exp.setMenu(me)
        r1b.addWidget(lbl1b,1);r1b.addWidget(self.btn_note_exp,0)
        self.note_status=QLabel("",box);self.note_status.setObjectName("PageSubTitle")
        r2=QHBoxLayout();r2.setSpacing(8)
        lbl2=QLabel("Target Values",box);lbl2.setObjectName("PageSubTitle")
        self.btn_tv_imp=QToolButton(box);self.btn_tv_imp.setObjectName("TargetAddBtn");self.btn_tv_imp.setText("Import");self.btn_tv_imp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_tv_exp=QToolButton(box);self.btn_tv_exp.setObjectName("TargetMiniBtn");self.btn_tv_exp.setText("Export");self.btn_tv_exp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mi=QMenu(self.btn_tv_imp)
        a=QAction("From JSON (.json)",self);a.triggered.connect(lambda:self._tv_import("json"));mi.addAction(a)
        a=QAction("From CSV (.csv)",self);a.triggered.connect(lambda:self._tv_import("csv"));mi.addAction(a)
        me=QMenu(self.btn_tv_exp)
        a=QAction("To JSON (.json)",self);a.triggered.connect(lambda:self._tv_export("json"));me.addAction(a)
        a=QAction("To CSV (.csv)",self);a.triggered.connect(lambda:self._tv_export("csv"));me.addAction(a)
        self.btn_tv_imp.setMenu(mi);self.btn_tv_exp.setMenu(me)
        r2.addWidget(lbl2,1);r2.addWidget(self.btn_tv_imp,0);r2.addWidget(self.btn_tv_exp,0)
        self.tv_status=QLabel("",box);self.tv_status.setObjectName("PageSubTitle")
        r3=QHBoxLayout();r3.setSpacing(8)
        lbl3=QLabel("Targets",box);lbl3.setObjectName("PageSubTitle")
        self.btn_tg_imp=QToolButton(box);self.btn_tg_imp.setObjectName("TargetAddBtn");self.btn_tg_imp.setText("Import");self.btn_tg_imp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_tg_exp=QToolButton(box);self.btn_tg_exp.setObjectName("TargetMiniBtn");self.btn_tg_exp.setText("Export");self.btn_tg_exp.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mi=QMenu(self.btn_tg_imp)
        a=QAction("From JSON (.json)",self);a.triggered.connect(lambda:self._tg_import());mi.addAction(a)
        me=QMenu(self.btn_tg_exp)
        a=QAction("To JSON (.json)",self);a.triggered.connect(lambda:self._tg_export());me.addAction(a)
        self.btn_tg_imp.setMenu(mi);self.btn_tg_exp.setMenu(me)
        r3.addWidget(lbl3,1);r3.addWidget(self.btn_tg_imp,0);r3.addWidget(self.btn_tg_exp,0)
        self.tg_status=QLabel("",box);self.tg_status.setObjectName("PageSubTitle")
        r4=QHBoxLayout();r4.setSpacing(8)
        lbl4=QLabel("LOYA Output",box);lbl4.setObjectName("PageSubTitle")
        self.chk_structured=QCheckBox("Structured output (JSON)",box)
        r4.addWidget(lbl4,1);r4.addWidget(self.chk_structured,0)
        self.output_status=QLabel("",box);self.output_status.setObjectName("PageSubTitle")
        v.addLayout(r1,0);v.addWidget(self.ncn_status,0)
        v.addLayout(r1b,0);v.addWidget(self.note_status,0)
        v.addLayout(r2,0);v.addWidget(self.tv_status,0)
        v.addLayout(r3,0);v.addWidget(self.tg_status,0)
        v.addLayout(r4,0);v.addWidget(self.output_status,0)
        v.addStretch(1)
        root.addWidget(box,1)
        self.chk_structured.stateChanged.connect(self._toggle_structured_output)
        QTimer.singleShot(0,self._load_output_settings)
    def _ensure_db(self):
        try:self.db.ensure();return True
        except Exception as e:
            QMessageBox.warning(self,"Database",f"Database error:\n{e}")
            return False
    def _load_output_settings(self):
        cfg=_get_chat_output_settings()
        try:self.chk_structured.blockSignals(True)
        except:pass
        self.chk_structured.setChecked(bool(cfg.get("structured_output",False)))
        try:self.chk_structured.blockSignals(False)
        except:pass
        self._set_output_status(cfg)
    def _set_output_status(self,cfg):
        self.output_status.setText("Structured output: On" if cfg.get("structured_output") else "Structured output: Off")
    def _toggle_structured_output(self,_):
        cfg={"structured_output":bool(self.chk_structured.isChecked())}
        _save_chat_output_settings(cfg)
        self._set_output_status(cfg)
    def _ncn_import(self,kind):
        if not self._ensure_db():return
        flt={"db":"Database (*.db)","json":"JSON (*.json)","csv":"CSV Bundle (*.zip);;CSV (*.csv);;ZIP (*.zip)","md":"Markdown (*.md)"}[kind]
        if kind=="md":
            paths,_=QFileDialog.getOpenFileNames(self,"Import Notes & Commands Notes",_abs(".."),flt)
            if not paths:return
            try:
                res=self.ncn_imp.run_multi_markdown(self,paths)
                if not res:
                    self.ncn_status.setText("Import cancelled.")
                    return
                self.ncn_status.setText(f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)} bad:{res.get('bad',0)}")
                _log("[+]",f"NCN import ok {res}")
            except Exception as e:
                self.ncn_status.setText(f"Import failed: {e}")
                _log("[!]",f"NCN import failed ({e})")
            return
        p,_=QFileDialog.getOpenFileName(self,"Import Notes & Commands Notes",_abs(".."),flt)
        if not p:return
        try:
            res=self.ncn_imp.run(self,kind,p)
            if not res:
                self.ncn_status.setText("Import cancelled.")
                return
            self.ncn_status.setText(f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)} bad:{res.get('bad',0)}")
            _log("[+]",f"NCN import ok {res}")
        except Exception as e:
            self.ncn_status.setText(f"Import failed: {e}")
            _log("[!]",f"NCN import failed ({e})")
    def _ncn_export(self,kind):
        if not self._ensure_db():return
        base=_abs("..")
        if kind=="db":
            p,_=QFileDialog.getSaveFileName(self,"Export Database",os.path.join(base,f"Note_LOYA_export_{_now()}.db"),"Database (*.db)")
        elif kind=="json":
            p,_=QFileDialog.getSaveFileName(self,"Export JSON",os.path.join(base,f"Note_LOYA_export_{_now()}.json"),"JSON (*.json)")
        elif kind=="md":
            p,_=QFileDialog.getSaveFileName(self,"Export Markdown",os.path.join(base,f"Note_LOYA_export_{_now()}.zip"),"ZIP (*.zip)")
        else:
            p,_=QFileDialog.getSaveFileName(self,"Export CSV",os.path.join(base,f"Note_LOYA_export_{_now()}.zip"),"ZIP (*.zip)")
        if not p:return
        ok=self.ncn_exp.run(self,kind,p)
        if ok:self.ncn_status.setText(f"Exported: {os.path.basename(p)}")
    def _notes_export(self,kind):
        if not self._ensure_db():return
        names=self.db.list_note_names()
        if not names:
            QMessageBox.information(self,"Notes Export","No notes found.")
            return
        name,ok=QInputDialog.getItem(self,"Export Note","Note",names,0,False)
        if not ok or not name:return
        base=_abs("..")
        safe=_safe_filename(name,fallback="note")
        if kind=="md":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (Markdown)",os.path.join(base,f"{safe}.md"),"Markdown (*.md)")
            if not p:return
            try:
                self.db.export_note_markdown(name,p)
                self.note_status.setText(f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export markdown -> {p}")
            except Exception as e:
                self.note_status.setText(f"Export failed: {e}")
                _log("[!]",f"Note export markdown failed ({e})")
                QMessageBox.warning(self,"Export",f"Export failed:\n{e}")
        elif kind=="md_human":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (Human Markdown)",os.path.join(base,f"{safe}.md"),"Markdown (*.md)")
            if not p:return
            try:
                self.db.export_note_markdown_human(name,p)
                self.note_status.setText(f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export human markdown -> {p}")
            except Exception as e:
                self.note_status.setText(f"Export failed: {e}")
                _log("[!]",f"Note export human markdown failed ({e})")
                QMessageBox.warning(self,"Export",f"Export failed:\n{e}")
        elif kind=="html":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (HTML)",os.path.join(base,f"{safe}.html"),"HTML (*.html)")
            if not p:return
            try:
                self.db.export_note_html(name,p)
                self.note_status.setText(f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export html -> {p}")
            except Exception as e:
                self.note_status.setText(f"Export failed: {e}")
                _log("[!]",f"Note export html failed ({e})")
                QMessageBox.warning(self,"Export",f"Export failed:\n{e}")
    def _tv_import(self,kind):
        flt={"json":"JSON (*.json)","csv":"CSV (*.csv)"}[kind]
        p,_=QFileDialog.getOpenFileName(self,"Import Target Values",_abs(".."),flt)
        if not p:return
        base=self.tv.load()
        prog=_progress(self,"Import","Loading ...");prog.show()
        try:
            incoming=self.tv.parse_json(p) if kind=="json" else self.tv.parse_csv(p)
            plan=self.tv.build_plan(incoming,base)
            dups=[{"table":"TargetValues","key":_norm(d.get("key","")),"existing":f'{_norm(d.get("existing_key",""))}:{int((d.get("existing") or {}).get("priority",(d.get("existing") or {}).get("value",0)) or 0)}',"incoming":f'{_norm(d.get("key",""))}:{int((d.get("incoming") or {}).get("priority",(d.get("incoming") or {}).get("value",0)) or 0)}',"in_cmd":""} for d in (plan.get("dups") or [])]
        finally:
            prog.close()
        decisions={}
        if dups:
            dlg=_DupDialog(self,"Target Values Duplicates",dups)
            if dlg.exec()!=QDialog.DialogCode.Accepted:
                self.tv_status.setText("Import cancelled.")
                return
            decisions=dlg.decisions()
        res=self.tv.apply_plan(base,plan,decisions)
        self.tv.save(base)
        self.tv_status.setText(f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)}")
        _log("[+]",f"TargetValues import ok {res}")
    def _tv_export(self,kind):
        data=self.tv.load()
        if kind=="json":
            p,_=QFileDialog.getSaveFileName(self,"Export Target Values",os.path.join(_abs(".."),f"target_values_{_now()}.json"),"JSON (*.json)")
            if not p:return
            self.tv.export_json(p,data)
        else:
            p,_=QFileDialog.getSaveFileName(self,"Export Target Values",os.path.join(_abs(".."),f"target_values_{_now()}.csv"),"CSV (*.csv)")
            if not p:return
            self.tv.export_csv(p,data)
        self.tv_status.setText(f"Exported: {os.path.basename(p)}")
        _log("[+]",f"TargetValues export ok ({kind}) -> {p}")
    def _tg_import(self):
        p,_=QFileDialog.getOpenFileName(self,"Import Targets",_abs(".."),"JSON (*.json)")
        if not p:return
        base=self.tg.load()
        prog=_progress(self,"Import","Loading ...");prog.show()
        try:
            incoming=self.tg.parse_json(p)
            plan=self.tg.build_plan(incoming,base)
            dups=[{"table":"Targets","key":_norm(d.get("key","")),"existing":self.tg._summ(d.get("existing")),"incoming":self.tg._summ(d.get("incoming")),"in_cmd":""} for d in (plan.get("dups") or [])]
        finally:
            prog.close()
        decisions={}
        if dups:
            dlg=_DupDialog(self,"Targets Duplicates",dups)
            if dlg.exec()!=QDialog.DialogCode.Accepted:
                self.tg_status.setText("Import cancelled.")
                return
            decisions=dlg.decisions()
        base,res=self.tg.apply_plan(base,plan,decisions)
        self.tg.save(base)
        self.tg_status.setText(f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)}")
        _log("[+]",f"Targets import ok {res}")
    def _tg_export(self):
        data=self.tg.load()
        p,_=QFileDialog.getSaveFileName(self,"Export Targets",os.path.join(_abs(".."),f"Targets_{_now()}.json"),"JSON (*.json)")
        if not p:return
        self.tg.export_json(p,data)
        self.tg_status.setText(f"Exported: {os.path.basename(p)}")
        _log("[+]",f"Targets export ok -> {p}")
class _TagsPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.tm=TagManager()
        self._rows=[]
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(8)
        top=QHBoxLayout();top.setContentsMargins(14,14,14,0);top.setSpacing(10)
        t=QLabel("Tag Manager",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(14,14,14,14);v.setSpacing(8)
        row1=QHBoxLayout();row1.setSpacing(8)
        self.search=QLineEdit(box);self.search.setObjectName("TargetSearch");self.search.setPlaceholderText("Search tags...")
        self.btn_refresh=QToolButton(box);self.btn_refresh.setObjectName("TargetMiniBtn");self.btn_refresh.setText("Refresh")
        row1.addWidget(self.search,1);row1.addWidget(self.btn_refresh,0)
        v.addLayout(row1)
        row2=QHBoxLayout();row2.setSpacing(8)
        row3=QHBoxLayout();row3.setSpacing(10)
        self.in_new=QLineEdit(box);self.in_new.setObjectName("TargetKeyInput");self.in_new.setPlaceholderText("New tag name")
        self.btn_rename=QToolButton(box);self.btn_rename.setObjectName("TargetAddBtn");self.btn_rename.setText("Rename")
        self.btn_merge=QToolButton(box);self.btn_merge.setObjectName("TargetMiniBtn");self.btn_merge.setText("Merge")
        self.btn_delete=QToolButton(box);self.btn_delete.setObjectName("TargetMiniBtn");self.btn_delete.setText("Delete")
        self.chk_linked=QCheckBox("Include linked commands (Notes)",box);self.chk_linked.setChecked(True)
        row2.addWidget(self.in_new,1);row2.addWidget(self.btn_rename,0);row2.addWidget(self.btn_merge,0);row2.addWidget(self.btn_delete,0);row2.addStretch(1)
        row3.addWidget(self.chk_linked,0);row3.addStretch(1)
        v.addLayout(row2)
        v.addLayout(row3)
        self.table=QTableWidget(box);self.table.setObjectName("HomeTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tag","Commands Notes","Linked","Total"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.table,1)
        self.status=QLabel("",box);self.status.setObjectName("PageSubTitle")
        v.addWidget(self.status,0)
        root.addWidget(box,1)
        self.search.textChanged.connect(self._render)
        self.btn_refresh.clicked.connect(self._load)
        self.btn_rename.clicked.connect(self._do_rename)
        self.btn_merge.clicked.connect(self._do_merge)
        self.btn_delete.clicked.connect(self._do_delete)
        QTimer.singleShot(0,self._load)
    def _set_status(self,msg):self.status.setText(_norm(msg))
    def _load(self):
        self._rows=self.tm.load_summary()
        self._render()
    def _render(self,*_):
        q=_norm(self.search.text()).lower()
        rows=[r for r in self._rows if not q or q in _norm(r.get("tag","")).lower()]
        self.table.setRowCount(len(rows))
        for r,it in enumerate(rows):
            tag=_norm(it.get("tag",""))
            cn=str(int(it.get("commands_notes",0)))
            cl=str(int(it.get("linked",0)))
            tot=str(int(it.get("total",0)))
            self._set_item(r,0,tag,tag,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,True)
            self._set_item(r,1,cn,None,Qt.AlignmentFlag.AlignCenter,False)
            self._set_item(r,2,cl,None,Qt.AlignmentFlag.AlignCenter,False)
            self._set_item(r,3,tot,None,Qt.AlignmentFlag.AlignCenter,False)
            self.table.setRowHeight(r,40)
        self.table.clearSelection()
    def _set_item(self,row,col,text,full=None,align=None,bold=False):
        it=QTableWidgetItem(text)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
        if align is not None:it.setTextAlignment(align)
        if bold:
            f=it.font();f.setBold(True);f.setWeight(800);it.setFont(f)
        if full is not None:it.setData(Qt.ItemDataRole.UserRole,full)
        self.table.setItem(row,col,it)
    def _selected_tags(self):
        out=[]
        sm=self.table.selectionModel()
        if not sm:return out
        for ix in sm.selectedRows(0):
            it=self.table.item(ix.row(),0)
            if not it:continue
            t=it.data(Qt.ItemDataRole.UserRole)
            if isinstance(t,str) and t not in out:out.append(t)
        return out
    def _confirm(self,msg):
        mb=QMessageBox(self);mb.setWindowTitle("Tag Manager");mb.setText(msg)
        bok=mb.addButton("Apply",QMessageBox.ButtonRole.AcceptRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        return mb.clickedButton()==bok
    def _apply_change(self,mode):
        tags=self._selected_tags()
        if not tags:
            QMessageBox.warning(self,"Tags","Select at least one tag.")
            return
        new_tag=_norm(self.in_new.text())
        if mode=="rename" and len(tags)!=1:
            QMessageBox.warning(self,"Rename","Select exactly one tag to rename.")
            return
        if mode=="merge" and len(tags)<2:
            QMessageBox.warning(self,"Merge","Select two or more tags to merge.")
            return
        if mode in ("rename","merge") and not new_tag:
            QMessageBox.warning(self,"Tag","New tag name is required.")
            return
        if mode=="rename" and _norm(tags[0]).lower()==new_tag.lower():
            QMessageBox.information(self,"Rename","New tag matches the old tag.")
            return
        include_linked=self.chk_linked.isChecked()
        msg=f"{mode.title()} tag(s): {', '.join(tags)}"
        if mode in ("rename","merge"):msg+=f" -> {new_tag}"
        if include_linked:msg+="\n\nThis will update linked commands and note content."
        if not self._confirm(msg):return
        res=self.tm.update_tags(mode,tags,new_tag,include_linked=include_linked)
        self._set_status(f"Updated CommandsNotes:{res.get('commands_notes',0)} Linked:{res.get('linked',0)} Notes:{res.get('notes',0)}")
        self._load()
    def _do_rename(self):self._apply_change("rename")
    def _do_merge(self):self._apply_change("merge")
    def _do_delete(self):self._apply_change("delete")
class _SecurityPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,14,14,0);top.setSpacing(10)
        t=QLabel("Security",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(14,14,14,14);v.setSpacing(10)
        info=QLabel("Protect access and encrypt the database at rest.",box);info.setObjectName("PageSubTitle")
        v.addWidget(info,0)
        row1=QHBoxLayout();row1.setSpacing(10)
        self.chk_lock=QCheckBox("Enable app lock on start",box)
        self.btn_set_pin=QToolButton(box);self.btn_set_pin.setObjectName("TargetAddBtn");self.btn_set_pin.setText("Set/Change PIN")
        row1.addWidget(self.chk_lock,0);row1.addWidget(self.btn_set_pin,0);row1.addStretch(1)
        v.addLayout(row1)
        self.pin_status=QLabel("",box);self.pin_status.setObjectName("PageSubTitle")
        v.addWidget(self.pin_status,0)
        row2=QHBoxLayout();row2.setSpacing(10)
        self.chk_enc=QCheckBox("Enable database encryption (at rest)",box)
        row2.addWidget(self.chk_enc,0);row2.addStretch(1)
        v.addLayout(row2)
        self.enc_status=QLabel("",box);self.enc_status.setObjectName("PageSubTitle")
        v.addWidget(self.enc_status,0)
        self.status=QLabel("",box);self.status.setObjectName("PageSubTitle")
        v.addWidget(self.status,0)
        root.addWidget(box,1)
        self.btn_set_pin.clicked.connect(self._set_pin)
        self.chk_lock.stateChanged.connect(self._toggle_lock)
        self.chk_enc.stateChanged.connect(self._toggle_enc)
        QTimer.singleShot(0,self._load)
    def _set_status(self,msg):self.status.setText(_norm(msg))
    def _load(self):
        cfg=_get_security_settings()
        for w in (self.chk_lock,self.chk_enc):
            try:w.blockSignals(True)
            except:pass
        self.chk_lock.setChecked(bool(cfg.get("app_lock_enabled",False)))
        self.chk_enc.setChecked(bool(cfg.get("enc_enabled",False)))
        for w in (self.chk_lock,self.chk_enc):
            try:w.blockSignals(False)
            except:pass
        self._set_pin_status(cfg)
        self._set_enc_status(cfg)
    def _set_pin_status(self,cfg):
        self.pin_status.setText("PIN: Set" if _pin_is_set(cfg) else "PIN: Not set")
    def _set_enc_status(self,cfg):
        encp=_enc_path()
        if cfg.get("enc_enabled") and os.path.isfile(encp):
            self.enc_status.setText(f"Encrypted file: {os.path.basename(encp)}")
        elif cfg.get("enc_enabled"):
            self.enc_status.setText("Encrypted file: Missing (will create on exit)")
        else:
            self.enc_status.setText("Encryption: Off")
    def _set_pin(self):
        cfg=_get_security_settings()
        if _pin_is_set(cfg):
            cur=_prompt_pin(self,"Verify PIN","Enter current PIN.")
            if cur is None:return
            if not _verify_pin(cur,cfg):
                QMessageBox.warning(self,"PIN","Wrong PIN.")
                return
        new_pin=_prompt_new_pin(self,"Set PIN","Enter a new PIN.")
        if not new_pin:return
        salt,phash=_hash_pin(new_pin)
        _save_security_settings({"pin_salt":salt,"pin_hash":phash})
        _set_session_pin(new_pin)
        cfg=_get_security_settings()
        if cfg.get("enc_enabled"):
            if not _HAS_CRYPTO:
                QMessageBox.warning(self,"Encryption","cryptography is not installed.")
            else:
                if not cfg.get("enc_salt"):
                    _save_security_settings({"enc_salt":base64.b64encode(os.urandom(16)).decode("ascii")})
                    cfg=_get_security_settings()
                ok,msg=_encrypt_db_file(new_pin,cfg.get("enc_salt","")) if os.path.isfile(_db_path()) else (True,"Encryption updated.")
                if not ok:QMessageBox.warning(self,"Encryption",msg)
        self._set_status("PIN updated.")
        self._load()
    def _toggle_lock(self,_):
        cfg=_get_security_settings()
        if self.chk_lock.isChecked():
            if not _pin_is_set(cfg):
                new_pin=_prompt_new_pin(self,"Set PIN","PIN is required to enable app lock.")
                if not new_pin:
                    self.chk_lock.blockSignals(True);self.chk_lock.setChecked(False);self.chk_lock.blockSignals(False)
                    return
                salt,phash=_hash_pin(new_pin)
                _save_security_settings({"pin_salt":salt,"pin_hash":phash})
                _set_session_pin(new_pin)
            _save_security_settings({"app_lock_enabled":True})
            self._set_status("App lock enabled.")
        else:
            _save_security_settings({"app_lock_enabled":False})
            self._set_status("App lock disabled.")
        self._load()
    def _toggle_enc(self,_):
        cfg=_get_security_settings()
        if self.chk_enc.isChecked():
            if not _HAS_CRYPTO:
                QMessageBox.warning(self,"Encryption","cryptography is not installed.")
                self.chk_enc.blockSignals(True);self.chk_enc.setChecked(False);self.chk_enc.blockSignals(False)
                return
            if not _pin_is_set(cfg):
                new_pin=_prompt_new_pin(self,"Set PIN","PIN is required for encryption.")
                if not new_pin:
                    self.chk_enc.blockSignals(True);self.chk_enc.setChecked(False);self.chk_enc.blockSignals(False)
                    return
                salt,phash=_hash_pin(new_pin)
                _save_security_settings({"pin_salt":salt,"pin_hash":phash})
                _set_session_pin(new_pin)
                cfg=_get_security_settings()
            if not cfg.get("enc_salt"):
                _save_security_settings({"enc_salt":base64.b64encode(os.urandom(16)).decode("ascii")})
                cfg=_get_security_settings()
            pin=_SESSION_PIN or _prompt_pin(self,"Encrypt","Enter PIN to enable encryption.")
            if not pin or not _verify_pin(pin,cfg):
                QMessageBox.warning(self,"Encryption","Wrong PIN.")
                self.chk_enc.blockSignals(True);self.chk_enc.setChecked(False);self.chk_enc.blockSignals(False)
                return
            _set_session_pin(pin)
            _save_security_settings({"enc_enabled":True})
            if os.path.isfile(_db_path()):
                ok,msg=_encrypt_db_file(pin,cfg.get("enc_salt",""))
                if not ok:
                    QMessageBox.warning(self,"Encryption",msg)
                    self.chk_enc.blockSignals(True);self.chk_enc.setChecked(False);self.chk_enc.blockSignals(False)
                    _save_security_settings({"enc_enabled":False})
                    return
                self._set_status(msg)
            else:
                self._set_status("Encryption enabled. No database yet.")
        else:
            if cfg.get("enc_enabled"):
                pin=_SESSION_PIN or _prompt_pin(self,"Disable Encryption","Enter PIN to disable encryption.")
                if not pin or not _verify_pin(pin,cfg):
                    QMessageBox.warning(self,"Encryption","Wrong PIN.")
                    self.chk_enc.blockSignals(True);self.chk_enc.setChecked(True);self.chk_enc.blockSignals(False)
                    return
                _set_session_pin(pin)
            _save_security_settings({"enc_enabled":False})
            try:
                if os.path.isfile(_enc_path()):os.remove(_enc_path())
            except Exception as e:
                QMessageBox.warning(self,"Encryption",f"Failed to remove encrypted file:\n{e}")
            self._set_status("Encryption disabled.")
        self._load()
class Widget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        root=QHBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(10)
        self.sidebar=QFrame(self);self.sidebar.setObjectName("SideBar")
        sv=QVBoxLayout(self.sidebar);sv.setContentsMargins(10,10,10,10);sv.setSpacing(10)
        self.btn_backup=QToolButton(self.sidebar);self.btn_backup.setObjectName("NavBtn");self.btn_backup.setText("Backup");self.btn_backup.setCheckable(True)
        self.btn_ie=QToolButton(self.sidebar);self.btn_ie.setObjectName("NavBtn");self.btn_ie.setText("Import & Export");self.btn_ie.setCheckable(True)
        self.btn_tags=QToolButton(self.sidebar);self.btn_tags.setObjectName("NavBtn");self.btn_tags.setText("Tags");self.btn_tags.setCheckable(True)
        self.btn_security=QToolButton(self.sidebar);self.btn_security.setObjectName("NavBtn");self.btn_security.setText("Security");self.btn_security.setCheckable(True)
        self.btn_backup.clicked.connect(lambda:self._nav(0))
        self.btn_ie.clicked.connect(lambda:self._nav(1))
        self.btn_tags.clicked.connect(lambda:self._nav(2))
        self.btn_security.clicked.connect(lambda:self._nav(3))
        sv.addWidget(self.btn_backup,0);sv.addWidget(self.btn_ie,0);sv.addWidget(self.btn_tags,0);sv.addWidget(self.btn_security,0);sv.addStretch(1)
        self.stack=QStackedWidget(self);self.stack.setObjectName("Stack")
        self.page_backup=_BackupPage(self.stack)
        self.page_ie=_ImportExportPage(self.stack)
        self.page_tags=_TagsPage(self.stack)
        self.page_security=_SecurityPage(self.stack)
        self.stack.addWidget(self.page_backup);self.stack.addWidget(self.page_ie);self.stack.addWidget(self.page_tags);self.stack.addWidget(self.page_security)
        self.scroll=QScrollArea(self);self.scroll.setObjectName("SettingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.stack)
        root.addWidget(self.sidebar,0);root.addWidget(self.scroll,1)
        QTimer.singleShot(0,self._sync_button_sizes)
        self._nav(0)
    def _nav(self,i):
        self.btn_backup.blockSignals(True);self.btn_ie.blockSignals(True);self.btn_tags.blockSignals(True);self.btn_security.blockSignals(True)
        self.btn_backup.setChecked(i==0);self.btn_ie.setChecked(i==1);self.btn_tags.setChecked(i==2);self.btn_security.setChecked(i==3)
        self.btn_backup.blockSignals(False);self.btn_ie.blockSignals(False);self.btn_tags.blockSignals(False);self.btn_security.blockSignals(False)
        self.stack.setCurrentIndex(i)
    def _sync_button_sizes(self):
        nav=[b for b in self.findChildren(QToolButton) if b.objectName()=="NavBtn" and _norm(b.text())]
        act=[b for b in self.findChildren(QToolButton) if b.objectName() in ("TargetAddBtn","TargetMiniBtn","TargetSaveBtn","TargetCancelBtn") and _norm(b.text())]
        if nav:
            fm=QFontMetrics(nav[0].font());w=max(fm.horizontalAdvance(_norm(b.text())) for b in nav)+40
            if w<170:w=170
            for b in nav:b.setFixedHeight(44);b.setFixedWidth(w)
        if act:
            fm=QFontMetrics(act[0].font());w=max(fm.horizontalAdvance(_norm(b.text())) for b in act)+40
            if w<160:w=160
            for b in act:b.setFixedHeight(30);b.setFixedWidth(w)
