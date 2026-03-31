import hashlib,json,os,shutil,subprocess,sys,tempfile,time,urllib.request,zipfile
from pathlib import Path
from . import update_helpers as _helpers
_STATE_VERSION_FIELDS=("current_version","last_available_version","pending_version","last_good_version")
_STATE_TEXT_FIELDS=("last_checked","last_error","source_repo","source_owner","source_name","source_tag","last_available_tag","package_sha256","release_id","commit_sha","remote_manifest_url","last_launch_started_at","last_launch_completed_at","last_launch_error","recovery_reason")
_STATE_BOOL_FIELDS=("update_in_progress","last_launch_ok","recovery_required")
_ALLOWED_UPDATE_DIRS=("Assets","Cores")
_ALLOWED_UPDATE_FILES=("LOYA_Note.py","RunNote.py","Requirements.json","README.md","LICENSE")
_REQUIRED_UPDATE_DIRS=("Assets","Cores")
_REQUIRED_UPDATE_FILES=("LOYA_Note.py","RunNote.py","Requirements.json")
_PRESERVE_UPDATE_PATHS=("Cores/Update/CurrentVersion.info","Cores/Update/CurentVersion.info","Cores/Update/state.json","Cores/Update/OldVersions")
def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def _safe_name(text,fallback):
    raw="".join(ch if ch.isalnum() or ch in ("-","_",".") else "_" for ch in str(text or "").strip())
    raw=raw.strip("._")
    return raw or fallback
def _log_update(tag,msg):
    try:
        path=_helpers.update_log_path()
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"a",encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {tag} {msg}\n")
    except Exception:
        pass
def _progress(progress,val,msg):
    if not progress:
        return
    try:
        progress.setValue(int(val))
    except Exception:
        pass
    try:
        progress._label.setText(str(msg))
    except Exception:
        pass
def default_update_state(current_version=""):
    version=_helpers.coerce_local_version(current_version,_helpers.DEFAULT_APP_VERSION)
    return {"current_version":version,"last_checked":"","last_available_version":"","pending_version":"","last_good_version":version,"update_in_progress":False,"last_error":"","source_repo":_helpers.OFFICIAL_SOURCE_REPO,"source_owner":_helpers.OFFICIAL_SOURCE_OWNER,"source_name":_helpers.OFFICIAL_SOURCE_NAME,"source_tag":_helpers.version_to_tag(version),"last_available_tag":"","package_sha256":"","release_id":"","commit_sha":"","remote_manifest_url":_helpers.GITHUB_RELEASES_API_URL,"last_launch_started_at":"","last_launch_completed_at":"","last_launch_ok":True,"last_launch_error":"","recovery_required":False,"recovery_reason":""}
def normalize_update_state(data,current_version=""):
    version=_helpers.coerce_local_version(current_version,_helpers.DEFAULT_APP_VERSION)
    out=default_update_state(version)
    changed=not isinstance(data,dict)
    if isinstance(data,dict):
        out.update(data)
    for key in _STATE_TEXT_FIELDS:
        val=out.get(key,"")
        norm=_helpers.normalize_text(val)
        if norm!=val:
            out[key]=norm
            changed=True
    for key in _STATE_VERSION_FIELDS:
        val=out.get(key,"")
        norm=_helpers.coerce_local_version(val,"")
        if key=="current_version" and not norm:
            norm=version
        if key=="last_good_version" and not norm:
            norm=out.get("current_version") or version
        if norm!=val:
            out[key]=norm
            changed=True
    for key in _STATE_BOOL_FIELDS:
        val=out.get(key)
        norm=bool(val)
        if norm is not val:
            out[key]=norm
            changed=True
    if out["source_repo"]!=_helpers.OFFICIAL_SOURCE_REPO:
        out["source_repo"]=_helpers.OFFICIAL_SOURCE_REPO
        changed=True
    if out["source_owner"]!=_helpers.OFFICIAL_SOURCE_OWNER:
        out["source_owner"]=_helpers.OFFICIAL_SOURCE_OWNER
        changed=True
    if out["source_name"]!=_helpers.OFFICIAL_SOURCE_NAME:
        out["source_name"]=_helpers.OFFICIAL_SOURCE_NAME
        changed=True
    if out["remote_manifest_url"]!=_helpers.GITHUB_RELEASES_API_URL:
        out["remote_manifest_url"]=_helpers.GITHUB_RELEASES_API_URL
        changed=True
    sha=_helpers.normalize_sha256(out.get("package_sha256",""))
    if sha!=out.get("package_sha256",""):
        out["package_sha256"]=sha
        changed=True
    commit=_helpers.normalize_commit_sha(out.get("commit_sha",""))
    if commit!=out.get("commit_sha",""):
        out["commit_sha"]=commit
        changed=True
    expected_tag=_helpers.version_to_tag(out.get("current_version") or version)
    tag=_helpers.normalize_text(out.get("source_tag",""))
    if tag and tag!=expected_tag:
        tag=expected_tag
        changed=True
    if not tag:
        tag=expected_tag
        changed=True
    out["source_tag"]=tag
    expected_latest_tag=_helpers.version_to_tag(out.get("last_available_version") or "")
    latest_tag=_helpers.normalize_text(out.get("last_available_tag",""))
    if expected_latest_tag:
        if latest_tag!=expected_latest_tag:
            latest_tag=expected_latest_tag
            changed=True
    elif latest_tag:
        latest_tag=""
        changed=True
    out["last_available_tag"]=latest_tag
    return out,changed
def write_current_version(version):
    ver=_helpers.coerce_local_version(version,_helpers.DEFAULT_APP_VERSION)
    text=ver+"\n"
    _helpers.write_text(_helpers.version_info_path(),text)
    _helpers.write_text(_helpers.legacy_version_info_path(),text)
    return ver
def get_app_version():
    cur=_helpers.read_text(_helpers.version_info_path(),"")
    ver=_helpers.coerce_local_version(cur,"")
    if not ver:
        legacy=_helpers.read_text(_helpers.legacy_version_info_path(),"")
        ver=_helpers.coerce_local_version(legacy,_helpers.DEFAULT_APP_VERSION)
    return write_current_version(ver or _helpers.DEFAULT_APP_VERSION)
def get_update_state(current_version=""):
    version=_helpers.coerce_local_version(current_version,get_app_version())
    data=_helpers.read_json(_helpers.update_state_path(),None)
    state,changed=normalize_update_state(data,version)
    if changed or not _helpers.update_state_path().is_file():
        _helpers.write_json(_helpers.update_state_path(),state)
    return state
def write_update_state(state,current_version=""):
    version=_helpers.coerce_local_version(current_version,get_app_version())
    out,_=normalize_update_state(state,version)
    _helpers.write_json(_helpers.update_state_path(),out)
    return out
def ensure_runtime_files(current_version=""):
    version=write_current_version(_helpers.coerce_local_version(current_version,get_app_version()))
    state=get_update_state(version)
    if state.get("current_version")!=version:
        state["current_version"]=version
        if not state.get("last_good_version"):
            state["last_good_version"]=version
        state=write_update_state(state,version)
    return {"version":version,"state":state}
def sync_installed_version(version=""):
    info=ensure_runtime_files(version)
    state=dict(info["state"])
    ver=info["version"]
    changed=False
    if state.get("current_version")!=ver:
        state["current_version"]=ver
        changed=True
    if not state.get("last_good_version"):
        state["last_good_version"]=ver
        changed=True
    expected_tag=_helpers.version_to_tag(ver)
    if state.get("source_tag")!=expected_tag:
        state["source_tag"]=expected_tag
        changed=True
    if changed:
        state=write_update_state(state,ver)
    return state
def get_windows_app_id(version=""):
    return _helpers.build_windows_app_id(version or get_app_version())
def get_app_identity():
    version=get_app_version()
    state=get_update_state(version)
    return {"app_name":_helpers.APP_NAME,"version":version,"display_version":version,"window_title":f"{_helpers.APP_NAME} v{version}","windows_app_id":get_windows_app_id(version),"source_repo":state.get("source_repo",_helpers.OFFICIAL_SOURCE_REPO),"source_owner":state.get("source_owner",_helpers.OFFICIAL_SOURCE_OWNER),"source_name":state.get("source_name",_helpers.OFFICIAL_SOURCE_NAME),"source_tag":state.get("source_tag",_helpers.version_to_tag(version))}
def validate_remote_manifest(data):
    return _helpers.validate_remote_manifest(data)
def _manifest_from_github_release(payload):
    if not isinstance(payload,dict):
        raise ValueError("GitHub release payload must be an object.")
    html_url=_helpers.normalize_text(payload.get("html_url",""))
    zipball_url=_helpers.normalize_text(payload.get("zipball_url",""))
    owner,name,repo_url=_helpers.canonical_repo_parts((html_url.rsplit("/releases/",1)[0] if "/releases/" in html_url else html_url) or zipball_url)
    repo_url=repo_url or _helpers.OFFICIAL_SOURCE_REPO
    asset_url=""
    assets=payload.get("assets",[])
    if isinstance(assets,list):
        preferred=[];fallback=[]
        for asset in assets:
            if not isinstance(asset,dict):
                continue
            url=_helpers.normalize_text(asset.get("browser_download_url",""))
            name_hint=_helpers.normalize_text(asset.get("name","")).lower()
            if not url:
                continue
            if name_hint.endswith(".zip"):
                preferred.append(url)
            else:
                fallback.append(url)
        if preferred:
            asset_url=preferred[0]
        elif fallback:
            asset_url=fallback[0]
    if not asset_url:
        asset_url=zipball_url
    manifest={"manifest_version":_helpers.REMOTE_MANIFEST_VERSION,"source_repo":repo_url,"source_owner":owner or _helpers.OFFICIAL_SOURCE_OWNER,"source_name":name or _helpers.OFFICIAL_SOURCE_NAME,"version":_helpers.tag_to_version(payload.get("tag_name","")),"source_tag":_helpers.normalize_text(payload.get("tag_name","")),"package_sha256":"","release_id":_helpers.normalize_text(payload.get("id","")),"commit_sha":_helpers.normalize_commit_sha(payload.get("target_commitish","")),"html_url":html_url,"asset_url":asset_url,"published_at":_helpers.normalize_text(payload.get("published_at",""))}
    return validate_remote_manifest(manifest)
def fetch_latest_release_manifest(timeout=10):
    req=urllib.request.Request(_helpers.GITHUB_RELEASES_API_URL,headers={"Accept":"application/vnd.github+json","User-Agent":"LOYA-Note-Updater"})
    with urllib.request.urlopen(req,timeout=float(timeout)) as resp:
        payload=json.load(resp)
    return _manifest_from_github_release(payload)
def check_for_updates(timeout=10):
    state=get_update_state()
    try:
        manifest=fetch_latest_release_manifest(timeout=timeout)
        state=record_remote_manifest(manifest)
        state["last_error"]=""
        state=write_update_state(state,state.get("current_version",""))
        cur=state.get("current_version","")
        latest=state.get("last_available_version","")
        newer=bool(cur and latest and _helpers.compare_semver(latest,cur)>0)
        return {"ok":True,"state":state,"manifest":manifest,"update_available":newer,"error":""}
    except Exception as e:
        state["last_checked"]=_utc_now()
        state["last_error"]=_helpers.normalize_text(e)
        state=write_update_state(state,state.get("current_version",""))
        return {"ok":False,"state":state,"manifest":None,"update_available":False,"error":str(e)}
def _apply_manifest_to_state(state,manifest):
    state=dict(state or {})
    norm=validate_remote_manifest(manifest)
    state["last_checked"]=_utc_now()
    state["last_available_version"]=norm["version"]
    state["source_repo"]=norm["source_repo"]
    state["source_owner"]=norm["source_owner"]
    state["source_name"]=norm["source_name"]
    state["last_available_tag"]=norm["source_tag"]
    state["package_sha256"]=norm["package_sha256"]
    state["release_id"]=norm["release_id"]
    state["commit_sha"]=norm["commit_sha"]
    return state
def record_remote_manifest(manifest):
    state=get_update_state()
    state=_apply_manifest_to_state(state,manifest)
    return write_update_state(state,state.get("current_version",""))
def mark_update_pending(manifest):
    state=get_update_state()
    state=_apply_manifest_to_state(state,manifest)
    state["pending_version"]=state.get("last_available_version","")
    state["update_in_progress"]=bool(state.get("pending_version"))
    state["last_error"]=""
    state["recovery_required"]=False
    state["recovery_reason"]=""
    return write_update_state(state,state.get("current_version",""))
def mark_update_completed(version="",release_id="",commit_sha="",package_sha256=""):
    ver=write_current_version(version or get_app_version())
    state=get_update_state(ver)
    state["current_version"]=ver
    state["last_good_version"]=ver
    state["pending_version"]=""
    state["last_available_version"]=ver
    state["update_in_progress"]=False
    state["last_error"]=""
    state["source_tag"]=_helpers.version_to_tag(ver)
    state["last_available_tag"]=_helpers.version_to_tag(ver)
    state["release_id"]=_helpers.normalize_text(release_id or state.get("release_id",""))
    state["commit_sha"]=_helpers.normalize_commit_sha(commit_sha or state.get("commit_sha",""))
    state["package_sha256"]=_helpers.normalize_sha256(package_sha256 or state.get("package_sha256",""))
    state["last_checked"]=_utc_now()
    state["recovery_required"]=False
    state["recovery_reason"]=""
    return write_update_state(state,ver)
def mark_update_failed(error):
    state=get_update_state()
    state["update_in_progress"]=False
    state["pending_version"]=""
    state["last_error"]=_helpers.normalize_text(error)
    state["recovery_required"]=True
    state["recovery_reason"]=_helpers.normalize_text(error)
    return write_update_state(state,state.get("current_version",""))
def pending_update_matches_current_install(state=None,version=""):
    st=state if isinstance(state,dict) else get_update_state(version)
    ver=_helpers.coerce_local_version(version or st.get("current_version","") or get_app_version(),"")
    pending=_helpers.coerce_local_version(st.get("pending_version",""),"")
    return bool(st.get("update_in_progress") and ver and pending and pending==ver)
def finalize_pending_update_on_launch(version=""):
    ver=_helpers.coerce_local_version(version,get_app_version())
    state=get_update_state(ver)
    if not pending_update_matches_current_install(state,ver):
        return {"completed":False,"version":ver,"state":state}
    state=mark_update_completed(ver,release_id=state.get("release_id",""),commit_sha=state.get("commit_sha",""),package_sha256=state.get("package_sha256",""))
    _log_update("[+]",f"Update launch confirmed: {ver}")
    return {"completed":True,"version":ver,"state":state}
def _relative_package_members(zip_path):
    with zipfile.ZipFile(zip_path,"r") as zf:
        rows=[]
        for info in zf.infolist():
            name=str(getattr(info,"filename","") or "").replace("\\","/").lstrip("/")
            if not name or name.endswith("/"):
                continue
            parts=[p for p in name.split("/") if p and p!="."]
            if not parts or any(p==".." for p in parts):
                raise ValueError("Downloaded package contains unsafe paths.")
            rows.append("/".join(parts))
    if not rows:
        raise ValueError("Downloaded package is empty.")
    prefix=rows[0].split("/",1)[0]
    if prefix and all(item.startswith(prefix+"/") for item in rows if "/" in item):
        trimmed=[item.split("/",1)[1] for item in rows if "/" in item]
        if trimmed:
            rows=trimmed
    return rows
def _validate_package_archive(zip_path):
    members=_relative_package_members(zip_path)
    files=set(members)
    for folder in _REQUIRED_UPDATE_DIRS:
        prefix=folder.rstrip("/")+"/"
        if not any(item.startswith(prefix) for item in files):
            raise ValueError(f"Downloaded package is missing required folder: {folder}")
    for path in _REQUIRED_UPDATE_FILES:
        if path not in files:
            raise ValueError(f"Downloaded package is missing required file: {path}")
    return {"entries":len(files),"files":sorted(files)}
def _download_package(manifest,timeout=60,stage_dir=None):
    url=_helpers.normalize_text(manifest.get("asset_url",""))
    if not url:
        raise ValueError("No downloadable package URL was found for the authenticated release.")
    if not _helpers.is_official_package_url(url,manifest.get("source_owner",""),manifest.get("source_name","")):
        raise ValueError("Authenticated release package URL does not belong to the official repository.")
    stage=Path(stage_dir or tempfile.mkdtemp(prefix="loya_update_")).resolve()
    stage.mkdir(parents=True,exist_ok=True)
    pkg_path=stage.joinpath("release_package.zip")
    req=urllib.request.Request(url,headers={"Accept":"application/octet-stream,application/vnd.github+json","User-Agent":"LOYA-Note-Updater"})
    sha=hashlib.sha256()
    with urllib.request.urlopen(req,timeout=float(timeout)) as resp,open(pkg_path,"wb") as fh:
        final_url=_helpers.normalize_text(resp.geturl() or url)
        if not _helpers.is_allowed_download_redirect_url(final_url):
            raise ValueError("Downloaded package redirected to a non-GitHub host.")
        while True:
            chunk=resp.read(1024*1024)
            if not chunk:
                break
            fh.write(chunk)
            sha.update(chunk)
    return {"path":str(pkg_path),"sha256":sha.hexdigest(),"requested_url":url,"final_url":final_url,"stage_dir":str(stage)}
def _write_update_plan(stage_dir,manifest,package_info,backups,parent_pid=0,launcher_python="",launcher_script=""):
    stage=Path(stage_dir).resolve()
    plan={"plan_version":1,"created_at":_utc_now(),"root_dir":str(_helpers.root_dir().resolve()),"parent_pid":int(parent_pid or 0),"launcher_python":launcher_python or sys.executable,"launcher_script":launcher_script or str(_helpers.root_dir().joinpath("RunNote.py")),"package_path":package_info.get("path",""),"expected_sha256":package_info.get("sha256",""),"requested_url":package_info.get("requested_url",""),"final_url":package_info.get("final_url",""),"stage_dir":str(stage),"current_version":get_app_version(),"target_version":manifest.get("version",""),"manifest":manifest,"data_backup":backups.get("data_backup",""),"code_snapshot":backups.get("code_snapshot",""),"allowed_dirs":list(_ALLOWED_UPDATE_DIRS),"allowed_files":list(_ALLOWED_UPDATE_FILES),"required_dirs":list(_REQUIRED_UPDATE_DIRS),"required_files":list(_REQUIRED_UPDATE_FILES),"preserve_paths":list(_PRESERVE_UPDATE_PATHS)}
    path=stage.joinpath("update_plan.json")
    _helpers.write_json(path,plan)
    return str(path)
def _spawn_apply_helper(helper_path,plan_path):
    args=[sys.executable,helper_path,plan_path]
    stdin=subprocess.DEVNULL
    stdout=subprocess.DEVNULL
    stderr=subprocess.DEVNULL
    if os.name=="nt":
        flags=0x00000008|0x00000200|0x08000000
        proc=subprocess.Popen(args,stdin=stdin,stdout=stdout,stderr=stderr,cwd=os.path.dirname(helper_path),creationflags=flags)
    else:
        proc=subprocess.Popen(args,stdin=stdin,stdout=stdout,stderr=stderr,cwd=os.path.dirname(helper_path),start_new_session=True)
    return int(getattr(proc,"pid",0) or 0)
def start_update_install(timeout=60,parent_pid=0,launcher_python="",launcher_script="",progress=None):
    stage_dir=""
    pending_marked=False
    try:
        current_version=get_app_version()
        _progress(progress,5,"Checking official release ...")
        manifest=fetch_latest_release_manifest(timeout=timeout)
        if _helpers.compare_semver(manifest["version"],current_version)<=0:
            raise ValueError("You are already on the latest authenticated version.")
        stage_dir=tempfile.mkdtemp(prefix="loya_update_")
        _progress(progress,20,"Downloading authenticated package ...")
        package_info=_download_package(manifest,timeout=timeout,stage_dir=stage_dir)
        manifest=dict(manifest)
        manifest["package_sha256"]=package_info["sha256"]
        manifest=validate_remote_manifest(manifest)
        _progress(progress,40,"Validating downloaded package ...")
        package_meta=_validate_package_archive(package_info["path"])
        _progress(progress,55,"Preparing data and code backups ...")
        from . import backup_restore as _backup_restore
        backups=_backup_restore.prepare_update_backups(current_version=current_version,reason=f"update_{manifest['version']}",progress=progress,root_dir=_helpers.root_dir())
        _progress(progress,82,"Writing update plan ...")
        state=mark_update_pending(manifest)
        pending_marked=True
        helper_src=_helpers.update_dir().joinpath("apply_update.py")
        if not helper_src.is_file():
            raise FileNotFoundError("Missing updater apply helper: Cores/Update/apply_update.py")
        helper_dst=Path(stage_dir).joinpath("apply_update.py")
        shutil.copy2(helper_src,helper_dst)
        plan_path=_write_update_plan(stage_dir,manifest,package_info,backups,parent_pid=parent_pid,launcher_python=launcher_python or sys.executable,launcher_script=launcher_script or str(_helpers.root_dir().joinpath("RunNote.py")))
        _progress(progress,92,"Starting detached updater helper ...")
        helper_pid=_spawn_apply_helper(str(helper_dst),plan_path)
        _progress(progress,100,"Update prepared. Close the app to apply it.")
        _log_update("[+]",f"Update staged: current={current_version} target={manifest['version']} helper_pid={helper_pid} package={package_info['path']}")
        return {"ok":True,"state":state,"manifest":manifest,"package":package_info,"package_meta":package_meta,"backups":backups,"plan_path":plan_path,"helper_pid":helper_pid,"stage_dir":stage_dir,"error":""}
    except Exception as e:
        err=str(e)
        if pending_marked:
            try:
                mark_update_failed(err)
            except Exception:
                pass
        _log_update("[!]",f"Update start failed: {err}")
        return {"ok":False,"state":get_update_state(),"manifest":None,"package":None,"package_meta":None,"backups":None,"plan_path":"","helper_pid":0,"stage_dir":stage_dir,"error":err}
