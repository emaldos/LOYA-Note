import hashlib,json,os,re,shutil,subprocess,sys,tempfile,time,zipfile
_SKIP_TOP_LEVEL={"Data","Logs","Backups","Update",".venv_windows",".venv_linux","__pycache__",".git",".pytest_cache",".mypy_cache",".ruff_cache",".idea",".vs",".vscode"}
_OFFICIAL_REPO="https://github.com/emaldos/LOYA-Note"
_SEMVER_RX=re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def _norm(v):
    return str(v or "").strip()
def _is_semver(text):
    return bool(_SEMVER_RX.fullmatch(_norm(text)))
def _is_official_repo(url):
    return _norm(url).rstrip("/").lower()==_OFFICIAL_REPO.lower()
def _is_official_package_url(url):
    low=_norm(url).lower()
    return low.startswith("https://github.com/emaldos/loya-note/releases/download/") or low.startswith("https://github.com/emaldos/loya-note/archive/") or low.startswith("https://github.com/emaldos/loya-note/zipball/") or low.startswith("https://api.github.com/repos/emaldos/loya-note/zipball") or low.startswith("https://api.github.com/repos/emaldos/loya-note/releases/") or low.startswith("https://codeload.github.com/emaldos/loya-note/")
def _read_json(path,default=None):
    try:
        with open(path,"r",encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default
def _write_json(path,obj):
    tmp=path+".tmp"
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(tmp,"w",encoding="utf-8") as fh:
        json.dump(obj,fh,ensure_ascii=False,indent=2)
    os.replace(tmp,path)
def _write_text(path,text):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"w",encoding="utf-8") as fh:
        fh.write(str(text))
def _within_root(path,root):
    try:
        return os.path.commonpath([os.path.abspath(path),os.path.abspath(root)])==os.path.abspath(root)
    except Exception:
        return False
def _state_path(root):
    return os.path.join(root,"Cores","Update","state.json")
def _update_log_path(root):
    return os.path.join(root,"Logs","Update_log.log")
def _append_log(root,tag,msg):
    try:
        path=_update_log_path(root)
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"a",encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {tag} {msg}\n")
    except Exception:
        pass
def _set_state(root,mutator):
    path=_state_path(root)
    state=_read_json(path,{})
    if not isinstance(state,dict):
        state={}
    mutator(state)
    _write_json(path,state)
    return state
def _mark_failed(root,current_version,error,clear_pending=True):
    err=_norm(error)
    def _mut(state):
        state["current_version"]=_norm(current_version or state.get("current_version",""))
        if not _norm(state.get("last_good_version","")):
            state["last_good_version"]=state["current_version"]
        state["last_error"]=err
        state["recovery_required"]=True
        state["recovery_reason"]=err
        state["last_checked"]=_now()
        state["update_in_progress"]=False if clear_pending else bool(state.get("update_in_progress",False))
        if clear_pending:
            state["pending_version"]=""
    return _set_state(root,_mut)
def _mark_waiting_launch(root,error=""):
    err=_norm(error)
    def _mut(state):
        state["last_error"]=err
        state["recovery_required"]=True
        state["recovery_reason"]=err
        state["last_checked"]=_now()
        state["update_in_progress"]=True
    return _set_state(root,_mut)
def _write_version_files(root,version):
    ver=_norm(version)
    if not ver:
        return
    for rel in ("Cores/Update/CurrentVersion.info","Cores/Update/CurentVersion.info"):
        path=os.path.join(root,*rel.split("/"))
        _write_text(path,ver+"\n")
def _sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as fh:
        while True:
            chunk=fh.read(1024*1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
def _pid_running(pid):
    try:
        pid=int(pid or 0)
    except Exception:
        pid=0
    if pid<=0:
        return False
    try:
        if os.name=="nt":
            p=subprocess.run(["tasklist","/FI",f"PID eq {pid}","/NH"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=0x08000000)
            txt=(p.stdout or "").strip().lower()
            return bool(txt and "no tasks are running" not in txt and str(pid) in txt)
        os.kill(pid,0)
        return True
    except Exception:
        return False
def _wait_for_exit(pid,timeout=180):
    end=time.time()+max(1,int(timeout or 180))
    while time.time()<end:
        if not _pid_running(pid):
            return True
        time.sleep(1)
    return not _pid_running(pid)
def _safe_extract(zip_path,dst_dir):
    out=os.path.abspath(dst_dir)
    os.makedirs(out,exist_ok=True)
    with zipfile.ZipFile(zip_path,"r") as zf:
        for info in zf.infolist():
            name=str(getattr(info,"filename","") or "").replace("\\","/").lstrip("/")
            if not name:
                continue
            parts=[p for p in name.split("/") if p and p!="."]
            if any(p==".." for p in parts):
                raise RuntimeError("Package contains unsafe paths.")
            target=os.path.abspath(os.path.join(out,*parts))
            if not _within_root(target,out):
                raise RuntimeError("Package extraction escaped the staging directory.")
            if getattr(info,"is_dir",lambda: name.endswith("/"))():
                os.makedirs(target,exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target),exist_ok=True)
            with zf.open(info,"r") as src,open(target,"wb") as dst:
                shutil.copyfileobj(src,dst)
def _looks_like_source_root(path,required_dirs,required_files):
    return all(os.path.isdir(os.path.join(path,item)) for item in required_dirs) and all(os.path.isfile(os.path.join(path,item)) for item in required_files)
def _locate_source_root(base_dir,required_dirs,required_files):
    base=os.path.abspath(base_dir)
    if _looks_like_source_root(base,required_dirs,required_files):
        return base
    for root,dirs,_ in os.walk(base):
        rel=os.path.relpath(root,base)
        if rel!="." and rel.count(os.sep)>3:
            dirs[:]=[]
            continue
        if _looks_like_source_root(root,required_dirs,required_files):
            return os.path.abspath(root)
    raise RuntimeError("Downloaded package is missing the required application files.")
def _norm_rel(rel):
    return "/".join([p for p in str(rel or "").replace("\\","/").split("/") if p and p!="."]).strip("/")
def _is_preserved(rel,preserve_paths):
    rel=_norm_rel(rel)
    return any(rel==keep or rel.startswith(keep+"/") for keep in preserve_paths)
def _has_preserved_child(rel,preserve_paths):
    rel=_norm_rel(rel)
    return any(keep.startswith(rel+"/") for keep in preserve_paths)
def _clear_tree(dst_root,preserve_paths=()):
    if not os.path.isdir(dst_root):
        return
    base_root=os.path.abspath(dst_root)
    for base,dirs,files in os.walk(base_root,topdown=False):
        rel_dir=os.path.relpath(base,base_root)
        rel_dir="" if rel_dir=="." else _norm_rel(rel_dir)
        for fn in files:
            rel=_norm_rel(os.path.join(rel_dir,fn) if rel_dir else fn)
            path=os.path.join(base,fn)
            if _is_preserved(rel,preserve_paths):
                continue
            if _within_root(path,base_root):
                try:os.remove(path)
                except Exception:pass
        for dn in dirs:
            rel=_norm_rel(os.path.join(rel_dir,dn) if rel_dir else dn)
            path=os.path.join(base,dn)
            if _is_preserved(rel,preserve_paths) or _has_preserved_child(rel,preserve_paths):
                continue
            if _within_root(path,base_root):
                shutil.rmtree(path,ignore_errors=True)
def _copy_tree(src_root,dst_root,preserve_paths=()):
    os.makedirs(dst_root,exist_ok=True)
    for base,dirs,files in os.walk(src_root):
        rel_dir=os.path.relpath(base,src_root)
        rel_dir="" if rel_dir=="." else _norm_rel(rel_dir)
        dirs[:]=[d for d in dirs if not _is_preserved(os.path.join(rel_dir,d) if rel_dir else d,preserve_paths)]
        target_dir=os.path.join(dst_root,rel_dir) if rel_dir else dst_root
        os.makedirs(target_dir,exist_ok=True)
        for fn in files:
            rel=_norm_rel(os.path.join(rel_dir,fn) if rel_dir else fn)
            if _is_preserved(rel,preserve_paths):
                continue
            src=os.path.join(base,fn)
            dst=os.path.join(target_dir,fn)
            shutil.copy2(src,dst)
def _replace_dir(root,source_root,top_name,preserve_paths=()):
    src=os.path.join(source_root,top_name)
    dst=os.path.join(root,top_name)
    if not os.path.isdir(src):
        raise RuntimeError(f"Missing update folder: {top_name}")
    if not _within_root(dst,root):
        raise RuntimeError(f"Unsafe target folder: {top_name}")
    _clear_tree(dst,preserve_paths)
    _copy_tree(src,dst,preserve_paths)
def _replace_file(root,source_root,name):
    src=os.path.join(source_root,name)
    dst=os.path.join(root,name)
    if not os.path.isfile(src):
        return
    if not _within_root(dst,root):
        raise RuntimeError(f"Unsafe target file: {name}")
    os.makedirs(os.path.dirname(dst),exist_ok=True)
    shutil.copy2(src,dst)
def _should_skip_restore(rel):
    rel=_norm_rel(rel)
    if not rel:
        return False
    top=rel.split("/",1)[0]
    if top in _SKIP_TOP_LEVEL:
        return True
    return rel.startswith("Cores/Update/OldVersions/")
def _remove_current_code(root):
    base_root=os.path.abspath(root)
    for base,dirs,files in os.walk(base_root,topdown=True):
        rel_dir=os.path.relpath(base,base_root)
        rel_dir="" if rel_dir=="." else _norm_rel(rel_dir)
        dirs[:]=[d for d in dirs if not _should_skip_restore(os.path.join(rel_dir,d) if rel_dir else d)]
        for fn in files:
            rel=_norm_rel(os.path.join(rel_dir,fn) if rel_dir else fn)
            path=os.path.join(base,fn)
            if _should_skip_restore(rel) or not _within_root(path,base_root):
                continue
            try:os.remove(path)
            except Exception:pass
    for base,dirs,_ in os.walk(base_root,topdown=False):
        rel_dir=os.path.relpath(base,base_root)
        rel_dir="" if rel_dir=="." else _norm_rel(rel_dir)
        if not rel_dir or _should_skip_restore(rel_dir) or any(k.startswith(rel_dir+"/") for k in _SKIP_TOP_LEVEL):
            continue
        if not _within_root(base,base_root):
            continue
        for dn in dirs:
            _=dn
        try:
            if not os.listdir(base):
                os.rmdir(base)
        except Exception:
            pass
def _restore_snapshot(root,snapshot_zip):
    if not snapshot_zip or not os.path.isfile(snapshot_zip):
        raise RuntimeError("Rollback snapshot was not found.")
    tmp=tempfile.mkdtemp(prefix="loya_update_rollback_")
    try:
        _safe_extract(snapshot_zip,tmp)
        app_root=os.path.join(tmp,"app")
        if not os.path.isdir(app_root):
            raise RuntimeError("Rollback snapshot format is invalid.")
        _remove_current_code(root)
        for base,dirs,files in os.walk(app_root):
            rel_dir=os.path.relpath(base,app_root)
            rel_dir="" if rel_dir=="." else _norm_rel(rel_dir)
            dirs[:]=[d for d in dirs if not _should_skip_restore(os.path.join(rel_dir,d) if rel_dir else d)]
            target_dir=os.path.join(root,rel_dir) if rel_dir else root
            os.makedirs(target_dir,exist_ok=True)
            for fn in files:
                rel=_norm_rel(os.path.join(rel_dir,fn) if rel_dir else fn)
                if _should_skip_restore(rel):
                    continue
                src=os.path.join(base,fn)
                dst=os.path.join(target_dir,fn)
                if _within_root(dst,root):
                    shutil.copy2(src,dst)
    finally:
        shutil.rmtree(tmp,ignore_errors=True)
def _launch_runnote(python_exe,launcher_script,root):
    if not os.path.isfile(launcher_script):
        raise RuntimeError("RunNote.py was not found after the update.")
    args=[python_exe or sys.executable,launcher_script]
    stdin=subprocess.DEVNULL
    stdout=subprocess.DEVNULL
    stderr=subprocess.DEVNULL
    if os.name=="nt":
        flags=0x00000008|0x00000200|0x08000000
        proc=subprocess.Popen(args,stdin=stdin,stdout=stdout,stderr=stderr,cwd=root,creationflags=flags)
    else:
        proc=subprocess.Popen(args,stdin=stdin,stdout=stdout,stderr=stderr,cwd=root,start_new_session=True)
    return int(getattr(proc,"pid",0) or 0)
def _validate_plan(plan):
    if not isinstance(plan,dict):
        raise RuntimeError("Invalid update plan.")
    root=os.path.abspath(_norm(plan.get("root_dir","")))
    package_path=os.path.abspath(_norm(plan.get("package_path","")))
    manifest=plan.get("manifest",{}) if isinstance(plan.get("manifest",{}),dict) else {}
    version=_norm(plan.get("target_version","") or manifest.get("version",""))
    if not _is_semver(version):
        raise RuntimeError("Update plan target_version must use X.X.X format.")
    tag=_norm(manifest.get("source_tag",""))
    if tag and tag.lower()!=f"v{version}".lower():
        raise RuntimeError("Update plan source_tag does not match target_version.")
    repo=_norm(manifest.get("source_repo",""))
    if repo and not _is_official_repo(repo):
        raise RuntimeError("Update plan source_repo is not the official LOYA repository.")
    requested_url=_norm(plan.get("requested_url",""))
    if requested_url and not _is_official_package_url(requested_url):
        raise RuntimeError("Update plan package URL is not from the official repository.")
    if not root or not os.path.isdir(root):
        raise RuntimeError("Update plan root_dir is invalid.")
    if not package_path or not os.path.isfile(package_path):
        raise RuntimeError("Update package file is missing.")
    expected_sha=_norm(plan.get("expected_sha256","")).lower()
    if not expected_sha or len(expected_sha)!=64:
        raise RuntimeError("Update plan is missing package_sha256.")
    return root,package_path
def main():
    if len(sys.argv)<2:
        return 2
    plan_path=os.path.abspath(sys.argv[1])
    plan=_read_json(plan_path,{})
    root,package_path=_validate_plan(plan)
    current_version=_norm(plan.get("current_version",""))
    target_version=_norm(plan.get("target_version",""))
    parent_pid=int(plan.get("parent_pid",0) or 0)
    expected_sha=_norm(plan.get("expected_sha256","")).lower()
    preserve_paths=[_norm_rel(p) for p in plan.get("preserve_paths",[]) if _norm_rel(p)]
    allowed_dirs=[_norm(p) for p in plan.get("allowed_dirs",[]) if _norm(p)]
    allowed_files=[_norm(p) for p in plan.get("allowed_files",[]) if _norm(p)]
    required_dirs=[_norm(p) for p in plan.get("required_dirs",[]) if _norm(p)]
    required_files=[_norm(p) for p in plan.get("required_files",[]) if _norm(p)]
    launcher_python=_norm(plan.get("launcher_python","")) or sys.executable
    launcher_script=os.path.abspath(_norm(plan.get("launcher_script","")) or os.path.join(root,"RunNote.py"))
    code_snapshot=os.path.abspath(_norm(plan.get("code_snapshot",""))) if _norm(plan.get("code_snapshot","")) else ""
    _append_log(root,"[*]",f"Apply helper started for {target_version or '?'} plan={plan_path}")
    if not _wait_for_exit(parent_pid,180):
        msg=f"Timed out waiting for PID {parent_pid} to exit."
        _append_log(root,"[!]",msg)
        _mark_failed(root,current_version,msg,clear_pending=True)
        return 3
    if _sha256_file(package_path).lower()!=expected_sha:
        msg="Downloaded package hash mismatch."
        _append_log(root,"[!]",msg)
        _mark_failed(root,current_version,msg,clear_pending=True)
        return 4
    tmp=tempfile.mkdtemp(prefix="loya_update_apply_")
    apply_started=False
    try:
        _safe_extract(package_path,tmp)
        source_root=_locate_source_root(tmp,required_dirs,required_files)
        for top in allowed_dirs:
            preserve=tuple(_norm_rel(p.split("/",1)[1]) for p in preserve_paths if p.startswith(top+"/"))
            _replace_dir(root,source_root,top,preserve_paths=preserve)
        for name in allowed_files:
            _replace_file(root,source_root,name)
        apply_started=True
        _write_version_files(root,target_version)
        _set_state(root,lambda state:(state.__setitem__("last_error",""),state.__setitem__("last_checked",_now())))
        pid=_launch_runnote(launcher_python,launcher_script,root)
        _append_log(root,"[+]",f"Update applied to {target_version}; relaunch PID={pid}")
        return 0
    except Exception as e:
        err=_norm(e)
        _append_log(root,"[!]",f"Update apply failed: {err}")
        if apply_started:
            try:
                _restore_snapshot(root,code_snapshot)
                _write_version_files(root,current_version)
                _append_log(root,"[*]",f"Rollback restored from {code_snapshot}")
                _mark_failed(root,current_version,f"Update rolled back: {err}",clear_pending=True)
            except Exception as rollback_err:
                rerr=_norm(rollback_err)
                _append_log(root,"[!]",f"Rollback failed: {rerr}")
                _mark_waiting_launch(root,f"Update apply failed and rollback failed: {err}; rollback error: {rerr}")
        else:
            _mark_failed(root,current_version,err,clear_pending=True)
        return 5
    finally:
        shutil.rmtree(tmp,ignore_errors=True)
if __name__=="__main__":
    raise SystemExit(main())
