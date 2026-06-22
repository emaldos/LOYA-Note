import os,sqlite3,json,csv,zipfile,shutil,tempfile,logging,re,time,base64,hashlib,hmac,html,sys,subprocess,importlib.util
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QTimer,QEvent
from PyQt6.QtGui import QAction,QFontMetrics,QTextDocument,QColor,QPageSize
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QToolButton,QStackedWidget,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QComboBox,QDialog,QFileDialog,QMessageBox,QMenu,QProgressBar,QCheckBox,QApplication,QLineEdit,QInputDialog,QScrollArea,QGridLayout,QTabWidget
from Cores.Update import GITHUB_RELEASES_API_URL as _UP_MANIFEST_URL
from Cores.Update import OFFICIAL_SOURCE_REPO as _UP_REPO_URL
from Cores import common_db as _common_db
from Cores import note_refs as _note_refs
from Cores.Update import backup_restore as _update_backup
from Cores.Update import check_for_updates as _check_for_updates
from Cores.Update import compare_semver as _compare_update_versions
from Cores.Update import get_app_identity as _get_app_identity
from Cores.Update import get_update_state as _get_update_state
from Cores.Update import list_code_snapshots as _list_code_snapshots
from Cores.Update import old_versions_dir as _old_versions_dir
from Cores.Update import start_update_install as _start_update_install
from Cores.Update import health_check as _health_check
from Cores import recycle_bin as _recycle_bin
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
    d=_health_check.logs_dir();os.makedirs(d,exist_ok=True)
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
def _data_dir():d=_health_check.data_dir();os.makedirs(d,exist_ok=True);return d
def _backups_dir():d=_health_check.backups_dir();os.makedirs(d,exist_ok=True);return d
def _db_path():return _common_db.db_path()
DB_SCHEMA_VERSION=_common_db.DB_SCHEMA_VERSION
def _targets_values_path():return _health_check.target_values_path()
def _targets_path():return _health_check.targets_path()
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
def _settings_path():return _health_check.settings_path()
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
def _get_update_settings():
    d=_read_settings()
    u=d.get("update",{}) if isinstance(d,dict) else {}
    try:hrs=int(u.get("check_interval_hours",24))
    except:hrs=24
    repo=_norm(u.get("repo_url",_UP_REPO_URL)) or _UP_REPO_URL
    manifest=_norm(u.get("manifest_url",_UP_MANIFEST_URL)) or _UP_MANIFEST_URL
    channel=_norm(u.get("last_channel","stable")) or "stable"
    return {"auto_enabled":bool(u.get("auto_enabled",False)),"check_interval_hours":max(1,hrs),"repo_url":_UP_REPO_URL if repo!=_UP_REPO_URL else repo,"manifest_url":_UP_MANIFEST_URL if manifest!=_UP_MANIFEST_URL else manifest,"last_checked":_norm(u.get("last_checked","")),"last_channel":channel}
def _save_update_settings(cfg):
    d=_read_settings()
    if not isinstance(d,dict):d={}
    cur=d.get("update",{}) if isinstance(d.get("update",{}),dict) else {}
    cur.update({"auto_enabled":bool(cfg.get("auto_enabled",False)),"check_interval_hours":max(1,_to_int(cfg.get("check_interval_hours",24),24)),"repo_url":_UP_REPO_URL,"manifest_url":_UP_MANIFEST_URL,"last_checked":_norm(cfg.get("last_checked","")),"last_channel":_norm(cfg.get("last_channel","stable")) or "stable"})
    d["update"]=cur
    return _write_settings(d)
def _sync_update_settings_from_state(state=None):
    cfg=_get_update_settings()
    st=state if isinstance(state,dict) else {}
    cfg["repo_url"]=_UP_REPO_URL
    cfg["manifest_url"]=_UP_MANIFEST_URL
    if st.get("last_checked"):cfg["last_checked"]=_norm(st.get("last_checked",""))
    if st.get("source_tag"):cfg["last_channel"]="stable"
    _save_update_settings(cfg)
    return cfg
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
_CMD_ANCHOR_COPY="cmdcopy:"
_CMD_IMG_PREFIX="cmdcard:"
_CMD_TOKEN_RX=re.compile(r"(?:cmdedit:|cmddelete:|cmdcopy:|cmdcard:)([A-Za-z0-9_-]+)",re.I)
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
def _cmd_token_from_block(block):
    m=_CMD_TOKEN_RX.search(block or "")
    return m.group(1) if m else ""
def _cmd_export_from_block(block,copy_button=True):
    token=_cmd_token_from_block(block)
    if not token:return block
    data=_decode_cmd_token(token)
    cmd=(data.get("command","") or "").rstrip()
    if not _norm(cmd):return block
    esc=_html_escape(cmd)
    align=_cmd_export_align(block)
    btn="<button type=\"button\" onclick=\"loyaCopy(this)\">Copy</button>" if copy_button else ""
    return f"<div class=\"loya-command align-{align}\"><pre>{esc}</pre>{btn}</div>"
def _cmd_c_from_block(block,note_name=""):
    token=_cmd_token_from_block(block)
    if not token:return ""
    data=_decode_cmd_token(token)
    return _cmd_block_html(data,note_name) if data and _norm(data.get("command","")) else ""
def _replace_cmd_tables_with_c(html_text,note_name=""):
    if not html_text:return ""
    rx=re.compile(r"<table[^>]*>.*?</table>",re.S|re.I)
    def _rep(m):
        block=m.group(0)
        h=_cmd_c_from_block(block,note_name)
        return f"<p>{h}</p>" if h else block
    out=rx.sub(_rep,html_text)
    rxp=re.compile(r"<p\b[^>]*>.*?(?:cmdedit:|cmddelete:|cmdcopy:|cmdcard:)[A-Za-z0-9_-]+.*?</p>",re.S|re.I)
    out=rxp.sub(lambda m:(f"<p>{_cmd_c_from_block(m.group(0),note_name)}</p>" if _cmd_c_from_block(m.group(0),note_name) else m.group(0)),out)
    rxi=re.compile(r"<img\b[^>]*(?:cmdedit:|cmddelete:|cmdcopy:|cmdcard:)[A-Za-z0-9_-]+[^>]*>",re.S|re.I)
    out=rxi.sub(lambda m:(f"<p>{_cmd_c_from_block(m.group(0),note_name)}</p>" if _cmd_c_from_block(m.group(0),note_name) else m.group(0)),out)
    return out
def _cmd_export_align(block):
    b=(block or "").lower()
    if "align=\"right\"" in b or "text-align: right" in b or "text-align:right" in b or ("margin-left: auto" in b and "margin-right: 0" in b):return "right"
    if "align=\"center\"" in b or "text-align: center" in b or "text-align:center" in b or ("margin-left: auto" in b and "margin-right: auto" in b):return "center"
    return "left"
def _replace_cmd_tables_for_export(html_text,copy_button=True):
    if not html_text:return ""
    rx=re.compile(r"<table[^>]*>.*?</table>",re.S|re.I)
    def _rep(m):
        block=m.group(0)
        return _cmd_export_from_block(block,copy_button)
    out=rx.sub(_rep,html_text)
    rxp=re.compile(r"<p\b[^>]*>.*?(?:cmdedit:|cmddelete:|cmdcopy:|cmdcard:)[A-Za-z0-9_-]+.*?</p>",re.S|re.I)
    out=rxp.sub(lambda m:_cmd_export_from_block(m.group(0),copy_button),out)
    rxi=re.compile(r"<img\b[^>]*(?:cmdedit:|cmddelete:|cmdcopy:|cmdcard:)[A-Za-z0-9_-]+[^>]*>",re.S|re.I)
    out=rxi.sub(lambda m:_cmd_export_from_block(m.group(0),copy_button),out)
    return out
def _note_html_theme(title,group,body):
    return "\n".join([
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset=\"utf-8\" />",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
        f"<title>{_html_escape(title)}</title>",
        "<style>",
        "body{margin:0;background:#0d1117;color:#e8eef7;font-family:Segoe UI,Arial,sans-serif;line-height:1.55;}main{max-width:980px;margin:0 auto;padding:42px 22px 64px;}h1{font-size:34px;margin:0 0 8px;color:#fff;} .meta{color:#9fb3c8;margin:0 0 26px;font-weight:700}.note{background:#141b24;border:1px solid #263446;border-radius:18px;padding:26px;box-shadow:0 20px 60px rgba(0,0,0,.28)}a{color:#8ab5ff}.loya-command{display:flex;gap:10px;align-items:flex-start;margin:14px 0}.loya-command.align-center{justify-content:center}.loya-command.align-right{justify-content:flex-end}.loya-command pre{white-space:pre-wrap;word-break:break-word;margin:0;background:#08111d;border:1px solid #304663;border-radius:12px;color:#8cecff;padding:12px 14px;min-width:min(680px,70%);font-family:Consolas,Menlo,monospace}.loya-command button{background:#1d4ed8;color:#fff;border:0;border-radius:10px;padding:8px 14px;font-weight:800;cursor:pointer}.loya-command button:active{transform:translateY(1px)}table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #394b63;padding:6px 8px}img{max-width:100%;height:auto}hr{border:0;border-top:1px solid #53657a;margin:18px 0}",
        "</style>",
        "<script>function loyaCopy(btn){var p=btn&&btn.parentElement;var pre=p?p.querySelector('pre'):null;var t=pre?pre.innerText:'';if(navigator.clipboard){navigator.clipboard.writeText(t);}else{var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();}btn.innerText='Copied';setTimeout(function(){btn.innerText='Copy';},900);}</script>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{_html_escape(title)}</h1>",
        (f"<p class=\"meta\">{_html_escape(group)}</p>" if group else ""),
        f"<section class=\"note\">{body}</section>",
        "</main>",
        "</body>",
        "</html>",
    ])
def _notes_pdf_html(notes):
    parts=["<!DOCTYPE html><html><head><meta charset=\"utf-8\" /><style>body{font-family:Segoe UI,Arial,sans-serif;color:#111;line-height:1.45}h1{font-size:24px;margin:0 0 8px}.meta{color:#555;font-weight:700}.note-page{page-break-after:always}.note-page:last-child{page-break-after:auto}.loya-command{display:flex;gap:8px;align-items:flex-start;margin:10px 0}.loya-command.align-center{justify-content:center}.loya-command.align-right{justify-content:flex-end}.loya-command pre{white-space:pre-wrap;word-break:break-word;border:1px solid #bbb;background:#f5f7fb;color:#005bbb;font-weight:700;padding:8px;margin:0;font-family:Consolas,monospace}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:5px}img{max-width:100%;height:auto}</style></head><body>"]
    for n in notes or []:
        title=_norm(n.get("note_name","")) or "Untitled";group=_norm(n.get("group_name",""));body=_replace_cmd_tables_for_export(_extract_html_body(n.get("content","") or ""),copy_button=False)
        parts.append(f"<section class=\"note-page\"><h1>{_html_escape(title)}</h1>"+(f"<p class=\"meta\">{_html_escape(group)}</p>" if group else "")+body+"</section>")
    parts.append("</body></html>")
    return "\n".join(parts)
def _write_pdf_from_html(html_text,out_path):
    printer=QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(out_path)
    try:printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    except Exception:pass
    doc=QTextDocument()
    doc.setHtml(html_text or "")
    fn=getattr(doc,"print",None) or getattr(doc,"print_",None)
    if not callable(fn):raise RuntimeError("PDF printing is not available.")
    fn(printer)
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
def _note_to_markdown(note_name,html_text,group_name=""):
    name=_norm(note_name) or "Untitled"
    group=_norm(group_name)
    plain=_html_to_plain(html_text)
    rx=re.compile(r"<C\s*\[(.*?)\]\s*>\s*(.*?)\s*</C>",re.S|re.I)
    out=[f"# {name}",""]
    if group:
        out.append(f"Group: {group}")
        out.append("")
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
def _extract_md_group(body):
    lines=(body or "").splitlines()
    idx=0
    while idx<len(lines) and not _norm(lines[idx]):
        idx+=1
    if idx>=len(lines):
        return "",body or ""
    m=re.match(r"^group\s*:\s*(.+)$",lines[idx],re.I)
    if not m:
        return "",body or ""
    group=_norm(m.group(1))
    lines.pop(idx)
    if idx<len(lines) and not _norm(lines[idx]):
        lines.pop(idx)
    return group,"\n".join(lines)
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
def _import_template_markdown():
    return """# LOYA Note Import Template

This file is a testing template to show how to format Markdown for LOYA Note.

How to use:
- Command boxes: use <C [Command Note Tittle:..., Category:..., Sub Category:..., Tags:..., Description:...] >
  The command goes between the tags.
- Note references: use -Notename-My Note- to link to a note named "My Note".
- Separator line: type --- on its own line to insert a line in the editor.

## Command Box Example
<C [Command Note Tittle: Ping Host, Category: Recon, Sub Category: ICMP, Tags: ping, Description: basic ping] >
ping {IP}
</C>

## Note Reference Example
See -Notename-Aleaice- for details.

---
"""

def _json_template(obj):return json.dumps(obj,ensure_ascii=False,indent=2)+"\n"
def _human_notes_json_template():
    return _json_template({"Notes":[{"note_name":"Example Note","group_name":"Examples","content":"<h1>Example Note</h1><p>Write note content here.</p><p><strong>Bold</strong>, <em>italic</em>, <u>underline</u>.</p><p><C [Command Note Tittle: Example Command, Category: General, Sub Category: Shell, Tags: demo, Description: example command] ></p><pre>echo hello</pre><p></C></p>","created_at":"","updated_at":""}],"CommandsNotes":[{"note_name":"Example Note","category":"General","sub_category":"Shell","command":"echo hello","tags":"demo","description":"Example command","created_at":"","updated_at":""}],"Commands":[]})
def _human_commands_md_template():
    return """# Commands Notes

## Example Command
- Category: General
- Sub Category: Shell
- Tags: demo
- Description: Example command

```bash
echo hello
```
"""
def _human_commands_json_template():
    return _json_template({"CommandsNotes":[{"note_name":"Example Note","category":"General","sub_category":"Shell","command":"echo hello","tags":"demo","description":"Example command","created_at":"","updated_at":""}]})
def _human_targets_json_template():
    return _json_template([{"id":"example_target","name":"Example Target","status":"not_used","values":{"URL":"https://example.com","IP":"127.0.0.1"},"created":"","updated":""}])
def _human_targets_csv_template():
    return "id,name,status,created,updated,URL,IP\nexample_target,Example Target,not_used,,,https://example.com,127.0.0.1\n"
def _human_target_values_json_template():
    return _json_template({"URL":{"priority":0},"IP":{"priority":10}})
def _human_target_values_csv_template():
    return "key,priority\nURL,0\nIP,10\n"
def _ai_notes_template():
    return """# LOYA Notes AI Template

## 1. Prompt For AI
Rewrite the user's note into LOYA Note structured markdown.
Return only the import content from section 2.
Use one H1 line for the note name.
Use an optional Group line directly after the H1.
Keep commands inside LOYA command blocks exactly.
Available note features: Note Name, Group, normal text, command block, bold, italic, underline, font size, text color, reference color, left or center alignment, bullet list, numbered list, and table.
Markdown can represent bold, italic, lists, tables, headings, and links.
For LOYA command blocks, use this exact wrapper:
<C [Command Note Tittle: ..., Category: ..., Sub Category: ..., Tags: ..., Description: ...] >
command text here
</C>

## 2. Exact Import Format
```markdown
# Example Note
Group: Examples

This is normal note text.

**Bold text**
*Italic text*
<u>Underlined text</u>
<span style="font-size:18px;color:#ffffff;background-color:#333333">Styled text</span>

- Bullet item
- Bullet item

| Name | Value |
| --- | --- |
| URL | https://example.com |

<C [Command Note Tittle: Example Command, Category: General, Sub Category: Shell, Tags: demo, Description: example command] >
echo hello
</C>
```
"""
def _ai_commands_template():
    return """# LOYA Commands AI Template

## 1. Prompt For AI
Rewrite the user's command list into LOYA Commands Notes markdown.
Return only the import content from section 2.
Each command must be under a level 2 heading.
Use Category, Sub Category, Tags, and Description metadata when available.
Put the command body inside one fenced code block.
Do not add explanations outside the format.

## 2. Exact Import Format
````markdown
# Commands Notes

## Example Command
- Category: General
- Sub Category: Shell
- Tags: demo
- Description: Example command

```bash
echo hello
```
````
"""
def _ai_targets_template():
    return """# LOYA Targets AI Template

## 1. Prompt For AI
Rewrite the user's targets into LOYA Targets JSON.
Return only the JSON array from section 2.
Each target needs name, status, and values.
Status must be not_used or live.
Use values for target elements such as URL, IP, HOST, PORT, USERNAME, or any custom element name.
Keep JSON valid with double quotes.

## 2. Exact Import Format
```json
[
  {
    "id": "example_target",
    "name": "Example Target",
    "status": "not_used",
    "values": {
      "URL": "https://example.com",
      "IP": "127.0.0.1"
    },
    "created": "",
    "updated": ""
  }
]
```
"""
def _ai_target_values_template():
    return """# LOYA Target Values AI Template

## 1. Prompt For AI
Rewrite the user's target element names into LOYA Target Values JSON.
Return only the JSON object from section 2.
Each key is an element name.
Priority is a number from 0 to 65535.
Use manual true only when the value should stay manually controlled.
Keep JSON valid with double quotes.

## 2. Exact Import Format
```json
{
  "URL": {
    "priority": 0
  },
  "IP": {
    "priority": 10,
    "manual": true
  }
}
```
"""

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
def _fmt_mtime(ts):
    try:return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:return "-"
def _open_path_ui(path):
    p=_norm(path)
    if not p:return False,""
    try:
        if os.name=="nt":os.startfile(p);return True,""
        if sys.platform=="darwin":subprocess.Popen(["open",p]);return True,""
        subprocess.Popen(["xdg-open",p]);return True,""
    except Exception as e:
        return False,str(e)
def _tail_text(path,limit=180):
    p=_norm(path)
    if not p or not os.path.isfile(p):return ""
    try:
        with open(p,"r",encoding="utf-8",errors="ignore") as f:
            lines=[_norm(x) for x in f.readlines()[-8:]]
        lines=[x for x in lines if x]
        if not lines:return ""
        text=lines[-1]
        return text if len(text)<=limit else text[:max(0,limit-3)]+"..."
    except Exception:return ""
def _short_mid(text,max_len=96):
    s=_norm(text)
    if len(s)<=max_len:return s
    if max_len<12:return s[:max_len]
    head=max(4,(max_len-5)//2);tail=max(4,max_len-5-head)
    return s[:head]+" ... "+s[-tail:]
def _apply_theme(w):
    try:
        app=QApplication.instance()
        if app and app.styleSheet():w.setStyleSheet(app.styleSheet())
    except Exception:pass
def _progress(owner,title,subtitle):
    d=QDialog(owner);d.setObjectName("ProgressDialog");d.setWindowTitle(title);d.setModal(True);d.resize(520,140)
    _apply_theme(d)
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
    _common_db.apply_migrations(con)
class Note_LOYA_Database:
    def __init__(self,path=None):self.path=path or _db_path()
    def exists(self):return os.path.isfile(self.path)
    def connect(self):
        os.makedirs(os.path.dirname(self.path),exist_ok=True)
        return sqlite3.connect(self.path)
    def ensure(self):
        con=self.connect()
        try:
            _common_db.ensure_schema(con)
        finally:
            con.close()
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
    def list_note_refs(self):
        self.ensure()
        con=self.connect();cur=con.cursor()
        cols=set(self.table_cols("Notes"))
        if "group_name" in cols:
            sel="id,note_name,group_name"
        else:
            sel="id,note_name"
        try:
            cur.execute(f"SELECT {sel} FROM Notes ORDER BY note_name COLLATE NOCASE")
            rows=cur.fetchall()
        except Exception:
            rows=[]
        con.close()
        out=[]
        for r in rows:
            ref={"note_id":int(r[0]),"note_name":_norm(r[1])}
            if "group_name" in cols:ref["group_name"]=_norm(r[2])
            if ref["note_name"]:out.append(ref)
        return out
    def read_note_by_id(self,note_id):
        self.ensure()
        try:nid=int(str(note_id).strip())
        except Exception:return None
        con=self.connect();cur=con.cursor()
        try:
            cols=set(self.table_cols("Notes"))
            sel="id,note_name"+(",group_name" if "group_name" in cols else "")+",content"
            cur.execute(f"SELECT {sel} FROM Notes WHERE id=?",(nid,))
            r=cur.fetchone()
        except:r=None
        con.close()
        if not r:return None
        if "group_name" in cols:
            return {"id":int(r[0]),"note_name":r[1] or "","group_name":r[2] or "","content":r[3] or ""}
        return {"id":int(r[0]),"note_name":r[1] or "","group_name":"","content":r[2] or ""}
    def read_note_by_name(self,name):
        self.ensure()
        con=self.connect();cur=con.cursor()
        try:
            cols=set(self.table_cols("Notes"))
            sel="note_name"+(",group_name" if "group_name" in cols else "")+",content"
            cur.execute(f"SELECT {sel} FROM Notes WHERE note_name=?",(name,))
            r=cur.fetchone()
        except:r=None
        con.close()
        if not r:return None
        if "group_name" in cols:
            return {"note_name":r[0] or "","group_name":r[1] or "","content":r[2] or ""}
        return {"note_name":r[0] or "","group_name":"","content":r[1] or ""}
    def resolve_note_ref(self,note_id=None,note_name=""):
        self.ensure()
        return _note_refs.resolve_note_ref(self.path,note_id=note_id,note_name=note_name)
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
        cols=set(self.table_cols("Notes"))
        cur.execute("SELECT id,note_name"+(",group_name" if "group_name" in cols else "")+",content FROM Notes ORDER BY id ASC")
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
                md=_note_to_markdown(n.get("note_name",""),n.get("content",""),n.get("group_name",""))
                grp=_safe_filename(n.get("group_name",""),fallback="") if _norm(n.get("group_name","")) else ""
                folder=f"Notes/{grp}" if grp else "Notes"
                z.writestr(f"{folder}/{name}.md",md.encode("utf-8"))
            if cmd_notes:
                if progress:_set_prog(progress,int((len(notes)*100)/total),"Writing CommandsNotes ...")
                z.writestr("CommandsNotes.md",_commands_notes_to_markdown(cmd_notes).encode("utf-8"))
        if progress:_set_prog(progress,100,"Done.")
    def export_note_markdown(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        title=_norm(note.get("note_name","")) or "Untitled"
        group=_norm(note.get("group_name",""))
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
            parts.append("")
        if group:
            parts.append(f"Group: {group}")
            if body:parts.append("")
        if body:parts.append(body)
        with open(out_path,"w",encoding="utf-8") as f:f.write("\n".join(parts).rstrip()+"\n")
    def export_note_markdown_human(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        title=_norm(note.get("note_name","")) or "Untitled"
        html=_replace_cmd_tables_with_c(note.get("content","") or "",title)
        md=_note_to_markdown(title,html,note.get("group_name",""))
        with open(out_path,"w",encoding="utf-8") as f:f.write(md)
    def export_note_html(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        title=_norm(note.get("note_name","")) or "Untitled"
        group=_norm(note.get("group_name",""))
        body=_replace_cmd_tables_for_export(_extract_html_body(note.get("content","") or ""))
        with open(out_path,"w",encoding="utf-8") as f:f.write(_note_html_theme(title,group,body))
    def export_note_pdf(self,note_name,out_path):
        self.ensure()
        note=self.read_note_by_name(note_name)
        if not note:raise RuntimeError("Note not found.")
        _write_pdf_from_html(_notes_pdf_html([note]),out_path)
    def export_notes_pdf(self,out_path,progress=None):
        self.ensure()
        con=self.connect();con.row_factory=sqlite3.Row;cur=con.cursor()
        cols=set(self.table_cols("Notes"))
        cur.execute("SELECT id,note_name"+(",group_name" if "group_name" in cols else "")+",content FROM Notes ORDER BY id ASC")
        notes=[dict(r) for r in cur.fetchall()]
        con.close()
        if not notes:raise RuntimeError("No notes found.")
        if progress:_set_prog(progress,60,"Rendering PDF ...")
        _write_pdf_from_html(_notes_pdf_html(notes),out_path)
        if progress:_set_prog(progress,100,"Done.")
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
        group_name,body=_extract_md_group(body)
        name=_norm(title)
        if not name:
            base=os.path.splitext(os.path.basename(path))[0]
            name=_safe_filename(base,fallback="Imported Note")
        note_md=("# "+name+"\n\n"+body) if body else ("# "+name)
        html_text=_markdown_to_html(_wrap_c_blocks(note_md))
        cmd_blocks=_parse_cmd_blocks(note_md)
        row={"note_name":name,"group_name":group_name,"content":html_text}
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
            out={"note_name":_norm(r.get("note_name",r.get("title",""))),"group_name":_norm(r.get("group_name",r.get("group",""))),"content":r.get("content","") or "", "created_at":_norm(r.get("created_at","")), "updated_at":_norm(r.get("updated_at",""))}
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
                cur.execute("INSERT INTO Notes(note_name,group_name,content,created_at,updated_at) VALUES(?,?,?,?,?)",(_norm(r.get("note_name","")),_norm(r.get("group_name","")),r.get("content","") or "",r.get("created_at") or now,r.get("updated_at") or now))
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
                cur.execute("UPDATE Notes SET group_name=?,content=?,updated_at=? WHERE note_name=?",(_norm(r.get("group_name","")),r.get("content","") or "",now,_norm(old.get("note_name",""))))
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
    def export_csv(self,out_path,data):
        arr=data if isinstance(data,list) else [data] if isinstance(data,dict) else []
        keys=[]
        for it in arr:
            vals=it.get("values",{}) if isinstance(it,dict) and isinstance(it.get("values",{}),dict) else {}
            for k in vals.keys():
                kk=_norm(k)
                if kk and kk not in keys:keys.append(kk)
        fields=["id","name","status","created","updated"]+keys
        with open(out_path,"w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for it in arr:
                if not isinstance(it,dict):continue
                vals=it.get("values",{}) if isinstance(it.get("values",{}),dict) else {}
                row={k:_norm(it.get(k,"")) for k in ["id","name","status","created","updated"]}
                for k in keys:row[k]=_norm(vals.get(k,""))
                w.writerow(row)
    def parse_json(self,path):
        d=_read_json(path,[])
        if isinstance(d,list):return d
        if isinstance(d,dict):return [d]
        return []
    def parse_csv(self,path):
        out=[];base={"id","name","target","target_name","status","created","updated","values","values_json"}
        with open(path,"r",encoding="utf-8",newline="") as f:
            rd=csv.DictReader(f)
            for r in rd:
                if not isinstance(r,dict):continue
                vals={}
                raw=_norm(r.get("values_json",r.get("values","")))
                if raw:
                    try:
                        parsed=json.loads(raw)
                        if isinstance(parsed,dict):vals.update({str(k):"" if v is None else str(v) for k,v in parsed.items()})
                    except Exception:pass
                for k,v in r.items():
                    kk=_norm(k)
                    if not kk or _l(kk) in base:continue
                    vv=_norm(v)
                    if vv:vals[kk]=vv
                name=_norm(r.get("name",r.get("target_name",r.get("target",""))))
                if not name and not vals:continue
                st=_l(r.get("status","not_used")).replace(" ","_").replace("-","_")
                item={"id":_norm(r.get("id","")),"name":name,"status":"live" if st in ("live","used") else "not_used","values":vals,"created":_norm(r.get("created","")),"updated":_norm(r.get("updated",""))}
                out.append(item)
        return out
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
        return _update_backup.create_data_backup(progress=progress,prefix="Backup",out_dir=self.dir)
    def restore(self,zip_path,mode,progress=None):
        return _update_backup.restore_data_backup(zip_path,mode=mode,progress=progress)
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
def _plan_preview_counts(plan,decisions=None):
    dups=plan.get("dups") or []
    added=len(plan.get("new") or [])
    merged=int(plan.get("merged") or 0)
    replaced=0;overwritten=0;skipped=len(plan.get("skip") or [])
    if decisions is None:skipped+=len(dups)
    else:
        for idx,_ in enumerate(dups):
            act=decisions.get(idx,"Skip")
            if act=="Replace":replaced+=1
            elif act=="Overwrite":overwritten+=1
            else:skipped+=1
    return {"added":added,"merged":merged,"replaced":replaced,"overwritten":overwritten,"skipped":skipped,"dups":len(dups)}
def _skip_preview_lines(plan,limit=8):
    out=[]
    for it in (plan.get("skip") or [])[:max(0,int(limit))]:
        table=_norm(it.get("table","")) or "Unknown"
        row=it.get("incoming") or {}
        label=_norm((row.get("note_name","") if isinstance(row,dict) else "")) or _norm((row.get("key","") if isinstance(row,dict) else "")) or _norm((row.get("name","") if isinstance(row,dict) else "")) or _norm((row.get("command","") if isinstance(row,dict) else ""))
        if not label:label=_norm(json.dumps(row,ensure_ascii=False))[:120]
        out.append(f"{table}: {label or 'Unsupported row'}")
    return out
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
class _ImportPreviewDialog(QDialog):
    def __init__(self,owner,title,plan,rows,source_label=""):
        super().__init__(owner)
        self.setObjectName("ImportDupDialog")
        self.setWindowTitle(title)
        self.resize(1080,720)
        self._plan=plan if isinstance(plan,dict) else {"new":[],"dups":[],"skip":[]}
        self._rows=list(rows or [])
        lay=QVBoxLayout(self);lay.setContentsMargins(14,14,14,14);lay.setSpacing(10)
        head=QHBoxLayout();head.setSpacing(10)
        t=QLabel("Import Preview",self);t.setObjectName("PageTitle");head.addWidget(t,1)
        self.apply_all=QComboBox(self);self.apply_all.setObjectName("HomePerPage");self.apply_all.addItems(["Per Item","Skip All","Replace All","Overwrite All"]);self.apply_all.currentTextChanged.connect(self._apply_all);head.addWidget(QLabel("Duplicates",self),0);head.addWidget(self.apply_all,0)
        lay.addLayout(head)
        sub=QLabel(("Dry-run preview only. No data is written until you click Apply."+(f"\nSource: {source_label}" if _norm(source_label) else "")),self);sub.setObjectName("PageSubTitle");sub.setWordWrap(True);lay.addWidget(sub,0)
        grid=QGridLayout();grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(14);grid.setVerticalSpacing(6)
        self.lbl_added=QLabel("0",self);self.lbl_added.setObjectName("PageSubTitle")
        self.lbl_merged=QLabel("0",self);self.lbl_merged.setObjectName("PageSubTitle")
        self.lbl_replaced=QLabel("0",self);self.lbl_replaced.setObjectName("PageSubTitle")
        self.lbl_overwritten=QLabel("0",self);self.lbl_overwritten.setObjectName("PageSubTitle")
        self.lbl_skipped=QLabel("0",self);self.lbl_skipped.setObjectName("PageSubTitle")
        self.lbl_dups=QLabel("0",self);self.lbl_dups.setObjectName("PageSubTitle")
        grid.addWidget(QLabel("Added",self),0,0);grid.addWidget(self.lbl_added,0,1)
        grid.addWidget(QLabel("Merged",self),0,2);grid.addWidget(self.lbl_merged,0,3)
        grid.addWidget(QLabel("Replaced",self),1,0);grid.addWidget(self.lbl_replaced,1,1)
        grid.addWidget(QLabel("Overwritten",self),1,2);grid.addWidget(self.lbl_overwritten,1,3)
        grid.addWidget(QLabel("Skipped",self),2,0);grid.addWidget(self.lbl_skipped,2,1)
        grid.addWidget(QLabel("Duplicates",self),2,2);grid.addWidget(self.lbl_dups,2,3)
        lay.addLayout(grid)
        skip_lines=_skip_preview_lines(self._plan)
        skip_total=len(self._plan.get("skip") or [])
        skip_msg=""
        if skip_total:
            skip_msg=f"Rows that cannot be imported safely will be skipped: {skip_total}."
            if skip_lines:skip_msg+="\n"+("\n".join(skip_lines))
            if skip_total>len(skip_lines):skip_msg+=f"\n... and {skip_total-len(skip_lines)} more."
        else:
            skip_msg="No invalid rows were detected in the dry-run."
        self.skip_info=QLabel(skip_msg,self);self.skip_info.setObjectName("PageSubTitle");self.skip_info.setWordWrap(True);lay.addWidget(self.skip_info,0)
        self.table=QTableWidget(self);self.table.setObjectName("HomeTable");self.table.setColumnCount(6);self.table.setHorizontalHeaderLabels(["Action","Table","Key","Existing","Incoming","Incoming Command"]);self.table.verticalHeader().setVisible(False);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setAlternatingRowColors(False);self.table.setShowGrid(True)
        h=self.table.horizontalHeader();h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter);h.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents);h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents);h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents);h.setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch);h.setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch);h.setSectionResizeMode(5,QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table,1)
        fb=QHBoxLayout();fb.setSpacing(10)
        self.btn_ok=QToolButton(self);self.btn_ok.setObjectName("TargetSaveBtn");self.btn_ok.setText("Apply")
        self.btn_cancel=QToolButton(self);self.btn_cancel.setObjectName("TargetCancelBtn");self.btn_cancel.setText("Cancel")
        self.btn_ok.clicked.connect(self.accept);self.btn_cancel.clicked.connect(self.reject)
        fb.addStretch(1);fb.addWidget(self.btn_ok,0);fb.addWidget(self.btn_cancel,0)
        lay.addLayout(fb)
        self._render();self._refresh_summary()
    def _make_combo(self):
        cb=QComboBox(self.table);cb.addItems(["Skip","Replace","Overwrite"]);cb.setCurrentText("Skip");cb.currentTextChanged.connect(lambda *_:self._refresh_summary());return cb
    def _apply_all(self,t):
        if t=="Per Item":return
        want="Skip" if t=="Skip All" else ("Replace" if t=="Replace All" else "Overwrite")
        for r in range(self.table.rowCount()):
            w=self.table.cellWidget(r,0)
            if isinstance(w,QComboBox):w.setCurrentText(want)
        self._refresh_summary()
    def _render(self):
        self.table.setRowCount(len(self._rows))
        for r,it in enumerate(self._rows):
            self.table.setCellWidget(r,0,self._make_combo())
            t=QTableWidgetItem(_norm(it.get("table","")));t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            k=QTableWidgetItem(_norm(it.get("key",""))[:180]);k.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            ex=QTableWidgetItem(_norm(it.get("existing",""))[:260]);ex.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            inc=QTableWidgetItem(_norm(it.get("incoming",""))[:260]);inc.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            cmd=QTableWidgetItem(_norm(it.get("in_cmd",""))[:260]);cmd.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r,1,t);self.table.setItem(r,2,k);self.table.setItem(r,3,ex);self.table.setItem(r,4,inc);self.table.setItem(r,5,cmd);self.table.setRowHeight(r,44)
        self.table.clearSelection()
    def decisions(self):
        out={}
        for r in range(self.table.rowCount()):
            w=self.table.cellWidget(r,0)
            out[r]=w.currentText() if isinstance(w,QComboBox) else "Skip"
        return out
    def _refresh_summary(self):
        counts=_plan_preview_counts(self._plan,self.decisions())
        self.lbl_added.setText(str(int(counts.get("added",0))))
        self.lbl_merged.setText(str(int(counts.get("merged",0))))
        self.lbl_replaced.setText(str(int(counts.get("replaced",0))))
        self.lbl_overwritten.setText(str(int(counts.get("overwritten",0))))
        self.lbl_skipped.setText(str(int(counts.get("skipped",0))))
        self.lbl_dups.setText(str(int(counts.get("dups",0))))
class _CurrentPageStack(QStackedWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda *_:self.updateGeometry())
    def sizeHint(self):
        cur=self.currentWidget()
        if cur is not None:
            try:
                sz=cur.sizeHint()
                if sz.isValid():return sz
            except Exception:pass
        return super().sizeHint()
    def minimumSizeHint(self):
        cur=self.currentWidget()
        if cur is not None:
            try:
                sz=cur.minimumSizeHint()
                if sz.isValid():return sz
            except Exception:pass
        return super().minimumSizeHint()
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
    def _preview(self,owner,plan,path_label=""):
        dups=[self.db.summarize_dup(x) for x in (plan.get("dups") or [])]
        dlg=_ImportPreviewDialog(owner,"Import Preview",plan,dups,source_label=path_label)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return None
        return dlg.decisions()
    def _apply_import(self,owner,plan,incoming,kind,path_label=""):
        decisions=self._preview(owner,plan,path_label)
        if decisions is None:return None
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
            _set_prog(prog,80,"Ready.")
        finally:
            prog.close()
        return self._apply_import(owner,plan,incoming,kind,os.path.basename(path))
    def run_multi_markdown(self,owner,paths):
        if not paths:return None
        if not self.db.exists():self.db.ensure()
        totals={"added":0,"replaced":0,"overwritten":0,"skipped":0,"bad":0}
        total=max(1,len(paths))
        for i,p in enumerate(paths):
            prog=_progress(owner,"Import",f"Preparing {i+1}/{total}: {os.path.basename(p)}");prog.show()
            try:
                incoming=self._apply_md_name(self.db.parse_incoming_markdown(p,progress=prog),p)
                existing=self.db.load_existing_maps()
                _set_prog(prog,55,"Scanning duplicates ...")
                plan=self.db.build_import_plan(incoming,existing,progress=prog)
                _set_prog(prog,80,"Ready.")
            finally:
                prog.close()
            res=self._apply_import(owner,plan,incoming,"md",os.path.basename(p)) or {}
            if not res:return None
            for k in totals.keys():
                try:totals[k]+=int(res.get(k,0))
                except Exception:pass
        return totals
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
            elif kind=="pdf":
                self.db.export_notes_pdf(out_path,progress=prog)
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
        self.table.cellClicked.connect(self._on_cell_click)
        self.table.cellDoubleClicked.connect(self._on_cell_double)
        self.table.itemSelectionChanged.connect(self._on_sel)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        fm=self.table.fontMetrics();self.table.setColumnWidth(2,max(88,fm.horizontalAdvance("000.0 MB")+26));self.table.setColumnWidth(3,max(72,fm.horizontalAdvance("Action")+28))
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
    def _schedule_table_refresh(self):QTimer.singleShot(0,self._refresh_table_layout)
    def showEvent(self,e):
        try:super().showEvent(e)
        except Exception:pass
        self._schedule_table_refresh()
    def resizeEvent(self,e):
        try:super().resizeEvent(e)
        except Exception:pass
        self._schedule_table_refresh()
    def _refresh_table_layout(self):
        try:self.table.doItemsLayout()
        except Exception:pass
        try:self.table.updateGeometry()
        except Exception:pass
        try:self.table.viewport().update()
        except Exception:pass
        try:
            h=self.table.horizontalHeader()
            h.setStretchLastSection(False)
            h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
            self.table.resizeColumnToContents(1)
            fm=self.table.fontMetrics();self.table.setColumnWidth(2,max(88,fm.horizontalAdvance("000.0 MB")+26));self.table.setColumnWidth(3,max(72,fm.horizontalAdvance("Action")+28))
        except Exception:pass
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
            name=QTableWidgetItem(os.path.basename(p));name.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft);name.setData(Qt.ItemDataRole.UserRole,p);name.setToolTip(p)
            mod=QTableWidgetItem(datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S"));mod.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            size=QTableWidgetItem(_fmt_size(sz));size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            x=QTableWidgetItem("X");x.setTextAlignment(Qt.AlignmentFlag.AlignCenter);x.setForeground(QColor("#ff5a5a"));xf=x.font();xf.setBold(True);xf.setWeight(900);x.setFont(xf);x.setToolTip("Delete")
            self.table.setItem(r,0,name);self.table.setItem(r,1,mod);self.table.setItem(r,2,size);self.table.setItem(r,3,x)
            self.table.setRowHeight(r,44)
        self.table.clearSelection()
        self._on_sel()
        self._schedule_table_refresh()
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
    def _row_path(self,row):
        it=self.table.item(row,0)
        if not it:return ""
        p=it.data(Qt.ItemDataRole.UserRole)
        return p if isinstance(p,str) else ""
    def _on_cell_click(self,row,col):
        if col!=3:return
        p=self._row_path(row)
        if p:self._delete_one(p)
    def _on_cell_double(self,row,col):
        if col==3:return
        self._restore_selected()
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
class _UpdatePage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(2)
        top=QHBoxLayout();top.setContentsMargins(8,8,8,0);top.setSpacing(4)
        t=QLabel("Update",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(8,6,8,8);v.setSpacing(6)
        self.info=QLabel("Check the official LOYA repository, download authenticated releases, and apply updates safely without touching Data/.",box);self.info.setObjectName("PageSubTitle");self.info.setWordWrap(True)
        v.addWidget(self.info,0)
        row=QHBoxLayout();row.setSpacing(6)
        self.chk_auto=QCheckBox("Enable update checks",box)
        self.cmb_freq=QComboBox(box);self.cmb_freq.setObjectName("HomePerPage")
        self.cmb_channel=QComboBox(box);self.cmb_channel.setObjectName("HomePerPage")
        self._freq_items=[("Daily",24),("Every 3 days",72),("Weekly",168)]
        self.cmb_freq.addItems([x[0] for x in self._freq_items])
        self.cmb_channel.addItems(["stable"])
        row.addWidget(self.chk_auto,0);row.addWidget(QLabel("Frequency",box),0);row.addWidget(self.cmb_freq,0);row.addWidget(QLabel("Channel",box),0);row.addWidget(self.cmb_channel,0);row.addStretch(1)
        v.addLayout(row)
        grid=QGridLayout();grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(8);grid.setVerticalSpacing(4);grid.setColumnStretch(1,1)
        self.cur_ver=QLabel("-",box);self.cur_ver.setObjectName("PageSubTitle")
        self.latest_ver=QLabel("-",box);self.latest_ver.setObjectName("PageSubTitle")
        self.last_checked=QLabel("-",box);self.last_checked.setObjectName("PageSubTitle")
        self.last_good=QLabel("-",box);self.last_good.setObjectName("PageSubTitle")
        self.source_repo=QLineEdit(box);self.source_repo.setObjectName("TargetInput");self.source_repo.setReadOnly(True)
        self.manifest_url=QLineEdit(box);self.manifest_url.setObjectName("TargetInput");self.manifest_url.setReadOnly(True)
        self.status=QLabel("-",box);self.status.setObjectName("PageSubTitle");self.status.setWordWrap(True)
        self.snapshots=QLabel("-",box);self.snapshots.setObjectName("PageSubTitle");self.snapshots.setWordWrap(True)
        grid.addWidget(QLabel("Current Version",box),0,0);grid.addWidget(self.cur_ver,0,1)
        grid.addWidget(QLabel("Latest Available",box),1,0);grid.addWidget(self.latest_ver,1,1)
        grid.addWidget(QLabel("Last Checked",box),2,0);grid.addWidget(self.last_checked,2,1)
        grid.addWidget(QLabel("Last Good Version",box),3,0);grid.addWidget(self.last_good,3,1)
        grid.addWidget(QLabel("Authenticated Repo",box),4,0);grid.addWidget(self.source_repo,4,1)
        grid.addWidget(QLabel("Manifest URL",box),5,0);grid.addWidget(self.manifest_url,5,1)
        grid.addWidget(QLabel("Update Status",box),6,0);grid.addWidget(self.status,6,1)
        grid.addWidget(QLabel("Code Snapshots",box),7,0);grid.addWidget(self.snapshots,7,1)
        v.addLayout(grid)
        acts=QHBoxLayout();acts.setSpacing(6)
        self.btn_check=QToolButton(box);self.btn_check.setObjectName("TargetAddBtn");self.btn_check.setText("Check Now");self.btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update=QToolButton(box);self.btn_update.setObjectName("TargetMiniBtn");self.btn_update.setText("Update Now");self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logs=QToolButton(box);self.btn_logs.setObjectName("TargetMiniBtn");self.btn_logs.setText("Open Logs");self.btn_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_snaps=QToolButton(box);self.btn_snaps.setObjectName("TargetMiniBtn");self.btn_snaps.setText("Open Snapshots");self.btn_snaps.setCursor(Qt.CursorShape.PointingHandCursor)
        acts.addWidget(self.btn_check,0);acts.addWidget(self.btn_update,0);acts.addWidget(self.btn_logs,0);acts.addWidget(self.btn_snaps,0);acts.addStretch(1)
        v.addLayout(acts)
        self.footer=QLabel("",box);self.footer.setObjectName("PageSubTitle");self.footer.setWordWrap(True)
        v.addWidget(self.footer,0)
        self.footer.hide()
        root.addWidget(box,0)
        root.addStretch(1)
        self.chk_auto.stateChanged.connect(self._save_update_settings)
        self.cmb_freq.currentIndexChanged.connect(self._save_update_settings)
        self.cmb_channel.currentIndexChanged.connect(self._save_update_settings)
        self.btn_check.clicked.connect(self._do_check)
        self.btn_update.clicked.connect(self._do_update_now)
        self.btn_logs.clicked.connect(self._open_logs)
        self.btn_snaps.clicked.connect(self._open_snapshots)
        QTimer.singleShot(0,self._load_all)
    def _set_footer(self,msg):
        text=_norm(msg)
        self.footer.setText(text)
        self.footer.setVisible(bool(text))
    def _fmt_when(self,text):
        s=_norm(text)
        if not s:return "-"
        try:
            d=datetime.fromisoformat(s.replace("Z","+00:00"))
            return d.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return s
    def _update_status_text(self,state):
        st=state if isinstance(state,dict) else {}
        cur=_norm(st.get("current_version",""))
        latest=_norm(st.get("last_available_version",""))
        pending=_norm(st.get("pending_version",""))
        err=_norm(st.get("last_error",""))
        if err:return "Error: "+err
        if st.get("update_in_progress"):
            if pending and cur and pending==cur:
                return f"Installed update {pending}. Waiting for first successful launch confirmation."
            return f"Update in progress to {pending or latest or '?'}."
        if pending:
            return f"Pending update detected for {pending}."
        if cur and latest:
            try:
                cmpv=_compare_update_versions(latest,cur)
                if cmpv>0:return f"New version available: {latest}."
                if cmpv==0:return "You are on the latest version."
            except Exception:
                pass
        if latest:return f"Latest authenticated release: {latest}."
        return "Not checked yet."
    def _load_update_settings(self):
        cfg=_get_update_settings()
        for w in (self.chk_auto,self.cmb_freq,self.cmb_channel):
            try:w.blockSignals(True)
            except:pass
        self.chk_auto.setChecked(bool(cfg.get("auto_enabled",False)))
        idx=0
        for i,(_,hrs) in enumerate(self._freq_items):
            if int(hrs)==int(cfg.get("check_interval_hours",24)):idx=i;break
        self.cmb_freq.setCurrentIndex(idx)
        self.cmb_channel.setCurrentIndex(0)
        for w in (self.chk_auto,self.cmb_freq,self.cmb_channel):
            try:w.blockSignals(False)
            except:pass
        return cfg
    def _save_update_settings(self,*_):
        hrs=self._freq_items[self.cmb_freq.currentIndex()][1] if self._freq_items else 24
        cfg={"auto_enabled":self.chk_auto.isChecked(),"check_interval_hours":hrs,"repo_url":_UP_REPO_URL,"manifest_url":_UP_MANIFEST_URL,"last_checked":_get_update_settings().get("last_checked",""),"last_channel":"stable"}
        _save_update_settings(cfg)
        self._set_footer("Update settings saved.")
    def _refresh_view(self,state=None):
        st=state if isinstance(state,dict) else _get_update_state()
        ident=_get_app_identity()
        cfg=_sync_update_settings_from_state(st)
        snaps=_list_code_snapshots()
        self.cur_ver.setText(_norm(ident.get("version","")) or "-")
        self.latest_ver.setText(_norm(st.get("last_available_version","")) or "-")
        self.last_checked.setText(self._fmt_when(cfg.get("last_checked","") or st.get("last_checked","")))
        self.last_good.setText(_norm(st.get("last_good_version","")) or "-")
        self.source_repo.setText(_norm(st.get("source_repo","")) or _UP_REPO_URL)
        self.manifest_url.setText(_UP_MANIFEST_URL)
        self.status.setText(self._update_status_text(st))
        snap_dir=_old_versions_dir()
        self.snapshots.setText(f"{len(snaps)} snapshot(s) in {snap_dir}")
        cur=_norm(st.get("current_version",""));latest=_norm(st.get("last_available_version",""));can_update=False
        if cur and latest:
            try:can_update=_compare_update_versions(latest,cur)>0
            except Exception:can_update=False
        self.btn_update.setEnabled(can_update and not bool(st.get("update_in_progress")))
    def _load_all(self):
        self._load_update_settings()
        self._refresh_view()
    def _do_check(self):
        prog=_progress(self,"Update Check","Checking official release ...");prog.show()
        try:
            out=_check_for_updates(timeout=10)
        finally:
            try:prog.close()
            except:pass
        state=out.get("state",{}) if isinstance(out,dict) else {}
        self._refresh_view(state)
        if out.get("ok"):
            if out.get("update_available"):
                msg=f"New authenticated version available: {state.get('last_available_version','')}."
            else:
                msg="You are already on the latest authenticated version."
            self._set_footer(msg);_log("[+]",f"Update check ok latest={state.get('last_available_version','')}")
        else:
            msg="Update check failed: "+_norm(out.get("error","Unknown error"))
            self._set_footer(msg);_log("[!]",msg)
    def _do_update_now(self):
        check=self._check_state_ready()
        if not check:return
        cur=_norm(check.get("current_version",""));latest=_norm(check.get("last_available_version",""))
        mb=QMessageBox(self);_apply_theme(mb);mb.setWindowTitle("Apply Update");mb.setText(f"Apply authenticated update from {cur or '?'} to {latest or '?'}?\n\nLOYA will create data and code backups, close the main window, apply the package from the official repository, and relaunch through RunNote.py.")
        bok=mb.addButton("Apply Update",QMessageBox.ButtonRole.AcceptRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()!=bok:return
        prog=_progress(self,"Update","Checking authenticated release ...");prog.show()
        try:
            out=_start_update_install(timeout=60,parent_pid=os.getpid(),launcher_python=sys.executable,launcher_script=os.path.join(_project_root(),"RunNote.py"),progress=prog)
        except Exception as e:
            out={"ok":False,"error":str(e),"state":_get_update_state()}
        finally:
            try:prog.close()
            except:pass
        state=out.get("state",{}) if isinstance(out,dict) else {}
        self._refresh_view(state)
        if not out.get("ok"):
            msg="Update start failed: "+_norm(out.get("error","Unknown error"))
            self._set_footer(msg);_log("[!]",msg)
            try:
                mb=QMessageBox(self);_apply_theme(mb);mb.setWindowTitle("Update Failed");mb.setText(msg);mb.setIcon(QMessageBox.Icon.Warning);mb.exec()
            except Exception:pass
            return
        backups=out.get("backups",{}) if isinstance(out.get("backups",{}),dict) else {}
        msg="The authenticated package is ready. LOYA will close now, apply the update out of process, and relaunch through RunNote.py."
        self._set_footer(msg)
        _log("[+]",f"Update handoff ready target={out.get('manifest',{}).get('version','')} helper_pid={out.get('helper_pid',0)} data={backups.get('data_backup','')} code={backups.get('code_snapshot','')}")
        try:
            mb=QMessageBox(self);_apply_theme(mb);mb.setWindowTitle("Applying Update");mb.setText(msg+f"\n\nData backup:\n{backups.get('data_backup','')}\n\nCode snapshot:\n{backups.get('code_snapshot','')}");mb.setIcon(QMessageBox.Icon.Information);mb.exec()
        except Exception:pass
        app=QApplication.instance()
        if app is not None:QTimer.singleShot(150,app.quit)
    def _check_state_ready(self):
        state=_get_update_state()
        cur=_norm(state.get("current_version",""));latest=_norm(state.get("last_available_version",""))
        if state.get("update_in_progress"):
            self._set_footer("An update is already in progress. Let it relaunch or recover first.")
            return None
        if not latest:
            self._do_check()
            state=_get_update_state();cur=_norm(state.get("current_version",""));latest=_norm(state.get("last_available_version",""))
        if not latest:
            self._set_footer("No authenticated release information is available yet.")
            return None
        try:
            if _compare_update_versions(latest,cur)<=0:
                self._set_footer("You are already on the latest authenticated version.")
                return None
        except Exception:
            self._set_footer("Version comparison failed. Check again first.")
            return None
        return state
    def _open_path(self,path):
        p=_norm(path)
        if not p:return False
        try:
            if os.name=="nt":os.startfile(p);return True
            if sys.platform=="darwin":subprocess.Popen(["open",p]);return True
            subprocess.Popen(["xdg-open",p]);return True
        except Exception as e:
            self._set_footer(f"Open failed: {e}")
            return False
    def _open_logs(self):
        p=os.path.join(_health_check.logs_dir(),"Update_log.log")
        try:
            os.makedirs(os.path.dirname(p),exist_ok=True)
            if not os.path.isfile(p):
                with open(p,"a",encoding="utf-8"):pass
        except Exception:
            pass
        if self._open_path(p):self._set_footer("Opened update log.")
    def _open_snapshots(self):
        p=_old_versions_dir()
        os.makedirs(p,exist_ok=True)
        if self._open_path(p):self._set_footer("Opened code snapshots folder.")
class _RecycleBinPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._rows=[]
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        top=QHBoxLayout();top.setContentsMargins(8,8,8,0);top.setSpacing(4)
        t=QLabel("Recycle Bin",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(10,8,10,10);v.setSpacing(6)
        self.info=QLabel("Deleted notes, commands, and targets stay here for 30 days before they are purged automatically.",box);self.info.setObjectName("PageSubTitle");self.info.setWordWrap(True)
        v.addWidget(self.info,0)
        row1=QHBoxLayout();row1.setSpacing(4)
        self.search=QLineEdit(box);self.search.setObjectName("TargetSearch");self.search.setPlaceholderText("Search recycle bin...")
        self.cmb_type=QComboBox(box);self.cmb_type.setObjectName("HomePerPage")
        self.cmb_type.addItem("All","")
        self.cmb_type.addItem("Notes",_recycle_bin.TYPE_NOTE)
        self.cmb_type.addItem("Commands",_recycle_bin.TYPE_COMMAND)
        self.cmb_type.addItem("Targets",_recycle_bin.TYPE_TARGET)
        self.btn_refresh=QToolButton(box);self.btn_refresh.setObjectName("TargetAddBtn");self.btn_refresh.setText("Refresh")
        self.btn_restore=QToolButton(box);self.btn_restore.setObjectName("TargetMiniBtn");self.btn_restore.setText("Restore")
        self.btn_delete=QToolButton(box);self.btn_delete.setObjectName("TargetMiniBtn");self.btn_delete.setText("Delete Permanently")
        row1.addWidget(self.search,1);row1.addWidget(self.cmb_type,0);row1.addWidget(self.btn_refresh,0);row1.addWidget(self.btn_restore,0);row1.addWidget(self.btn_delete,0)
        v.addLayout(row1)
        self.table=QTableWidget(box);self.table.setObjectName("HomeTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Type","Label","Source","Deleted","Expires"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(96)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0,120);self.table.setColumnWidth(2,150);self.table.setColumnWidth(3,180);self.table.setColumnWidth(4,180)
        v.addWidget(self.table,1)
        self.status=QLabel("",box);self.status.setObjectName("PageSubTitle");self.status.setWordWrap(True)
        v.addWidget(self.status,0)
        root.addWidget(box,1)
        self.search.textChanged.connect(self._render)
        self.cmb_type.currentIndexChanged.connect(self._load)
        self.btn_refresh.clicked.connect(self._load)
        self.btn_restore.clicked.connect(self._restore_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.table.itemSelectionChanged.connect(self._sync_actions)
        self.table.cellDoubleClicked.connect(lambda r,c:self._restore_selected())
        QTimer.singleShot(0,self._load)
    def _fmt_when(self,text):
        s=_norm(text)
        if not s:return "-"
        try:return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:return s
    def _set_status(self,msg):self.status.setText(_norm(msg))
    def _selected_ids(self):
        out=[]
        sm=self.table.selectionModel()
        if not sm:return out
        for ix in sm.selectedRows(0):
            it=self.table.item(ix.row(),0)
            if not it:continue
            rid=it.data(Qt.ItemDataRole.UserRole)
            if str(rid).isdigit() and int(rid) not in out:out.append(int(rid))
        return out
    def _sync_actions(self):
        n=len(self._selected_ids())
        self.btn_restore.setEnabled(n>0)
        self.btn_delete.setEnabled(n>0)
    def _set_item(self,row,col,text,data=None,align=None,bold=False):
        it=QTableWidgetItem(text)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
        it.setToolTip(_norm(text))
        if align is not None:it.setTextAlignment(align)
        if bold:
            f=it.font();f.setBold(True);f.setWeight(800);it.setFont(f)
        if data is not None:it.setData(Qt.ItemDataRole.UserRole,data)
        self.table.setItem(row,col,it)
    def _load(self,*_):
        purged=_recycle_bin.purge_expired()
        et=self.cmb_type.currentData()
        self._rows=_recycle_bin.list_entries(entity_type=et or "")
        self._render()
        msg=f"{len(self._rows)} item(s) in Recycle Bin."
        if purged:msg+=f" Purged expired: {purged}."
        self._set_status(msg)
    def _render(self,*_):
        q=_norm(self.search.text()).lower()
        rows=[]
        for it in self._rows:
            if q and q not in _norm(it.get("label","")).lower() and q not in _norm(it.get("source","")).lower() and q not in _norm(_recycle_bin.TYPE_LABELS.get(it.get("entity_type",""),it.get("entity_type",""))).lower():continue
            rows.append(it)
        self.table.setRowCount(len(rows))
        for r,it in enumerate(rows):
            typ=_recycle_bin.TYPE_LABELS.get(it.get("entity_type",""),_norm(it.get("entity_type","")).title())
            self._set_item(r,0,typ,it.get("id"),Qt.AlignmentFlag.AlignCenter,True)
            self._set_item(r,1,_norm(it.get("label","")) or "-",None,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,True)
            self._set_item(r,2,_norm(it.get("source","")) or "-",None,Qt.AlignmentFlag.AlignCenter,False)
            self._set_item(r,3,self._fmt_when(it.get("deleted_at","")),None,Qt.AlignmentFlag.AlignCenter,False)
            self._set_item(r,4,self._fmt_when(it.get("expires_at","")),None,Qt.AlignmentFlag.AlignCenter,False)
            self.table.setRowHeight(r,46)
        self.table.clearSelection()
        self._sync_actions()
    def _restore_selected(self):
        ids=self._selected_ids()
        if not ids:return
        mb=QMessageBox(self);mb.setWindowTitle("Restore");mb.setText(f"Restore {len(ids)} item(s) from Recycle Bin?")
        bok=mb.addButton("Restore",QMessageBox.ButtonRole.AcceptRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()!=bok:return
        ok=0;fails=[]
        for rid in ids:
            done,msg=_recycle_bin.restore_entry(rid)
            if done:ok+=1
            else:fails.append(f"#{rid}: {msg}")
        self._load()
        msg=f"Restored: {ok}"
        if fails:msg+=f" | Failed: {len(fails)}"
        self._set_status(msg)
        if fails:QMessageBox.warning(self,"Restore Issues","\n".join(fails[:8]))
    def _delete_selected(self):
        ids=self._selected_ids()
        if not ids:return
        mb=QMessageBox(self);mb.setWindowTitle("Delete Permanently");mb.setText(f"Permanently delete {len(ids)} Recycle Bin item(s)?\n\nThis cannot be undone.")
        bok=mb.addButton("Delete",QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()!=bok:return
        ok=0;fails=[]
        for rid in ids:
            done,msg=_recycle_bin.delete_entry(rid)
            if done:ok+=1
            else:fails.append(f"#{rid}: {msg}")
        self._load()
        msg=f"Deleted permanently: {ok}"
        if fails:msg+=f" | Failed: {len(fails)}"
        self._set_status(msg)
        if fails:QMessageBox.warning(self,"Delete Issues","\n".join(fails[:8]))
class _ImportExportPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.db=Note_LOYA_Database()
        self.ncn_imp=NCN_Import(self.db)
        self.ncn_exp=NCN_Export(self.db)
        self.tv=TargetValues()
        self.tg=Targets()
        self._status_labels={}
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,14,14,0);top.setSpacing(10)
        t=QLabel("Import and Export",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        self.tabs=QTabWidget(self);self.tabs.setObjectName("TargetTabs")
        export_box,ev=self._make_tab()
        self.btn_all_exp=self._button(export_box,"Export","TargetAddBtn",self._export_all)
        ev.addLayout(self._make_row(export_box,"Export All",self.btn_all_exp));ev.addWidget(self._make_status("all",export_box),0)
        self.btn_ncn_exp=self._menu_button(export_box,"All Notes","TargetMiniBtn",[("Database (.db)",lambda:self._ncn_export("db")),("JSON (.json)",lambda:self._ncn_export("json")),("CSV ZIP (.zip)",lambda:self._ncn_export("csv")),("Markdown ZIP (.zip)",lambda:self._ncn_export("md")),("PDF (.pdf)",lambda:self._ncn_export("pdf"))])
        self.btn_note_exp=self._menu_button(export_box,"One Note","TargetMiniBtn",[("Markdown (.md)",lambda:self._notes_export("md")),("Human Markdown (.md)",lambda:self._notes_export("md_human")),("HTML (.html)",lambda:self._notes_export("html")),("PDF (.pdf)",lambda:self._notes_export("pdf"))])
        ev.addLayout(self._make_row(export_box,"Export Notes",self.btn_ncn_exp,self.btn_note_exp));ev.addWidget(self._make_status("ncn",export_box),0);ev.addWidget(self._make_status("note",export_box),0)
        self.btn_cmd_exp=self._menu_button(export_box,"Export","TargetMiniBtn",[("Markdown (.md)",lambda:self._commands_export("md")),("JSON (.json)",lambda:self._commands_export("json")),("CSV (.csv)",lambda:self._commands_export("csv"))])
        ev.addLayout(self._make_row(export_box,"Export Commands (Notes DB)",self.btn_cmd_exp));ev.addWidget(self._make_status("cmd",export_box),0)
        self.btn_tv_exp=self._menu_button(export_box,"Export","TargetMiniBtn",[("JSON (.json)",lambda:self._tv_export("json")),("CSV (.csv)",lambda:self._tv_export("csv"))])
        ev.addLayout(self._make_row(export_box,"Export Target Values",self.btn_tv_exp));ev.addWidget(self._make_status("tv",export_box),0)
        self.btn_tg_exp=self._menu_button(export_box,"Export","TargetMiniBtn",[("JSON (.json)",lambda:self._tg_export("json")),("CSV (.csv)",lambda:self._tg_export("csv"))])
        ev.addLayout(self._make_row(export_box,"Export Targets",self.btn_tg_exp));ev.addWidget(self._make_status("tg",export_box),0)
        ev.addStretch(1)
        import_box,iv=self._make_tab()
        self.btn_all_imp=self._button(import_box,"Import","TargetAddBtn",self._import_all)
        iv.addLayout(self._make_row(import_box,"Import All",self.btn_all_imp));iv.addWidget(self._make_status("all_import",import_box),0)
        self.btn_ncn_imp=self._menu_button(import_box,"Import","TargetAddBtn",[("Database (.db)",lambda:self._ncn_import("db")),("JSON (.json)",lambda:self._ncn_import("json")),("CSV Bundle (.zip/.csv)",lambda:self._ncn_import("csv")),("Structured Markdown (.md)",lambda:self._ncn_import("md")),("Human Markdown (.md)",lambda:self._ncn_import("md_human"))])
        iv.addLayout(self._make_row(import_box,"Import Notes",self.btn_ncn_imp));iv.addWidget(self._make_status("ncn",import_box),0)
        self.btn_cmd_imp=self._menu_button(import_box,"Import","TargetAddBtn",[("Markdown (.md)",lambda:self._commands_import("md")),("JSON (.json)",lambda:self._commands_import("json")),("CSV (.csv)",lambda:self._commands_import("csv"))])
        iv.addLayout(self._make_row(import_box,"Import Commands (Notes DB)",self.btn_cmd_imp));iv.addWidget(self._make_status("cmd",import_box),0)
        self.btn_tv_imp=self._menu_button(import_box,"Import","TargetAddBtn",[("JSON (.json)",lambda:self._tv_import("json")),("CSV (.csv)",lambda:self._tv_import("csv"))])
        iv.addLayout(self._make_row(import_box,"Import Target Values",self.btn_tv_imp));iv.addWidget(self._make_status("tv",import_box),0)
        self.btn_tg_imp=self._menu_button(import_box,"Import","TargetAddBtn",[("JSON (.json)",lambda:self._tg_import("json")),("CSV (.csv)",lambda:self._tg_import("csv"))])
        iv.addLayout(self._make_row(import_box,"Import Targets",self.btn_tg_imp));iv.addWidget(self._make_status("tg",import_box),0);iv.addStretch(1)
        tpl_box,tv=self._make_tab()
        self.btn_tpl_h_notes=self._menu_button(tpl_box,"Export","TargetMiniBtn",[("Markdown (.md)",lambda:self._export_human_template("notes","md")),("JSON (.json)",lambda:self._export_human_template("notes","json")),("Database (.db)",lambda:self._export_human_template("notes","db"))])
        tv.addLayout(self._make_row(tpl_box,"Notes Template",self.btn_tpl_h_notes))
        self.btn_tpl_h_cmds=self._menu_button(tpl_box,"Export","TargetMiniBtn",[("Markdown (.md)",lambda:self._export_human_template("commands","md")),("JSON (.json)",lambda:self._export_human_template("commands","json"))])
        tv.addLayout(self._make_row(tpl_box,"Commands Template",self.btn_tpl_h_cmds))
        self.btn_tpl_h_tv=self._menu_button(tpl_box,"Export","TargetMiniBtn",[("JSON (.json)",lambda:self._export_human_template("target_values","json")),("CSV (.csv)",lambda:self._export_human_template("target_values","csv"))])
        tv.addLayout(self._make_row(tpl_box,"Target Values Template",self.btn_tpl_h_tv))
        self.btn_tpl_h_tg=self._menu_button(tpl_box,"Export","TargetMiniBtn",[("JSON (.json)",lambda:self._export_human_template("targets","json")),("CSV (.csv)",lambda:self._export_human_template("targets","csv"))])
        tv.addLayout(self._make_row(tpl_box,"Targets Template",self.btn_tpl_h_tg))
        self.btn_tpl_h_all=self._button(tpl_box,"Export","TargetAddBtn",lambda:self._export_template_bundle("human"))
        tv.addLayout(self._make_row(tpl_box,"All Human Templates",self.btn_tpl_h_all));tv.addWidget(self._make_status("tpl",tpl_box),0);tv.addStretch(1)
        ai_box,av=self._make_tab()
        ai_note=QLabel("AI prompt templates explain LOYA Note import structure for each data type. Give one to AI with normal notes or data, then ask it to recreate the content in a LOYA-ready import format.",ai_box);ai_note.setObjectName("IEInfo");ai_note.setWordWrap(True)
        av.addWidget(ai_note,0)
        self.btn_tpl_ai_notes=self._button(ai_box,"Export","TargetMiniBtn",lambda:self._export_ai_template("notes"))
        av.addLayout(self._make_row(ai_box,"Notes AI Template",self.btn_tpl_ai_notes))
        self.btn_tpl_ai_cmds=self._button(ai_box,"Export","TargetMiniBtn",lambda:self._export_ai_template("commands"))
        av.addLayout(self._make_row(ai_box,"Commands AI Template",self.btn_tpl_ai_cmds))
        self.btn_tpl_ai_tv=self._button(ai_box,"Export","TargetMiniBtn",lambda:self._export_ai_template("target_values"))
        av.addLayout(self._make_row(ai_box,"Target Values AI Template",self.btn_tpl_ai_tv))
        self.btn_tpl_ai_tg=self._button(ai_box,"Export","TargetMiniBtn",lambda:self._export_ai_template("targets"))
        av.addLayout(self._make_row(ai_box,"Targets AI Template",self.btn_tpl_ai_tg))
        self.btn_tpl_ai_all=self._button(ai_box,"Export","TargetAddBtn",lambda:self._export_template_bundle("ai"))
        av.addLayout(self._make_row(ai_box,"All AI Templates",self.btn_tpl_ai_all));av.addWidget(self._make_status("tpl",ai_box),0);av.addStretch(1)
        self.tabs.addTab(export_box,"Export");self.tabs.addTab(import_box,"Import");self.tabs.addTab(tpl_box,"Template");self.tabs.addTab(ai_box,"AI Prompt Template")
        root.addWidget(self.tabs,1)
    def _make_tab(self):
        box=QFrame(self.tabs);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(12,12,12,12);v.setSpacing(5)
        return box,v
    def _make_row(self,parent,title,*widgets):
        r=QHBoxLayout();r.setSpacing(0)
        frame=QFrame(parent);frame.setObjectName("IEActionRow")
        row=QHBoxLayout(frame);row.setContentsMargins(10,5,10,5);row.setSpacing(8)
        lbl=QLabel(title,frame);lbl.setObjectName("IEActionTitle");lbl.setWordWrap(False)
        meta=QLabel(self._row_meta(title),frame);meta.setObjectName("IEActionMeta");meta.setWordWrap(False)
        row.addWidget(lbl,0)
        row.addWidget(meta,1)
        for w in widgets:row.addWidget(w,0)
        r.addWidget(frame,1)
        return r
    def _row_meta(self,title):
        return {"Export All":"Data ZIP","Export Notes":"DB / JSON / CSV ZIP / MD ZIP / PDF / one-note MD / HTML / PDF","Export Commands (Notes DB)":"MD / JSON / CSV","Export Target Values":"JSON / CSV","Export Targets":"JSON / CSV","Import All":"Data ZIP","Import Notes":"DB / JSON / CSV bundle / structured MD / human MD","Import Commands (Notes DB)":"MD / JSON / CSV","Import Target Values":"JSON / CSV","Import Targets":"JSON / CSV","Notes Template":"MD / JSON / DB","Commands Template":"MD / JSON","Target Values Template":"JSON / CSV","Targets Template":"JSON / CSV","All Human Templates":"ZIP bundle","Notes AI Template":"AI MD","Commands AI Template":"AI MD","Target Values AI Template":"AI MD","Targets AI Template":"AI MD","All AI Templates":"ZIP bundle"}.get(title,"")
    def _button(self,parent,text,obj,fn=None):
        btn=QToolButton(parent);btn.setObjectName(obj);btn.setText(text);btn.setCursor(Qt.CursorShape.PointingHandCursor);btn.setMinimumWidth(82)
        if callable(fn):btn.clicked.connect(fn)
        return btn
    def _menu_button(self,parent,text,obj,actions):
        btn=self._button(parent,text,obj);btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(btn)
        for title,fn in actions:
            a=QAction(title,self);a.triggered.connect(fn);menu.addAction(a)
        btn.setMenu(menu)
        return btn
    def _make_status(self,key,parent):
        lbl=QLabel("",parent);lbl.setObjectName("IEStatus");lbl.hide()
        self._status_labels.setdefault(key,[]).append(lbl)
        return lbl
    def _set_ie_status(self,key,text):
        text=_norm(text)
        for lbl in self._status_labels.get(key,[]):
            lbl.setText(text)
            lbl.setVisible(bool(text))
    def _ensure_db(self):
        try:self.db.ensure();return True
        except Exception as e:
            QMessageBox.warning(self,"Database",f"Database error:\n{e}")
            return False
    def _import_all_info(self,path):
        with zipfile.ZipFile(path,"r") as z:names=z.namelist()
        data=[n for n in names if n.replace("\\","/").startswith("Data/") and not n.endswith("/")]
        return len(data),"manifest.json" in names
    def _choose_import_all_mode(self,name,count):
        mb=QMessageBox(self);mb.setWindowTitle("Import All");mb.setText(f"Import all data from:\n{name}\n\nFiles: {count}\nChoose mode:")
        b1=mb.addButton("Merge",QMessageBox.ButtonRole.AcceptRole)
        b2=mb.addButton("Replace",QMessageBox.ButtonRole.DestructiveRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        if mb.clickedButton()==b1:return "merge"
        if mb.clickedButton()==b2:return "replace"
        return ""
    def _import_all(self):
        p,_=QFileDialog.getOpenFileName(self,"Import All",_abs(".."),"ZIP (*.zip)")
        if not p:return
        try:count,_=self._import_all_info(p)
        except Exception as e:
            self._set_ie_status("all_import",f"Invalid zip: {e}")
            QMessageBox.warning(self,"Import All",f"Invalid zip:\n{e}")
            return
        if count<=0:
            self._set_ie_status("all_import","Import failed: missing Data folder.")
            QMessageBox.warning(self,"Import All","This zip does not contain LOYA Data files.")
            return
        mode=self._choose_import_all_mode(os.path.basename(p),count)
        if not mode:
            self._set_ie_status("all_import","Import cancelled.")
            return
        prog=_progress(self,"Import All","Restoring data ...");prog.show()
        try:
            ok,msg=_update_backup.restore_data_backup(p,mode=mode,progress=prog)
        finally:
            prog.close()
        self._set_ie_status("all_import",msg)
        if ok:
            _log("[+]",f"Import all ok: {p} ({mode})")
            QMessageBox.information(self,"Import All",msg)
        else:
            _log("[!]",f"Import all failed: {p} ({msg})")
            QMessageBox.warning(self,"Import All",msg)
    def _warn_human_markdown_import(self):
        mb=QMessageBox(self);mb.setWindowTitle("Human Markdown Import");mb.setText("Human markdown does not keep LOYA command blocks.\nCommands may import as normal note text, so you may need to update them manually.\nYou can also use the Template tab for AI format guidance and ask AI to rewrite the note into LOYA structured markdown.")
        bok=mb.addButton("Continue",QMessageBox.ButtonRole.AcceptRole)
        mb.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        return mb.clickedButton()==bok
    def _ncn_import(self,kind):
        if not self._ensure_db():return
        human_md=(kind=="md_human")
        if human_md:
            if not self._warn_human_markdown_import():
                self._set_ie_status("ncn","Import cancelled.")
                return
            kind="md"
        flt={"db":"Database (*.db)","json":"JSON (*.json)","csv":"CSV Bundle (*.zip);;CSV (*.csv);;ZIP (*.zip)","md":"Markdown (*.md)"}[kind]
        if kind=="md":
            paths,_=QFileDialog.getOpenFileNames(self,"Import Human Markdown" if human_md else "Import Notes",_abs(".."),flt)
            if not paths:return
            try:
                res=self.ncn_imp.run_multi_markdown(self,paths)
                if not res:
                    self._set_ie_status("ncn","Import cancelled.")
                    return
                self._set_ie_status("ncn",f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)} bad:{res.get('bad',0)}")
                _log("[+]",f"NCN import ok {res}")
            except Exception as e:
                self._set_ie_status("ncn",f"Import failed: {e}")
                _log("[!]",f"NCN import failed ({e})")
            return
        p,_=QFileDialog.getOpenFileName(self,"Import Notes",_abs(".."),flt)
        if not p:return
        try:
            res=self.ncn_imp.run(self,kind,p)
            if not res:
                self._set_ie_status("ncn","Import cancelled.")
                return
            self._set_ie_status("ncn",f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)} bad:{res.get('bad',0)}")
            _log("[+]",f"NCN import ok {res}")
        except Exception as e:
            self._set_ie_status("ncn",f"Import failed: {e}")
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
        elif kind=="pdf":
            p,_=QFileDialog.getSaveFileName(self,"Export Notes PDF",os.path.join(base,f"LOYA_Notes_{_now()}.pdf"),"PDF (*.pdf)")
        else:
            p,_=QFileDialog.getSaveFileName(self,"Export CSV",os.path.join(base,f"Note_LOYA_export_{_now()}.zip"),"ZIP (*.zip)")
        if not p:return
        ok=self.ncn_exp.run(self,kind,p)
        if ok:self._set_ie_status("ncn",f"Exported: {os.path.basename(p)}")
    def _commands_export(self,kind):
        if not self._ensure_db():return
        rows=self.db.read_table("CommandsNotes")
        if not rows:
            QMessageBox.information(self,"Commands Export","No CommandsNotes rows found.")
            return
        base=_abs("..")
        if kind=="md":
            p,_=QFileDialog.getSaveFileName(self,"Export Commands",os.path.join(base,f"CommandsNotes_{_now()}.md"),"Markdown (*.md)")
        elif kind=="json":
            p,_=QFileDialog.getSaveFileName(self,"Export Commands",os.path.join(base,f"CommandsNotes_{_now()}.json"),"JSON (*.json)")
        else:
            p,_=QFileDialog.getSaveFileName(self,"Export Commands",os.path.join(base,f"CommandsNotes_{_now()}.csv"),"CSV (*.csv)")
        if not p:return
        try:
            if kind=="md":
                with open(p,"w",encoding="utf-8") as f:f.write(_commands_notes_to_markdown(rows))
            elif kind=="json":
                _write_json(p,{"CommandsNotes":rows})
            else:
                fields=["note_name","category","sub_category","command","tags","description","created_at","updated_at"]
                with open(p,"w",encoding="utf-8",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
                    for r in rows:w.writerow({k:_norm(r.get(k,"")) for k in fields})
            self._set_ie_status("cmd",f"Exported: {os.path.basename(p)}")
            _log("[+]",f"CommandsNotes export ok ({kind}) -> {p}")
        except Exception as e:
            self._set_ie_status("cmd",f"Export failed: {e}")
            _log("[!]",f"CommandsNotes export failed ({e})")
            QMessageBox.warning(self,"Export Commands",f"Export failed:\n{e}")
    def _commands_incoming(self,kind,path):
        if kind=="md":incoming=self.db.parse_incoming_markdown(path)
        elif kind=="json":incoming=self.db.parse_incoming_json(path)
        else:incoming=self.db.parse_incoming_csv_zip(path)
        rows=incoming.get("CommandsNotes") if isinstance(incoming,dict) else []
        return {"CommandsNotes":[r for r in (rows or []) if isinstance(r,dict)]}
    def _commands_import_one(self,kind,path):
        incoming=self._commands_incoming(kind,path)
        if not incoming.get("CommandsNotes"):
            return {"added":0,"replaced":0,"overwritten":0,"skipped":0,"bad":1}
        existing=self.db.load_existing_maps()
        plan=self.db.build_import_plan(incoming,existing)
        return self.ncn_imp._apply_import(self,plan,incoming,"commands",os.path.basename(path))
    def _commands_import(self,kind):
        if not self._ensure_db():return
        flt={"md":"Markdown (*.md)","json":"JSON (*.json)","csv":"CSV (*.csv)"}[kind]
        if kind=="md":
            paths,_=QFileDialog.getOpenFileNames(self,"Import Commands",_abs(".."),flt)
            if not paths:return
            total={"added":0,"replaced":0,"overwritten":0,"skipped":0,"bad":0}
            for p in paths:
                try:
                    res=self._commands_import_one(kind,p)
                    if not res:continue
                    for k in total.keys():total[k]+=int(res.get(k,0) or 0)
                except Exception as e:
                    self._set_ie_status("cmd",f"Import failed: {e}")
                    _log("[!]",f"CommandsNotes import failed ({e})")
                    return
            self._set_ie_status("cmd",f"Imported: +{total.get('added',0)} rep:{total.get('replaced',0)} ow:{total.get('overwritten',0)} skip:{total.get('skipped',0)} bad:{total.get('bad',0)}")
            _log("[+]",f"CommandsNotes import ok {total}")
            return
        p,_=QFileDialog.getOpenFileName(self,"Import Commands",_abs(".."),flt)
        if not p:return
        try:
            res=self._commands_import_one(kind,p)
            if not res:
                self._set_ie_status("cmd","Import cancelled.")
                return
            self._set_ie_status("cmd",f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)} bad:{res.get('bad',0)}")
            _log("[+]",f"CommandsNotes import ok {res}")
        except Exception as e:
            self._set_ie_status("cmd",f"Import failed: {e}")
            _log("[!]",f"CommandsNotes import failed ({e})")
    def _export_all(self):
        base=_abs("..")
        p,_=QFileDialog.getSaveFileName(self,"Export All",os.path.join(base,f"LOYA_All_export_{_now()}.zip"),"ZIP (*.zip)")
        if not p:return
        prog=_progress(self,"Export All","Collecting data ...");prog.show()
        try:
            data_dir=_data_dir();out_abs=os.path.abspath(p);files=[]
            if os.path.isdir(data_dir):
                for b,_,names in os.walk(data_dir):
                    for n in names:
                        src=os.path.abspath(os.path.join(b,n))
                        if src==out_abs or not os.path.isfile(src):continue
                        rel=os.path.relpath(src,data_dir).replace("\\","/")
                        files.append((src,f"Data/{rel}"))
            ident=_get_app_identity()
            meta={"type":"LOYA Note Export All","format_version":1,"created_at":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),"app_version":_norm(ident.get("display_version","")) or _norm(ident.get("version","")),"files":[arc for _,arc in files]}
            os.makedirs(os.path.dirname(out_abs),exist_ok=True)
            total=max(1,len(files))
            with zipfile.ZipFile(out_abs,"w",compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json",json.dumps(meta,ensure_ascii=False,indent=2))
                for i,(src,arc) in enumerate(files):
                    _set_prog(prog,int(((i+1)*100)/total),f"Writing {os.path.basename(src)} ...")
                    z.write(src,arcname=arc)
            self._set_ie_status("all",f"Exported: {os.path.basename(out_abs)}")
            _log("[+]",f"Export all -> {out_abs}")
        except Exception as e:
            self._set_ie_status("all",f"Export failed: {e}")
            _log("[!]",f"Export all failed ({e})")
            QMessageBox.warning(self,"Export All",f"Export failed:\n{e}")
        finally:
            prog.close()
    def _save_template_text(self,title,default_name,flt,text):
        p,_=QFileDialog.getSaveFileName(self,title,os.path.join(_abs(".."),default_name),flt)
        if not p:return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True)
            with open(p,"w",encoding="utf-8",newline="") as f:f.write(text if text.endswith("\n") else text+"\n")
            self._set_ie_status("tpl",f"Template saved: {os.path.basename(p)}")
            _log("[+]",f"Template export -> {p}")
            QMessageBox.information(self,"Template","Template exported.")
        except Exception as e:
            self._set_ie_status("tpl",f"Export failed: {e}")
            _log("[!]",f"Template export failed ({e})")
            QMessageBox.warning(self,"Template",f"Export failed:\n{e}")
    def _human_template_text(self,kind,fmt):
        if kind=="notes" and fmt=="md":return _import_template_markdown()
        if kind=="notes" and fmt=="json":return _human_notes_json_template()
        if kind=="commands" and fmt=="md":return _human_commands_md_template()
        if kind=="commands" and fmt=="json":return _human_commands_json_template()
        if kind=="targets" and fmt=="json":return _human_targets_json_template()
        if kind=="targets" and fmt=="csv":return _human_targets_csv_template()
        if kind=="target_values" and fmt=="json":return _human_target_values_json_template()
        if kind=="target_values" and fmt=="csv":return _human_target_values_csv_template()
        return ""
    def _human_template_meta(self,kind,fmt):
        names={"notes":"LOYA_Notes_Template","commands":"LOYA_Commands_Template","targets":"LOYA_Targets_Template","target_values":"LOYA_TargetValues_Template"}
        labels={"notes":"Notes","commands":"Commands","targets":"Targets","target_values":"Target Values"}
        ext={"md":"md","json":"json","csv":"csv","db":"db"}.get(fmt,fmt)
        flt={"md":"Markdown (*.md)","json":"JSON (*.json)","csv":"CSV (*.csv)","db":"Database (*.db)"}.get(fmt,"All Files (*)")
        return f"Export {labels.get(kind,'Template')} Template",f"{names.get(kind,'LOYA_Template')}.{ext}",flt
    def _export_human_notes_db_template(self):
        title,default,flt=self._human_template_meta("notes","db")
        p,_=QFileDialog.getSaveFileName(self,title,os.path.join(_abs(".."),default),flt)
        if not p:return
        try:
            if os.path.isfile(p):os.remove(p)
            db=Note_LOYA_Database(p);db.ensure()
            now=datetime.utcnow().isoformat()
            con=sqlite3.connect(p);cur=con.cursor()
            cur.execute("INSERT INTO Notes(note_name,group_name,content,created_at,updated_at) VALUES(?,?,?,?,?)",("Example Note","Examples","<h1>Example Note</h1><p>Write note content here.</p>",now,now))
            cur.execute("INSERT INTO CommandsNotes(note_name,category,sub_category,command,tags,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",("Example Note","General","Shell","echo hello","demo","Example command",now,now))
            con.commit();con.close()
            self._set_ie_status("tpl",f"Template saved: {os.path.basename(p)}")
            _log("[+]",f"DB template export -> {p}")
            QMessageBox.information(self,"Template","Template exported.")
        except Exception as e:
            self._set_ie_status("tpl",f"Export failed: {e}")
            _log("[!]",f"DB template export failed ({e})")
            QMessageBox.warning(self,"Template",f"Export failed:\n{e}")
    def _export_human_template(self,kind,fmt):
        if kind=="notes" and fmt=="db":
            self._export_human_notes_db_template();return
        title,default,flt=self._human_template_meta(kind,fmt)
        text=self._human_template_text(kind,fmt)
        if not text:
            QMessageBox.warning(self,"Template","Template is not available.")
            return
        self._save_template_text(title,default,flt,text)
    def _ai_template_text(self,kind):
        if kind=="notes":return _ai_notes_template()
        if kind=="commands":return _ai_commands_template()
        if kind=="targets":return _ai_targets_template()
        if kind=="target_values":return _ai_target_values_template()
        return ""
    def _export_ai_template(self,kind):
        names={"notes":"LOYA_Notes_AI_Template.md","commands":"LOYA_Commands_AI_Template.md","targets":"LOYA_Targets_AI_Template.md","target_values":"LOYA_TargetValues_AI_Template.md"}
        labels={"notes":"Notes","commands":"Commands","targets":"Targets","target_values":"Target Values"}
        text=self._ai_template_text(kind)
        if not text:
            QMessageBox.warning(self,"Template","Template is not available.")
            return
        self._save_template_text(f"Export {labels.get(kind,'AI')} AI Template",names.get(kind,"LOYA_AI_Template.md"),"Markdown (*.md)",text)
    def _export_template_bundle(self,mode):
        ai=mode=="ai"
        default="LOYA_AI_Templates.zip" if ai else "LOYA_Human_Templates.zip"
        p,_=QFileDialog.getSaveFileName(self,"Export AI Templates" if ai else "Export Human Templates",os.path.join(_abs(".."),default),"ZIP (*.zip)")
        if not p:return
        try:
            entries=[]
            if ai:
                entries=[("Notes_AI_Template.md",_ai_notes_template()),("Commands_AI_Template.md",_ai_commands_template()),("Targets_AI_Template.md",_ai_targets_template()),("TargetValues_AI_Template.md",_ai_target_values_template())]
            else:
                entries=[("Notes_Template.md",_import_template_markdown()),("Notes_Template.json",_human_notes_json_template()),("Commands_Template.md",_human_commands_md_template()),("Commands_Template.json",_human_commands_json_template()),("Targets_Template.json",_human_targets_json_template()),("Targets_Template.csv",_human_targets_csv_template()),("TargetValues_Template.json",_human_target_values_json_template()),("TargetValues_Template.csv",_human_target_values_csv_template())]
            with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for name,text in entries:z.writestr(name,(text if text.endswith("\n") else text+"\n").encode("utf-8"))
            self._set_ie_status("tpl",f"Templates saved: {os.path.basename(p)}")
            _log("[+]",f"Template bundle export -> {p}")
            QMessageBox.information(self,"Template","Templates exported.")
        except Exception as e:
            self._set_ie_status("tpl",f"Export failed: {e}")
            _log("[!]",f"Template bundle export failed ({e})")
            QMessageBox.warning(self,"Template",f"Export failed:\n{e}")
    def _export_template(self):
        self._export_human_template("notes","md")
    def _notes_export(self,kind):
        if not self._ensure_db():return
        notes=self.db.list_note_refs()
        if not notes:
            QMessageBox.information(self,"Notes Export","No notes found.")
            return
        labels=[];label_map={}
        for it in notes:
            name=_norm(it.get("note_name",""))
            if not name:continue
            grp=_norm(it.get("group_name",""))
            label=f"{grp} | {name}" if grp else f"Ungrouped | {name}"
            labels.append(label);label_map[label]=name
        name_label,ok=QInputDialog.getItem(self,"Export Note","Note",labels,0,False)
        if not ok or not name_label:return
        name=label_map.get(name_label,"")
        if not name:return
        base=_abs("..")
        safe=_safe_filename(name,fallback="note")
        if kind=="md":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (Markdown)",os.path.join(base,f"{safe}.md"),"Markdown (*.md)")
            if not p:return
            try:
                self.db.export_note_markdown(name,p)
                self._set_ie_status("note",f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export markdown -> {p}")
            except Exception as e:
                self._set_ie_status("note",f"Export failed: {e}")
                _log("[!]",f"Note export markdown failed ({e})")
                QMessageBox.warning(self,"Export",f"Export failed:\n{e}")
        elif kind=="md_human":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (Human Markdown)",os.path.join(base,f"{safe}.md"),"Markdown (*.md)")
            if not p:return
            try:
                self.db.export_note_markdown_human(name,p)
                self._set_ie_status("note",f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export human markdown -> {p}")
            except Exception as e:
                self._set_ie_status("note",f"Export failed: {e}")
                _log("[!]",f"Note export human markdown failed ({e})")
                QMessageBox.warning(self,"Export",f"Export failed:\n{e}")
        elif kind=="html":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (HTML)",os.path.join(base,f"{safe}.html"),"HTML (*.html)")
            if not p:return
            try:
                self.db.export_note_html(name,p)
                self._set_ie_status("note",f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export html -> {p}")
            except Exception as e:
                self._set_ie_status("note",f"Export failed: {e}")
                _log("[!]",f"Note export html failed ({e})")
                QMessageBox.warning(self,"Export",f"Export failed:\n{e}")
        elif kind=="pdf":
            p,_=QFileDialog.getSaveFileName(self,"Export Note (PDF)",os.path.join(base,f"{safe}.pdf"),"PDF (*.pdf)")
            if not p:return
            try:
                self.db.export_note_pdf(name,p)
                self._set_ie_status("note",f"Exported: {os.path.basename(p)}")
                _log("[+]",f"Note export pdf -> {p}")
            except Exception as e:
                self._set_ie_status("note",f"Export failed: {e}")
                _log("[!]",f"Note export pdf failed ({e})")
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
        finally:
            prog.close()
        dups=[{"table":"TargetValues","key":_norm(d.get("key","")),"existing":f'{_norm(d.get("existing_key",""))}:{int((d.get("existing") or {}).get("priority",(d.get("existing") or {}).get("value",0)) or 0)}',"incoming":f'{_norm(d.get("key",""))}:{int((d.get("incoming") or {}).get("priority",(d.get("incoming") or {}).get("value",0)) or 0)}',"in_cmd":""} for d in (plan.get("dups") or [])]
        dlg=_ImportPreviewDialog(self,"Import Preview",plan,dups,source_label=os.path.basename(p))
        if dlg.exec()!=QDialog.DialogCode.Accepted:
            self._set_ie_status("tv","Import cancelled.")
            return
        decisions=dlg.decisions()
        res=self.tv.apply_plan(base,plan,decisions)
        self.tv.save(base)
        self._set_ie_status("tv",f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)}")
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
        self._set_ie_status("tv",f"Exported: {os.path.basename(p)}")
        _log("[+]",f"TargetValues export ok ({kind}) -> {p}")
    def _tg_import(self,kind="json"):
        flt={"json":"JSON (*.json)","csv":"CSV (*.csv)"}[kind]
        p,_=QFileDialog.getOpenFileName(self,"Import Targets",_abs(".."),flt)
        if not p:return
        base=self.tg.load()
        prog=_progress(self,"Import","Loading ...");prog.show()
        try:
            incoming=self.tg.parse_json(p) if kind=="json" else self.tg.parse_csv(p)
            plan=self.tg.build_plan(incoming,base)
        finally:
            prog.close()
        dups=[{"table":"Targets","key":_norm(d.get("key","")),"existing":self.tg._summ(d.get("existing")),"incoming":self.tg._summ(d.get("incoming")),"in_cmd":""} for d in (plan.get("dups") or [])]
        dlg=_ImportPreviewDialog(self,"Import Preview",plan,dups,source_label=os.path.basename(p))
        if dlg.exec()!=QDialog.DialogCode.Accepted:
            self._set_ie_status("tg","Import cancelled.")
            return
        decisions=dlg.decisions()
        base,res=self.tg.apply_plan(base,plan,decisions)
        self.tg.save(base)
        self._set_ie_status("tg",f"Imported: +{res.get('added',0)} rep:{res.get('replaced',0)} ow:{res.get('overwritten',0)} skip:{res.get('skipped',0)}")
        _log("[+]",f"Targets import ok {res}")
    def _tg_export(self,kind="json"):
        data=self.tg.load()
        if kind=="json":
            p,_=QFileDialog.getSaveFileName(self,"Export Targets",os.path.join(_abs(".."),f"Targets_{_now()}.json"),"JSON (*.json)")
        else:
            p,_=QFileDialog.getSaveFileName(self,"Export Targets",os.path.join(_abs(".."),f"Targets_{_now()}.csv"),"CSV (*.csv)")
        if not p:return
        if kind=="json":self.tg.export_json(p,data)
        else:self.tg.export_csv(p,data)
        self._set_ie_status("tg",f"Exported: {os.path.basename(p)}")
        _log("[+]",f"Targets export ok ({kind}) -> {p}")
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
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        top=QHBoxLayout();top.setContentsMargins(8,8,8,0);top.setSpacing(4)
        t=QLabel("Security",self);t.setObjectName("PageTitle");top.addWidget(t,1);root.addLayout(top)
        box=QFrame(self);box.setObjectName("ContentFrame")
        v=QVBoxLayout(box);v.setContentsMargins(8,6,8,8);v.setSpacing(4)
        info=QLabel("Protect access and encrypt the database at rest.",box);info.setObjectName("PageSubTitle");info.setWordWrap(True)
        v.addWidget(info,0)
        row1=QHBoxLayout();row1.setSpacing(4)
        self.chk_lock=QCheckBox("Enable app lock on start",box)
        self.btn_set_pin=QToolButton(box);self.btn_set_pin.setObjectName("TargetAddBtn");self.btn_set_pin.setText("Set/Change PIN")
        row1.addWidget(self.chk_lock,0);row1.addWidget(self.btn_set_pin,0);row1.addStretch(1)
        v.addLayout(row1)
        self.pin_status=QLabel("",box);self.pin_status.setObjectName("PageSubTitle")
        v.addWidget(self.pin_status,0)
        row2=QHBoxLayout();row2.setSpacing(4)
        self.chk_enc=QCheckBox("Enable database encryption (at rest)",box)
        row2.addWidget(self.chk_enc,0);row2.addStretch(1)
        v.addLayout(row2)
        self.enc_status=QLabel("",box);self.enc_status.setObjectName("PageSubTitle")
        v.addWidget(self.enc_status,0)
        self.status=QLabel("",box);self.status.setObjectName("PageSubTitle")
        v.addWidget(self.status,0)
        self.status.hide()
        root.addWidget(box,0)
        root.addStretch(1)
        self.btn_set_pin.clicked.connect(self._set_pin)
        self.chk_lock.stateChanged.connect(self._toggle_lock)
        self.chk_enc.stateChanged.connect(self._toggle_enc)
        QTimer.singleShot(0,self._load)
    def _set_status(self,msg):
        text=_norm(msg)
        self.status.setText(text)
        self.status.setVisible(bool(text))
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
        self.btn_ie=QToolButton(self.sidebar);self.btn_ie.setObjectName("NavBtn");self.btn_ie.setText("Import && Export");self.btn_ie.setCheckable(True)
        self.btn_tags=QToolButton(self.sidebar);self.btn_tags.setObjectName("NavBtn");self.btn_tags.setText("Tags");self.btn_tags.setCheckable(True)
        self.btn_security=QToolButton(self.sidebar);self.btn_security.setObjectName("NavBtn");self.btn_security.setText("Security");self.btn_security.setCheckable(True)
        self.btn_update=QToolButton(self.sidebar);self.btn_update.setObjectName("NavBtn");self.btn_update.setText("Update");self.btn_update.setCheckable(True)
        self.btn_recycle=QToolButton(self.sidebar);self.btn_recycle.setObjectName("NavBtn");self.btn_recycle.setText("Recycle Bin");self.btn_recycle.setCheckable(True)
        self.btn_backup.clicked.connect(lambda:self._nav(0))
        self.btn_ie.clicked.connect(lambda:self._nav(1))
        self.btn_tags.clicked.connect(lambda:self._nav(2))
        self.btn_security.clicked.connect(lambda:self._nav(3))
        self.btn_update.clicked.connect(lambda:self._nav(4))
        self.btn_recycle.clicked.connect(lambda:self._nav(5))
        sv.addWidget(self.btn_backup,0);sv.addWidget(self.btn_ie,0);sv.addWidget(self.btn_tags,0);sv.addWidget(self.btn_security,0);sv.addWidget(self.btn_update,0);sv.addWidget(self.btn_recycle,0);sv.addStretch(1)
        self.stack=_CurrentPageStack(self);self.stack.setObjectName("Stack")
        self.page_backup=_BackupPage(self.stack)
        self.page_ie=_ImportExportPage(self.stack)
        self.page_tags=_TagsPage(self.stack)
        self.page_security=_SecurityPage(self.stack)
        self.page_update=_UpdatePage(self.stack)
        self.page_recycle=_RecycleBinPage(self.stack)
        self.stack.addWidget(self.page_backup);self.stack.addWidget(self.page_ie);self.stack.addWidget(self.page_tags);self.stack.addWidget(self.page_security);self.stack.addWidget(self.page_update);self.stack.addWidget(self.page_recycle)
        self.scroll=QScrollArea(self);self.scroll.setObjectName("SettingsScroll")
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.stack)
        self.scroll.viewport().installEventFilter(self)
        root.addWidget(self.sidebar,0);root.addWidget(self.scroll,1)
        QTimer.singleShot(0,self._sync_button_sizes)
        QTimer.singleShot(0,self._sync_stack_height)
        QTimer.singleShot(0,self._scroll_top)
        self._nav(0)
    def eventFilter(self,obj,e):
        try:
            if obj is self.scroll.viewport() and e is not None and e.type()==QEvent.Type.Resize:self._schedule_stack_sync()
        except Exception:pass
        return super().eventFilter(obj,e)
    def _sync_stack_height(self):
        try:
            view=self.scroll.viewport()
            view_w=max(0,int(view.width()))
            view_h=max(0,int(view.height()))
        except Exception:
            view_w=0;view_h=0
        cur=self.stack.currentWidget()
        hint=0;used=0;hfw=0
        if cur is not None:
            lay=cur.layout()
            if lay is not None:
                try:lay.activate()
                except Exception:pass
                if view_w>0:
                    try:
                        if lay.hasHeightForWidth():hfw=int(lay.totalHeightForWidth(view_w))
                    except Exception:pass
                try:
                    for i in range(lay.count()):
                        it=lay.itemAt(i)
                        if it is None or it.spacerItem() is not None:continue
                        g=it.geometry()
                        used=max(used,int(g.y()+g.height()))
                except Exception:pass
            if used>0:hint=used
            else:
                if hfw>0:hint=max(hint,hfw)
                try:hint=max(hint,int(cur.minimumSizeHint().height()))
                except Exception:pass
                try:hint=max(hint,int(cur.sizeHint().height()))
                except Exception:pass
        expand_pages=(_BackupPage,_ImportExportPage,_TagsPage,_UpdatePage,_RecycleBinPage)
        target=(max(view_h,0) if isinstance(cur,expand_pages) else max(hint,0))
        width=max(view_w,0)
        if width>0 and (self.stack.width()!=width or self.stack.height()!=target):self.stack.setFixedSize(width,target)
    def _scroll_top(self):
        try:self.scroll.verticalScrollBar().setValue(0)
        except Exception:pass
        try:self.scroll.horizontalScrollBar().setValue(0)
        except Exception:pass
    def _schedule_scroll_top(self):
        QTimer.singleShot(0,self._scroll_top)
    def _schedule_stack_sync(self):
        QTimer.singleShot(0,self._sync_stack_height)
    def on_page_activated(self):
        self._schedule_stack_sync()
        self._schedule_scroll_top()
    def showEvent(self,e):
        try:super().showEvent(e)
        except Exception:pass
        self._schedule_stack_sync()
        self._schedule_scroll_top()
    def resizeEvent(self,e):
        try:super().resizeEvent(e)
        except Exception:pass
        self._schedule_stack_sync()
    def _nav(self,i):
        self.btn_backup.blockSignals(True);self.btn_ie.blockSignals(True);self.btn_tags.blockSignals(True);self.btn_security.blockSignals(True);self.btn_update.blockSignals(True);self.btn_recycle.blockSignals(True)
        self.btn_backup.setChecked(i==0);self.btn_ie.setChecked(i==1);self.btn_tags.setChecked(i==2);self.btn_security.setChecked(i==3);self.btn_update.setChecked(i==4);self.btn_recycle.setChecked(i==5)
        self.btn_backup.blockSignals(False);self.btn_ie.blockSignals(False);self.btn_tags.blockSignals(False);self.btn_security.blockSignals(False);self.btn_update.blockSignals(False);self.btn_recycle.blockSignals(False)
        self.stack.setCurrentIndex(i)
        if i==0:
            try:self.page_backup._schedule_table_refresh()
            except Exception:pass
        elif i==4:
            try:self.page_update._load_all()
            except Exception:pass
        elif i==5:
            try:self.page_recycle._load()
            except Exception:pass
        self._schedule_stack_sync()
        QTimer.singleShot(30,self._sync_stack_height)
        self._schedule_scroll_top()
    def _sync_button_sizes(self):
        nav=[b for b in self.findChildren(QToolButton) if b.objectName()=="NavBtn" and _norm(b.text())]
        act=[b for b in self.findChildren(QToolButton) if b.objectName() in ("TargetAddBtn","TargetMiniBtn","TargetSaveBtn","TargetCancelBtn") and _norm(b.text())]
        if nav:
            fm=QFontMetrics(nav[0].font());w=max(fm.horizontalAdvance(_norm(b.text())) for b in nav)+40
            if w<170:w=170
            for b in nav:b.setFixedHeight(44);b.setFixedWidth(w)
        if act:
            for b in act:
                fm=QFontMetrics(b.font());w=fm.horizontalAdvance(_norm(b.text()))+34
                if w<118:w=118
                b.setFixedHeight(30)
                b.setFixedWidth(w)
