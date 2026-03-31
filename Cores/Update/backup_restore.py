import json,logging,os,shutil,tempfile,time,zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from . import update_helpers as _helpers
from . import update_service as _service
_DATA_LOGGER=None
_DOWNGRADE_LOGGER=None
_SKIP_DIR_NAMES={"Data","Logs","Backups",".venv_windows",".venv_linux","__pycache__",".git",".pytest_cache",".mypy_cache",".ruff_cache",".idea",".vs",".vscode"}
_SKIP_FILE_NAMES={"Thumbs.db",".DS_Store"}
_SKIP_FILE_SUFFIXES={".pyc",".pyo",".tmp",".temp",".log",".bak",".old",".swp",".swo"}
def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def _stamp():
    return time.strftime("%Y-%m-%d_%H-%M-%S",time.gmtime())
def _root_dir(root_dir=None):
    p=Path(root_dir) if root_dir else _helpers.root_dir()
    return p.resolve()
def _data_dir(root_dir=None):
    return _root_dir(root_dir).joinpath("Data")
def _backups_dir(root_dir=None,out_dir=None):
    p=Path(out_dir) if out_dir else _root_dir(root_dir).joinpath("Backups")
    p.mkdir(parents=True,exist_ok=True)
    return p.resolve()
def old_versions_dir(root_dir=None,out_dir=None):
    p=Path(out_dir) if out_dir else _root_dir(root_dir).joinpath("Cores","Update","OldVersions")
    p.mkdir(parents=True,exist_ok=True)
    return p.resolve()
def _logs_dir(root_dir=None):
    p=_root_dir(root_dir).joinpath("Logs")
    p.mkdir(parents=True,exist_ok=True)
    return p.resolve()
def _safe_name(text,fallback):
    raw="".join(ch if ch.isalnum() or ch in ("-","_",".") else "_" for ch in str(text or "").strip())
    raw=raw.strip("._")
    return raw or fallback
def _within_root(path,root):
    try:return os.path.commonpath([str(Path(path).resolve()),str(Path(root).resolve())])==str(Path(root).resolve())
    except Exception:return False
def _skip_dir(name):
    return str(name or "").strip() in _SKIP_DIR_NAMES
def _skip_file(name):
    base=str(name or "").strip()
    if not base:return True
    if base in _SKIP_FILE_NAMES:return True
    if base.endswith("~"):return True
    low=base.lower()
    return any(low.endswith(sfx) for sfx in _SKIP_FILE_SUFFIXES)
def _should_skip_rel(rel_path):
    rel=str(rel_path or "").replace("\\","/").strip("/")
    if not rel:return False
    parts=[p for p in rel.split("/") if p]
    if any(_skip_dir(p) for p in parts):return True
    if parts[:3]==["Cores","Update","OldVersions"]:return True
    return _skip_file(parts[-1])
def _iter_project_files(root_dir=None):
    root=_root_dir(root_dir)
    for base,dirs,files in os.walk(root):
        rel_dir=os.path.relpath(base,root)
        if rel_dir==".":
            rel_dir=""
        dirs[:]=[d for d in dirs if not _should_skip_rel(os.path.join(rel_dir,d))]
        for fn in files:
            rel=os.path.join(rel_dir,fn) if rel_dir else fn
            if _should_skip_rel(rel):continue
            src=root.joinpath(rel)
            if src.is_file():yield src,rel.replace("\\","/")
def _logger(name,path):
    lg=logging.getLogger(name);lg.setLevel(logging.INFO)
    fp=os.path.abspath(str(path))
    for h in list(lg.handlers):
        try:
            if getattr(h,"baseFilename","") and os.path.abspath(h.baseFilename)==fp:return lg
        except Exception:
            pass
    h=RotatingFileHandler(fp,maxBytes=1024*1024,backupCount=5,encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s","%Y-%m-%d %H:%M:%S"))
    lg.addHandler(h);return lg
def _update_log(root_dir=None):
    global _DATA_LOGGER
    if _DATA_LOGGER is None:_DATA_LOGGER=_logger("UpdateService",_logs_dir(root_dir).joinpath("Update_log.log"))
    return _DATA_LOGGER
def _downgrade_log(root_dir=None):
    global _DOWNGRADE_LOGGER
    if _DOWNGRADE_LOGGER is None:_DOWNGRADE_LOGGER=_logger("DowngradeService",_logs_dir(root_dir).joinpath("Downgrade_log.log"))
    return _DOWNGRADE_LOGGER
def _log_update(tag,msg,root_dir=None):
    try:_update_log(root_dir).info(f"{tag} {msg}")
    except Exception:pass
def _log_downgrade(tag,msg,root_dir=None):
    try:_downgrade_log(root_dir).info(f"{tag} {msg}")
    except Exception:pass
def create_data_backup(progress=None,prefix="Backup",root_dir=None,out_dir=None):
    bdir=_backups_dir(root_dir,out_dir)
    data_dir=_data_dir(root_dir)
    name=f"{_safe_name(prefix,'Backup')}_{_stamp()}.zip"
    out=bdir.joinpath(name)
    if progress:
        try:progress.setValue(10);progress._label.setText("Collecting Data/ ...")
        except Exception:pass
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        if data_dir.is_dir():
            for base,_,files in os.walk(data_dir):
                for fn in files:
                    p=Path(base).joinpath(fn)
                    rel=os.path.relpath(p,data_dir).replace("\\","/")
                    z.write(str(p),arcname=f"Data/{rel}")
    if progress:
        try:progress.setValue(100);progress._label.setText("Done.")
        except Exception:pass
    _log_update("[+]",f"Data backup created: {out}",root_dir)
    return str(out)
def restore_data_backup(zip_path,mode="merge",progress=None,root_dir=None):
    if not zip_path or not os.path.isfile(zip_path):return False,"Backup not found"
    if mode not in ("merge","replace"):return False,"Invalid mode"
    tmp=tempfile.mkdtemp(prefix="loya_restore_")
    try:
        if progress:
            try:progress.setValue(10);progress._label.setText("Extracting ...")
            except Exception:pass
        with zipfile.ZipFile(zip_path,"r") as z:z.extractall(tmp)
        src=os.path.join(tmp,"Data")
        dst=str(_data_dir(root_dir))
        if not os.path.isdir(src):return False,"Missing Data/ in backup"
        if progress:
            try:progress.setValue(40);progress._label.setText("Restoring Data/ ...")
            except Exception:pass
        for base,_,files in os.walk(src):
            rel=os.path.relpath(base,src)
            td=os.path.join(dst,rel) if rel!="." else dst
            os.makedirs(td,exist_ok=True)
            for fn in files:
                dp=os.path.join(td,fn)
                if mode=="merge" and os.path.exists(dp):continue
                shutil.copy2(os.path.join(base,fn),dp)
        if progress:
            try:progress.setValue(100);progress._label.setText("Done.")
            except Exception:pass
        _log_downgrade("[+]",f"Data restore ok: {zip_path} mode={mode}",root_dir)
        return True,"Restore done. Restart app if needed."
    except Exception as e:
        _log_downgrade("[!]",f"Data restore failed: {zip_path} ({e})",root_dir)
        return False,f"Restore failed: {e}"
    finally:
        try:shutil.rmtree(tmp,ignore_errors=True)
        except Exception:pass
def list_code_snapshots(root_dir=None,out_dir=None):
    rows=[]
    sdir=old_versions_dir(root_dir,out_dir)
    try:
        for n in os.listdir(sdir):
            if not n.lower().endswith(".zip"):continue
            p=sdir.joinpath(n)
            try:
                st=p.stat()
                rows.append((str(p),st.st_mtime,st.st_size))
            except Exception:
                pass
    except Exception:
        pass
    rows.sort(key=lambda x:x[1],reverse=True)
    return rows
def trim_code_snapshots(keep=2,root_dir=None,out_dir=None):
    try:keep=max(0,int(keep))
    except Exception:keep=2
    rows=list_code_snapshots(root_dir,out_dir)
    ok=0;bad=0
    allowed=str(old_versions_dir(root_dir,out_dir))
    for p,_,_ in rows[keep:]:
        try:
            if p and os.path.isfile(p) and os.path.dirname(os.path.abspath(p))==os.path.abspath(allowed):
                os.remove(p);ok+=1;_log_update("[*]",f"Old snapshot removed: {p}",root_dir)
            else:bad+=1
        except Exception:bad+=1
    return ok,bad
def create_code_snapshot(version="",reason="update",keep=2,progress=None,root_dir=None,out_dir=None):
    root=_root_dir(root_dir)
    sdir=old_versions_dir(root_dir,out_dir)
    ver=_helpers.coerce_local_version(version,_service.get_app_version())
    tag=_safe_name(reason,"update")
    name=f"CodeSnapshot_{_safe_name(ver,'0.0.0')}_{tag}_{_stamp()}.zip"
    out=sdir.joinpath(name)
    meta={"version":ver,"reason":tag,"created_at":_utc_now(),"source_repo":_helpers.OFFICIAL_SOURCE_REPO}
    if progress:
        try:progress.setValue(5);progress._label.setText("Collecting code files ...")
        except Exception:pass
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("__snapshot__/metadata.json",json.dumps(meta,ensure_ascii=False,indent=2))
        total=0
        for src,rel in _iter_project_files(root):
            z.write(str(src),arcname=f"app/{rel}")
            total+=1
    trim_code_snapshots(keep=keep,root_dir=root,out_dir=sdir)
    if progress:
        try:progress.setValue(100);progress._label.setText("Done.")
        except Exception:pass
    _log_update("[+]",f"Code snapshot created: {out} version={ver} reason={tag}",root)
    return {"path":str(out),"version":ver,"reason":tag}
def _remove_current_code(root):
    root=str(_root_dir(root))
    for base,dirs,files in os.walk(root,topdown=True):
        rel_dir=os.path.relpath(base,root)
        if rel_dir==".":
            rel_dir=""
        dirs[:]=[d for d in dirs if not _should_skip_rel(os.path.join(rel_dir,d))]
        for fn in files:
            rel=os.path.join(rel_dir,fn) if rel_dir else fn
            if _should_skip_rel(rel):continue
            p=os.path.join(base,fn)
            if _within_root(p,root):
                try:os.remove(p)
                except Exception:pass
    for base,dirs,_ in os.walk(root,topdown=False):
        rel_dir=os.path.relpath(base,root)
        if rel_dir in (".",""):continue
        if _should_skip_rel(rel_dir):continue
        if not _within_root(base,root):continue
        try:
            if not os.listdir(base):os.rmdir(base)
        except Exception:
            pass
def restore_code_snapshot(zip_path,root_dir=None,progress=None,replace=True):
    if not zip_path or not os.path.isfile(zip_path):return False,"Snapshot not found"
    root=_root_dir(root_dir)
    tmp=tempfile.mkdtemp(prefix="loya_code_restore_")
    try:
        if progress:
            try:progress.setValue(10);progress._label.setText("Extracting code snapshot ...")
            except Exception:pass
        with zipfile.ZipFile(zip_path,"r") as z:z.extractall(tmp)
        app_src=os.path.join(tmp,"app")
        if not os.path.isdir(app_src):return False,"Invalid snapshot format"
        if replace:_remove_current_code(root)
        if progress:
            try:progress.setValue(55);progress._label.setText("Restoring code files ...")
            except Exception:pass
        for base,dirs,files in os.walk(app_src):
            rel_dir=os.path.relpath(base,app_src)
            rel_dir="" if rel_dir=="." else rel_dir
            dirs[:]=[d for d in dirs if not _should_skip_rel(os.path.join(rel_dir,d))]
            td=os.path.join(str(root),rel_dir) if rel_dir else str(root)
            os.makedirs(td,exist_ok=True)
            for fn in files:
                rel=os.path.join(rel_dir,fn) if rel_dir else fn
                if _should_skip_rel(rel):continue
                src=os.path.join(base,fn);dst=os.path.join(td,fn)
                if _within_root(dst,root):shutil.copy2(src,dst)
        if progress:
            try:progress.setValue(100);progress._label.setText("Done.")
            except Exception:pass
        _log_downgrade("[+]",f"Code snapshot restored: {zip_path}",root)
        return True,"Code snapshot restored."
    except Exception as e:
        _log_downgrade("[!]",f"Code snapshot restore failed: {zip_path} ({e})",root)
        return False,f"Restore failed: {e}"
    finally:
        try:shutil.rmtree(tmp,ignore_errors=True)
        except Exception:pass
def prepare_update_backups(current_version="",reason="update",keep_code_versions=2,progress=None,root_dir=None,data_backup_dir=None,code_backup_dir=None):
    ver=_helpers.coerce_local_version(current_version,_service.get_app_version())
    data_backup=create_data_backup(progress=progress,prefix="UpdateBackup",root_dir=root_dir,out_dir=data_backup_dir)
    code_snapshot=create_code_snapshot(version=ver,reason=reason,keep=keep_code_versions,progress=progress,root_dir=root_dir,out_dir=code_backup_dir)
    out={"version":ver,"data_backup":data_backup,"code_snapshot":code_snapshot.get("path",""),"old_versions_dir":str(old_versions_dir(root_dir,code_backup_dir))}
    _log_update("[+]",f"Update safety backups ready: data={data_backup} code={out['code_snapshot']}",root_dir)
    return out
