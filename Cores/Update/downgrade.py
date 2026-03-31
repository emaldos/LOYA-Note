import argparse,json,os,re,sys,time,zipfile
if __package__ in (None,""):
    _ROOT=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..",".."))
    if _ROOT not in sys.path:sys.path.insert(0,_ROOT)
    from Cores.Update import backup_restore as _backup_restore
    from Cores.Update import update_helpers as _helpers
    from Cores.Update import update_service as _service
else:
    from . import backup_restore as _backup_restore
    from . import update_helpers as _helpers
    from . import update_service as _service
_VER_RX=re.compile(r"CodeSnapshot_((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))_")
def _norm(v):return str(v or "").strip()
def _root_dir(root_dir=None):return str((os.path.abspath(root_dir) if root_dir else _helpers.root_dir()))
def _now():return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def _fmt_mtime(ts):
    try:return time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(float(ts)))
    except Exception:return "-"
def _fmt_size(n):
    try:n=int(n)
    except Exception:return "0 B"
    for unit in ("B","KB","MB","GB","TB"):
        if n<1024:return f"{n} {unit}"
        n//=1024
    return f"{n} PB"
def _log(root_dir,tag,msg):
    try:
        path=os.path.join(_root_dir(root_dir),"Logs","Downgrade_log.log")
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"a",encoding="utf-8") as fh:fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {tag} {msg}\n")
    except Exception:pass
def _snapshot_meta(path):
    out={"version":"","reason":"","created_at":"","path":path}
    try:
        with zipfile.ZipFile(path,"r") as zf:
            if "__snapshot__/metadata.json" in zf.namelist():
                data=json.loads(zf.read("__snapshot__/metadata.json").decode("utf-8","ignore"))
                if isinstance(data,dict):
                    out["version"]=_helpers.coerce_local_version(data.get("version",""),"")
                    out["reason"]=_norm(data.get("reason",""))
                    out["created_at"]=_norm(data.get("created_at",""))
    except Exception:pass
    if not out["version"]:
        m=_VER_RX.search(os.path.basename(path))
        if m:out["version"]=_helpers.coerce_local_version(m.group(1),"")
    return out
def list_snapshots(limit=2,root_dir=None):
    try:limit=max(1,int(limit or 2))
    except Exception:limit=2
    rows=_backup_restore.list_code_snapshots(root_dir=_root_dir(root_dir))
    out=[]
    for idx,(path,mtime,size) in enumerate(rows[:limit],1):
        meta=_snapshot_meta(path)
        out.append({"index":idx,"path":path,"mtime":mtime,"size":size,"size_text":_fmt_size(size),"mtime_text":_fmt_mtime(mtime),"version":_norm(meta.get("version","")),"reason":_norm(meta.get("reason","")),"created_at":_norm(meta.get("created_at",""))})
    return out
def _resolve_snapshot(index=None,path="",root_dir=None):
    rows=list_snapshots(limit=2,root_dir=root_dir)
    if path:
        target=os.path.abspath(path)
        for row in rows:
            if os.path.abspath(row["path"])==target:return row
        return None
    try:idx=int(index or 0)
    except Exception:idx=0
    if idx<=0:return rows[0] if rows else None
    for row in rows:
        if row["index"]==idx:return row
    return None
def _write_downgraded_state(version,root_dir=None):
    ver=_helpers.coerce_local_version(version,_service.get_app_version())
    _service.write_current_version(ver)
    state=_service.get_update_state(ver)
    state["current_version"]=ver
    state["last_good_version"]=ver
    state["pending_version"]=""
    state["update_in_progress"]=False
    state["last_error"]=""
    state["last_checked"]=_now()
    state["last_launch_ok"]=True
    state["last_launch_error"]=""
    state["recovery_required"]=False
    state["recovery_reason"]=""
    state["source_tag"]=_helpers.version_to_tag(ver)
    _service.write_update_state(state,ver)
    return state
def restore_snapshot(index=None,path="",root_dir=None):
    row=_resolve_snapshot(index=index,path=path,root_dir=root_dir)
    if not row:return False,{"error":"No downgrade snapshot is available."}
    root=_root_dir(root_dir)
    _log(root,"[*]",f"Downgrade requested: {row['path']}")
    ok,msg=_backup_restore.restore_code_snapshot(row["path"],root_dir=root,replace=True)
    if not ok:
        _log(root,"[!]",f"Downgrade failed: {row['path']} ({msg})")
        return False,{"error":msg,"snapshot":row}
    ver=_helpers.coerce_local_version(row.get("version",""),_service.get_app_version())
    _write_downgraded_state(ver,root_dir=root)
    _log(root,"[+]",f"Downgrade restored snapshot {os.path.basename(row['path'])} -> {ver}")
    return True,{"snapshot":row,"version":ver,"message":"Downgrade completed."}
def _print_snapshots(rows,output=print):
    if not rows:
        output("No downgrade snapshots available.")
        return
    output("Available downgrade snapshots:")
    for row in rows:
        line=f"{row['index']}. v{row['version'] or '?'} | {row['mtime_text']} | {row['size_text']} | {os.path.basename(row['path'])}"
        if row.get("reason"):line+=f" | reason={row['reason']}"
        output(line)
def main(argv=None):
    ap=argparse.ArgumentParser(description="Restore one of the last 2 LOYA code snapshots.")
    ap.add_argument("--root",default="",help="Project root")
    ap.add_argument("--list",action="store_true",help="List available downgrade snapshots")
    ap.add_argument("--index",type=int,default=0,help="Snapshot index from --list")
    ap.add_argument("--snapshot",default="",help="Explicit snapshot path")
    ap.add_argument("--latest",action="store_true",help="Use the latest snapshot")
    ap.add_argument("--yes",action="store_true",help="Skip confirmation")
    ns=ap.parse_args(argv)
    rows=list_snapshots(limit=2,root_dir=ns.root)
    if ns.list:
        _print_snapshots(rows)
        return 0
    row=_resolve_snapshot(index=(1 if ns.latest and not ns.index else ns.index),path=ns.snapshot,root_dir=ns.root)
    if not row:
        _print_snapshots(rows)
        return 2
    _print_snapshots(rows)
    if not ns.yes:
        ans=_norm(input(f"Restore snapshot {row['index']} ({os.path.basename(row['path'])})? [y/N]: "))
        if ans.lower() not in ("y","yes"):return 0
    ok,data=restore_snapshot(index=row["index"],root_dir=ns.root)
    if not ok:
        print("Downgrade failed: "+_norm(data.get("error","Unknown error")))
        return 3
    print(f"Downgrade completed to v{data.get('version','?')} from {os.path.basename(data['snapshot']['path'])}.")
    return 0
if __name__=="__main__":raise SystemExit(main())
