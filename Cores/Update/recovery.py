import argparse,os,subprocess,sys,time
from pathlib import Path
if __package__ in (None,""):
    _ROOT=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..",".."))
    if _ROOT not in sys.path:sys.path.insert(0,_ROOT)
    from Cores.Update import backup_restore as _backup_restore
    from Cores.Update import downgrade as _downgrade
    from Cores.Update import health_check as _health_check
    from Cores.Update import update_service as _service
else:
    from . import backup_restore as _backup_restore
    from . import downgrade as _downgrade
    from . import health_check as _health_check
    from . import update_service as _service
def _norm(v):return str(v or "").strip()
def _root_dir(root_dir=None):return str((Path(root_dir).resolve() if root_dir else Path(__file__).resolve().parents[2]))
def _fmt_time(ts):
    try:return time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(float(ts)))
    except Exception:return "-"
def _fmt_size(n):
    try:n=int(n)
    except Exception:return "0 B"
    for unit in ("B","KB","MB","GB","TB"):
        if n<1024:return f"{n} {unit}"
        n//=1024
    return f"{n} PB"
def _console_python(python_exe=""):
    py=os.path.abspath(_norm(python_exe) or sys.executable)
    if os.name=="nt" and py.lower().endswith("pythonw.exe"):
        alt=py[:-5]+".exe"
        if os.path.isfile(alt):return alt
    return py
def _open_path(path):
    p=_norm(path)
    if not p:return False,"Missing path."
    try:
        if os.name=="nt":os.startfile(p);return True,""
        if sys.platform=="darwin":subprocess.Popen(["open",p]);return True,""
        subprocess.Popen(["xdg-open",p]);return True,""
    except Exception as e:return False,str(e)
def _backup_rows(root_dir=None,limit=8):
    rows=[];bdir=Path(_health_check.backups_dir())
    try:
        for p in bdir.glob("*.zip"):
            if p.is_file():
                st=p.stat()
                rows.append({"path":str(p),"mtime":st.st_mtime,"size":st.st_size})
    except Exception:pass
    rows.sort(key=lambda x:x["mtime"],reverse=True)
    return rows[:max(1,int(limit or 8))]
def build_recovery_context(report=None,extra_reason="",root_dir=None):
    root=_root_dir(root_dir)
    rep=report if report is not None else _health_check.run_health_check(after_security=False)
    ver=_service.get_app_version()
    state=_service.get_update_state(ver)
    backups=_backup_rows(root,8)
    snapshots=_downgrade.list_snapshots(limit=2,root_dir=root)
    reasons=[]
    if rep and getattr(rep,"errors",None):reasons.extend([_norm(x) for x in rep.errors if _norm(x)])
    if state.get("recovery_required") and _norm(state.get("recovery_reason","")):reasons.append(_norm(state.get("recovery_reason","")))
    elif state.get("last_launch_ok") is False and _norm(state.get("last_launch_error","")):reasons.append(_norm(state.get("last_launch_error","")))
    if state.get("update_in_progress") and _norm(state.get("pending_version","")):
        reasons.append(f"Update to {state.get('pending_version','')} is still waiting for startup confirmation.")
    if _norm(extra_reason):reasons.append(_norm(extra_reason))
    dedup=[];seen=set()
    for item in reasons:
        key=item.lower()
        if key in seen:continue
        seen.add(key);dedup.append(item)
    update_related=bool(state.get("pending_version") or state.get("update_in_progress") or state.get("release_id") or state.get("package_sha256"))
    allow_downgrade=bool(snapshots) and bool(update_related and (state.get("recovery_required") or state.get("last_launch_ok") is False or (rep and rep.fatal)))
    return {"root_dir":root,"report":rep,"state":state,"current_version":ver,"reasons":dedup,"backups":backups,"snapshots":snapshots,"allow_downgrade":allow_downgrade}
def needs_recovery(context=None,forced=False):
    if forced:return True
    ctx=context if isinstance(context,dict) else build_recovery_context()
    rep=ctx.get("report")
    state=ctx.get("state",{}) if isinstance(ctx.get("state",{}),dict) else {}
    if rep and getattr(rep,"fatal",False):return True
    if state.get("recovery_required"):return True
    if state.get("last_launch_ok") is False and (state.get("update_in_progress") or _norm(state.get("last_launch_error",""))):return True
    return False
def diagnostics_text(context=None):
    ctx=context if isinstance(context,dict) else build_recovery_context()
    rep=ctx.get("report");state=ctx.get("state",{}) if isinstance(ctx.get("state",{}),dict) else {}
    lines=["Diagnostics",f"Root: {ctx.get('root_dir','')}",f"Current version: {ctx.get('current_version','') or '?'}",f"Last good version: {_norm(state.get('last_good_version','')) or '-'}",f"Pending version: {_norm(state.get('pending_version','')) or '-'}",f"Update in progress: {bool(state.get('update_in_progress'))}",f"Recovery required: {bool(state.get('recovery_required'))}",f"Recovery reason: {_norm(state.get('recovery_reason','')) or '-'}",f"Last launch ok: {bool(state.get('last_launch_ok'))}",f"Last launch error: {_norm(state.get('last_launch_error','')) or '-'}",f"Logs: {_health_check.logs_dir()}",f"Backups: {_health_check.backups_dir()}",f"Snapshots: {_health_check.old_versions_dir()}",f"Database: {_health_check.db_path()}",f"Settings: {_health_check.settings_path()}",f"Targets: {_health_check.targets_path()}"]
    if rep:
        if rep.repairs:lines.append("Repairs:");lines.extend([f"- {x}" for x in rep.repairs])
        if rep.warnings:lines.append("Warnings:");lines.extend([f"- {x}" for x in rep.warnings])
        if rep.errors:lines.append("Errors:");lines.extend([f"- {x}" for x in rep.errors])
    if ctx.get("backups"):lines.append(f"Data backups available: {len(ctx['backups'])}")
    if ctx.get("snapshots"):lines.append(f"Code snapshots available: {len(ctx['snapshots'])}")
    return "\n".join(lines)
def _restart_launcher(launcher_python,launcher_script,root_dir):
    py=_console_python(launcher_python)
    script=os.path.abspath(_norm(launcher_script) or os.path.join(_root_dir(root_dir),"RunNote.py"))
    if not os.path.isfile(script):return False,"RunNote.py not found."
    stdin=subprocess.DEVNULL
    if os.name=="nt":
        try:subprocess.Popen([py,script],cwd=_root_dir(root_dir),stdin=stdin,creationflags=0x00000010);return True,"Launcher restarted."
        except Exception as e:return False,str(e)
    try:subprocess.Popen([py,script],cwd=_root_dir(root_dir),stdin=stdin,start_new_session=True);return True,"Launcher restarted."
    except Exception as e:return False,str(e)
def _ask(prompt,default=""):
    try:return _norm(input(prompt))
    except EOFError:return _norm(default)
def _choose_backup(context,output=print):
    rows=context.get("backups",[]) if isinstance(context,dict) else []
    if not rows:
        output("No data backups available.")
        return None
    output("Available backups:")
    for i,row in enumerate(rows,1):output(f"{i}. {_fmt_time(row['mtime'])} | {_fmt_size(row['size'])} | {os.path.basename(row['path'])}")
    raw=_ask("Select backup number [Enter to cancel]: ")
    if not raw:return None
    try:idx=int(raw)
    except Exception:return None
    if idx<1 or idx>len(rows):return None
    return rows[idx-1]
def _restore_backup_interactive(context,output=print):
    row=_choose_backup(context,output)
    if not row:return False,"Backup restore cancelled."
    mode_raw=_ask("Restore mode [M=merge / R=replace, default M]: ","m").lower()
    mode="replace" if mode_raw.startswith("r") else "merge"
    ok,msg=_backup_restore.restore_data_backup(row["path"],mode=mode,root_dir=context.get("root_dir",""))
    return ok,msg
def _run_downgrade_interactive(context,launcher_python="",output=print):
    rows=context.get("snapshots",[]) if isinstance(context,dict) else []
    if not rows:
        output("No downgrade snapshots available.")
        return False,"No downgrade snapshots available."
    output("Available downgrade snapshots:")
    for row in rows:
        line=f"{row['index']}. v{row['version'] or '?'} | {row['mtime_text']} | {row['size_text']} | {os.path.basename(row['path'])}"
        if row.get("reason"):line+=f" | reason={row['reason']}"
        output(line)
    raw=_ask("Select snapshot number [Enter to cancel]: ")
    if not raw:return False,"Downgrade cancelled."
    try:idx=int(raw)
    except Exception:return False,"Invalid snapshot number."
    script=os.path.join(context.get("root_dir",""),"Cores","Update","downgrade.py")
    py=_console_python(launcher_python)
    if not os.path.isfile(script):return False,"downgrade.py not found."
    try:
        rc=subprocess.call([py,script,"--root",context.get("root_dir",""),"--index",str(idx),"--yes"],cwd=context.get("root_dir",""))
        return rc==0,("Downgrade completed." if rc==0 else f"Downgrade script failed with code {rc}.")
    except Exception as e:return False,str(e)
def run_recovery_console(context=None,launcher_python="",launcher_script="",forced=False,extra_reason="",output=print):
    ctx=context if isinstance(context,dict) else build_recovery_context(extra_reason=extra_reason)
    if not needs_recovery(ctx,forced):return {"action":"continue","context":ctx}
    while True:
        ctx=build_recovery_context(extra_reason=extra_reason,root_dir=ctx.get("root_dir",""))
        output("")
        output("LOYA Recovery Mode")
        output("==================")
        if ctx.get("reasons"):
            output("Reason:")
            for item in ctx["reasons"]:output("- "+item)
        else:
            output("Recovery was requested manually.")
        output("")
        options=[("1","Restore Backup"),("3","Open Logs"),("4","Show Diagnostics"),("5","Retry Startup"),("0","Exit")]
        if ctx.get("allow_downgrade"):options.insert(1,("2","Downgrade Last Version"))
        for key,label in options:output(f"{key}. {label}")
        choice=_ask("Choose: ","0")
        if choice=="1":
            ok,msg=_restore_backup_interactive(ctx,output)
            output(msg)
            if ok:return {"action":"restart","context":ctx}
            continue
        if choice=="2" and ctx.get("allow_downgrade"):
            ok,msg=_run_downgrade_interactive(ctx,launcher_python=launcher_python,output=output)
            output(msg)
            if ok:return {"action":"restart","context":ctx}
            continue
        if choice=="3":
            ok,msg=_open_path(_health_check.logs_dir())
            output("Logs opened." if ok else f"Open logs failed: {msg}")
            continue
        if choice=="4":
            output("")
            output(diagnostics_text(ctx))
            output("")
            continue
        if choice=="5":
            return {"action":"continue","context":ctx}
        if choice=="0":
            return {"action":"exit","context":ctx}
        output("Unknown option.")
def main(argv=None):
    ap=argparse.ArgumentParser(description="LOYA recovery console")
    ap.add_argument("--force",action="store_true",help="Open recovery even if no error is detected")
    ap.add_argument("--reason",default="",help="Extra reason shown in the recovery screen")
    ap.add_argument("--launcher-python",default="",help="Python executable to relaunch RunNote.py")
    ap.add_argument("--launcher-script",default="",help="RunNote.py path")
    ap.add_argument("--root",default="",help="Project root")
    ns=ap.parse_args(argv)
    ctx=build_recovery_context(extra_reason=ns.reason,root_dir=ns.root)
    res=run_recovery_console(context=ctx,launcher_python=ns.launcher_python,launcher_script=ns.launcher_script,forced=ns.force,extra_reason=ns.reason)
    act=_norm(res.get("action",""))
    if act in ("restart","continue"):
        ok,msg=_restart_launcher(ns.launcher_python,ns.launcher_script or os.path.join(_root_dir(ns.root),"RunNote.py"),ctx.get("root_dir",""))
        print(msg if ok else "Launcher restart failed: "+msg)
        return 0 if ok else 3
    return 0
if __name__=="__main__":raise SystemExit(main())
