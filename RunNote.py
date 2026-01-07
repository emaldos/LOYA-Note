import os,sys,json,subprocess,threading,time,re
from pathlib import Path
def _abs(*p):
    return str(Path(__file__).resolve().parent.joinpath(*p))
def _is_win():
    return os.name=="nt"
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
                {"name":"openpyxl","version":"==3.1.5"}
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
    req_path=_abs("Requirements.json")
    py_req,reqs=_read_requirements(req_path)
    if not _py_ok(py_req):
        print(f"ERROR: Python version not supported. Required: {py_req} | Current: {sys.version.split()[0]}")
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
