import os,sys,json,subprocess,threading,time,re
from pathlib import Path
try:
    from Cores.Update import APP_NAME as _UPDATE_APP_NAME
    from Cores.Update import DEFAULT_APP_VERSION as _DEFAULT_APP_VERSION
    from Cores.Update import ensure_runtime_files as _ensure_update_runtime
    from Cores.Update import get_app_version as _get_app_version
    from Cores.Update import recovery as _recovery
    from Cores.Update import sync_installed_version as _sync_installed_version
except Exception:
    _UPDATE_APP_NAME="LOYA Note"
    _DEFAULT_APP_VERSION="5.0.0"
    _recovery=None
    def _get_app_version():
        return _DEFAULT_APP_VERSION
    def _ensure_update_runtime(current_version=""):
        return {"version":_DEFAULT_APP_VERSION,"state":{}}
    def _sync_installed_version(version=""):
        return {}
def _abs(*p):
    return str(Path(__file__).resolve().parent.joinpath(*p))
def _is_win():
    return os.name=="nt"
def _console_python():
    py=os.path.abspath(sys.executable)
    if _is_win() and py.lower().endswith("pythonw.exe"):
        alt=py[:-5]+".exe"
        if os.path.isfile(alt):return alt
    return py
def _restart_self():
    script=_abs("RunNote.py")
    py=_console_python()
    try:
        if _is_win():
            subprocess.Popen([py,script],cwd=_abs(),stdin=subprocess.DEVNULL,creationflags=0x00000010)
        else:
            subprocess.Popen([py,script],cwd=_abs(),stdin=subprocess.DEVNULL,start_new_session=True)
        return True,"Launcher restarted."
    except Exception as e:
        return False,str(e)
def _parse_args(argv):
    out={"force_recovery":False,"recovery_reason":""}
    i=0
    while i<len(argv):
        arg=str(argv[i] or "").strip()
        if arg=="--recovery":
            out["force_recovery"]=True
        elif arg=="--reason" and i+1<len(argv):
            i+=1;out["recovery_reason"]=str(argv[i] or "").strip()
        i+=1
    return out
_QT_WIN_MIN_VER=(10,0,17763)
def _fmt_ver_tuple(ver):
    if not ver:
        return "unknown"
    return ".".join(str(int(x)) for x in ver)
def _win_ver():
    if not _is_win():
        return None
    try:
        wv=sys.getwindowsversion()
        return int(wv.major),int(wv.minor),int(wv.build)
    except Exception:
        return None
def _check_windows_qt_support():
    if not _is_win():
        return True,""
    ver=_win_ver()
    if ver and ver<_QT_WIN_MIN_VER:
        return False,(
            f"Windows {_fmt_ver_tuple(ver)} detected.\n"
            "Qt 6 requires Windows 10 version 1809 (build 17763) or later."
        )
    return True,""
def _vc_redist_info():
    info={"ok":True,"installed":None,"version":"","dlls_ok":True}
    if not _is_win():
        return info
    sysroot=os.environ.get("SystemRoot",r"C:\Windows")
    dlls=[
        os.path.join(sysroot,"System32","vcruntime140.dll"),
        os.path.join(sysroot,"System32","vcruntime140_1.dll"),
        os.path.join(sysroot,"System32","msvcp140.dll"),
    ]
    info["dlls_ok"]=all(os.path.isfile(p) for p in dlls)
    info["dlls"]=dlls
    try:
        import winreg
    except Exception:
        info["ok"]=bool(info["dlls_ok"])
        return info
    key_paths=(
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
        r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
    )
    for key_path in key_paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,key_path) as key:
                try:
                    info["version"]=str(winreg.QueryValueEx(key,"Version")[0] or "").strip()
                except OSError:
                    info["version"]=""
                try:
                    info["installed"]=int(winreg.QueryValueEx(key,"Installed")[0])==1
                except OSError:
                    info["installed"]=None
                info["key_path"]=key_path
                break
        except OSError:
            continue
    info["ok"]=bool(info["installed"] or info["dlls_ok"])
    return info
def _check_platform_prereqs():
    ok,msg=_check_windows_qt_support()
    if not ok:
        return False,msg
    vc=_vc_redist_info()
    if _is_win() and not vc.get("ok"):
        return False,(
            "Microsoft Visual C++ Redistributable x64 was not detected.\n"
            "Qt 6 on Windows needs the MSVC runtime. Install or repair the x64 VC++ Redistributable, then run LOYA Note again."
        )
    return True,""
def _bootstrap_startup_state():
    try:
        from Cores.Update import health_check as _health_check
    except Exception as exc:
        return False,f"Failed to load startup health check ({exc})","",None
    try:
        report=_health_check.run_health_check(after_security=False)
    except Exception as exc:
        return False,f"Startup health check crashed ({exc})","",None
    if report.fatal:
        return False,report.fatal_text(),"",report
    notice=report.notice_text() if report.has_notice() else ""
    return True,"",notice,report
def _run_recovery(force=False,reason="",report=None):
    if _recovery is None:
        return {"action":"continue","shown":False}
    try:
        ctx=_recovery.build_recovery_context(report=report,extra_reason=reason,root_dir=_abs())
        if not _recovery.needs_recovery(ctx,force):return {"action":"continue","shown":False,"context":ctx}
        out=_recovery.run_recovery_console(context=ctx,launcher_python=_console_python(),launcher_script=_abs("RunNote.py"),forced=force,extra_reason=reason)
        if not isinstance(out,dict):out={"action":"continue"}
        out["shown"]=True
        return out
    except Exception as exc:
        return {"action":"continue","shown":False,"error":f"Recovery mode failed to start ({exc})."}
def _py_ok(req):
    if not req:
        return True
    m=re.match(r"^\s*>=\s*(\d+)\.(\d+)",str(req))
    if not m:
        return True
    maj,mi=int(m.group(1)),int(m.group(2))
    return (sys.version_info.major,sys.version_info.minor)>=(maj,mi)
def _read_requirements(p):
    d=None
    try:
        if os.path.isfile(p):
            with open(p,"r",encoding="utf-8") as f:
                d=json.load(f)
    except Exception:
        d=None
    if not isinstance(d,dict):
        d={
            "python":{"requires":">=3.10"},
            "pip":{"packages":[
                {"name":"PyQt6","version":"==6.10.1"},
                {"name":"PyQt6-Qt6","version":"==6.10.1"},
                {"name":"PyQt6-sip","version":"==13.10.2"},
                {"name":"cryptography","version":"==42.0.5"}
            ]}
        }
    py_req=((d.get("python") or {}).get("requires") if isinstance(d.get("python"),dict) else "")
    pkgs=((d.get("pip") or {}).get("packages") if isinstance(d.get("pip"),dict) else [])
    out=[]
    if isinstance(pkgs,list):
        for it in pkgs:
            if not isinstance(it,dict):
                continue
            n=str(it.get("name","") or "").strip()
            v=str(it.get("version","") or "").strip()
            if n:
                out.append(n+v)
    return py_req,out
class _Spinner:
    def __init__(self):
        self._stop=threading.Event()
        self._t=None
        self._msg=""
        self._ok=None
    def start(self,msg):
        self._msg=msg
        self._ok=None
        self._stop.clear()
        self._t=threading.Thread(target=self._run,daemon=True)
        self._t.start()
    def _run(self):
        frames=["[.    ]","[..   ]","[...  ]","[.... ]","[.....]","[ ....]","[  ...]","[   ..]","[    .]"]
        i=0
        while not self._stop.is_set():
            f=frames[i%len(frames)]
            i+=1
            sys.stdout.write(f"\r{f} {self._msg} ")
            sys.stdout.flush()
            time.sleep(0.08)
    def stop(self,ok=True,tail=""):
        self._ok=ok
        self._stop.set()
        if self._t:
            self._t.join(timeout=0.5)
        mark="[OK]" if ok else "[ERR]"
        s=f"\r{mark} {self._msg}"
        if tail:
            s+=f" {tail}"
        sys.stdout.write(s+" "*8+"\n")
        sys.stdout.flush()
def _run(cmd,spinner_msg=None,env=None,cwd=None):
    sp=_Spinner()
    if spinner_msg:
        sp.start(spinner_msg)
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env,cwd=cwd)
    out=[]
    try:
        for line in p.stdout:
            if line:
                out.append(line.rstrip("\n"))
    except Exception:
        pass
    rc=p.wait()
    if spinner_msg:
        sp.stop(rc==0,tail="")
    return rc,"\n".join(out[-30:])
def _venv_paths(venv_dir):
    if _is_win():
        py=os.path.join(venv_dir,"Scripts","python.exe")
        pyw=os.path.join(venv_dir,"Scripts","pythonw.exe")
        pip=os.path.join(venv_dir,"Scripts","pip.exe")
    else:
        py=os.path.join(venv_dir,"bin","python3")
        pyw=""
        pip=os.path.join(venv_dir,"bin","pip3")
    return py,pyw,pip
def _make_hidden_windows(p):
    if not _is_win():
        return
    try:
        subprocess.run(["attrib","+h",p],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception:
        pass
def _ensure_venv(venv_dir):
    if os.path.isdir(venv_dir):
        return True,""
    rc,tail=_run([sys.executable,"-m","venv",venv_dir],f"Creating venv ({os.path.basename(venv_dir)})")
    if rc!=0:
        return False,tail
    _make_hidden_windows(venv_dir)
    return True,""
def _ensure_pip(py):
    rc,tail=_run([py,"-m","pip","install","-U","pip"],"Updating pip")
    return rc==0,tail
def _ensure_deps(py,reqs):
    if not reqs:
        return True,""
    cmd=[py,"-m","pip","install","--upgrade","--upgrade-strategy","only-if-needed"]+reqs
    rc,tail=_run(cmd,"Installing/Updating requirements")
    return rc==0,tail
def _check_pyqt_runtime(py):
    code=(
        "import sys,traceback\n"
        "try:\n"
        "    from PyQt6.QtCore import Qt,QSize,QPropertyAnimation,QEasingCurve,QTimer\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
        "print('QT_IMPORT_OK')\n"
    )
    rc,tail=_run([py,"-c",code],"Verifying PyQt6 runtime")
    return rc==0,tail
def _pyqt_runtime_help(tail=""):
    lines=[]
    if _is_win():
        ver=_win_ver()
        if ver:
            lines.append(f"Windows version: {_fmt_ver_tuple(ver)}")
        vc=_vc_redist_info()
        if vc.get("version"):
            lines.append(f"VC++ runtime: {vc['version']}")
        elif vc.get("ok"):
            lines.append("VC++ runtime: detected")
        else:
            lines.append("VC++ runtime: not detected")
        if ver and ver<_QT_WIN_MIN_VER:
            lines.append("Qt 6 only supports Windows 10 version 1809 (build 17763) or later.")
        elif not vc.get("ok"):
            lines.append("Qt 6 on Windows needs the x64 Microsoft Visual C++ Redistributable.")
        else:
            lines.append("PyQt6 was installed, but QtCore still failed to load on this machine.")
            lines.append("This usually means the Windows Qt runtime prerequisites are missing or broken.")
    if tail:
        lines.append("")
        lines.append("PyQt6 import traceback:")
        lines.append(tail)
    return "\n".join(lines).strip()
def _launch_app(py,pyw,app_path):
    if not os.path.isfile(app_path):
        return False,f"Missing file: {os.path.basename(app_path)}",0
    stdin=subprocess.DEVNULL
    stdout=subprocess.DEVNULL
    stderr=subprocess.DEVNULL
    if _is_win():
        DETACHED_PROCESS=0x00000008
        CREATE_NEW_PROCESS_GROUP=0x00000200
        CREATE_NO_WINDOW=0x08000000
        flags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW
        exe=pyw if pyw and os.path.isfile(pyw) else py
        p=subprocess.Popen([exe,app_path],stdin=stdin,stdout=stdout,stderr=stderr,creationflags=flags,cwd=os.path.dirname(app_path))
    else:
        p=subprocess.Popen([py,app_path],stdin=stdin,stdout=stdout,stderr=stderr,start_new_session=True,cwd=os.path.dirname(app_path))
    return True,"",int(getattr(p,"pid",0) or 0)
def main():
    args=_parse_args(sys.argv[1:])
    app_version=_get_app_version()
    try:
        _ensure_update_runtime(app_version)
        _sync_installed_version(app_version)
    except Exception as exc:
        print(f"WARNING: updater runtime init failed ({exc})")
    print(f"{_UPDATE_APP_NAME} v{app_version}")
    req_path=_abs("Requirements.json")
    py_req,reqs=_read_requirements(req_path)
    if not _py_ok(py_req):
        print(f"ERROR: Python version not supported. Required: {py_req} | Current: {sys.version.split()[0]}")
        return 2
    force_recovery=bool(args.get("force_recovery"))
    recovery_reason=str(args.get("recovery_reason","") or "")
    while True:
        ok,msg,notice,report=_bootstrap_startup_state()
        rec=_run_recovery(force=force_recovery,reason=(recovery_reason or msg),report=report)
        if rec.get("error"):
            print("WARNING: "+str(rec.get("error")))
        act=str(rec.get("action","continue") or "continue").strip().lower()
        if act=="restart":
            rok,rmsg=_restart_self()
            print(rmsg if rok else "ERROR: "+rmsg)
            return 0 if rok else 10
        if act=="exit":
            return 10
        if rec.get("shown"):
            force_recovery=False;recovery_reason=""
            continue
        force_recovery=False;recovery_reason=""
        if ok:
            if notice:print(notice)
            break
        print("ERROR: Startup state validation failed")
        print(msg)
        return 2
    ok,msg=_check_platform_prereqs()
    if not ok:
        print("ERROR: Platform prerequisites failed")
        print(msg)
        return 2
    venv_dir=_abs(".venv_windows" if _is_win() else ".venv_linux")
    ok,tail=_ensure_venv(venv_dir)
    if not ok:
        print("ERROR: Failed to create venv")
        print(tail)
        return 3
    py,pyw,pip=_venv_paths(venv_dir)
    if not os.path.isfile(py):
        print("ERROR: venv python not found")
        return 4
    ok,tail=_ensure_pip(py)
    if not ok:
        print("ERROR: Failed to update pip")
        print(tail)
        return 5
    ok,tail=_ensure_deps(py,reqs)
    if not ok:
        print("ERROR: Failed to install requirements")
        print(tail)
        return 6
    ok,tail=_check_pyqt_runtime(py)
    if not ok:
        print("ERROR: PyQt6 runtime check failed")
        msg=_pyqt_runtime_help(tail)
        if msg:
            print(msg)
        return 7
    app=_abs("LOYA_Note.py")
    sp=_Spinner()
    sp.start("Launching LOYA Note")
    ok,msg,pid=_launch_app(py,pyw,app)
    sp.stop(ok)
    if not ok:
        print(f"ERROR: {msg}")
        return 7
    print(f"OK: Running in background (PID: {pid})")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
