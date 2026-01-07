import os,sys,importlib.util,logging,time
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QSize,QPropertyAnimation,QEasingCurve,QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication,QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QFrame,QLabel,QStackedWidget,QSizePolicy,QToolButton
APP_NAME="LOYA Note"
APP_VER="3.0.0"
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _purge_old_logs(days=30):
    try:
        d=_abs("Logs")
        if not os.path.isdir(d):return 0
        cut=time.time()-(days*86400);n=0
        for name in os.listdir(d):
            p=os.path.join(d,name)
            if not os.path.isfile(p):continue
            try:
                if os.path.getmtime(p)<cut:os.remove(p);n+=1
            except:pass
        return n
    except:return 0
def _log_setup():
    d=_abs("Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("Note");lg.setLevel(logging.INFO)
    if lg.handlers:return lg
    h=RotatingFileHandler(os.path.join(d,"Note_log.log"),maxBytes=1024*1024,backupCount=5,encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s","%Y-%m-%d %H:%M:%S"))
    lg.addHandler(h);return lg
_LOG=None
def _log(tag,msg):
    global _LOG
    if _LOG is None:_LOG=_log_setup()
    try:_LOG.info(f"{tag} {msg}")
    except:pass
def _load_qss():
    p=_abs("Cores","Theme","DarkTheme.qss")
    try:
        with open(p,"r",encoding="utf-8") as f:
            s=f.read();_log("[+]",f"Theme loaded: {p}");return s
    except Exception as e:
        _log("[-]",f"Theme not loaded: {p} ({e})");return ""
_SETTINGS_MOD=None
def _load_settings_module():
    global _SETTINGS_MOD
    if _SETTINGS_MOD is not None:return _SETTINGS_MOD
    p=_abs("Cores","Settings.py")
    if not os.path.isfile(p):return None
    try:
        spec=importlib.util.spec_from_file_location("loya_settings",p)
        mod=importlib.util.module_from_spec(spec)
        sys.modules["loya_settings"]=mod
        spec.loader.exec_module(mod)
        _SETTINGS_MOD=mod
        return mod
    except Exception as e:
        _log("[!]",f"Settings module load error: {p} ({e})")
        return None
def _load_widget(module_path,attr="Widget"):
    if not os.path.isfile(module_path):_log("[-]",f"Module missing: {module_path}");return None
    try:
        if os.path.basename(module_path).lower()=="settings.py":
            mod=_load_settings_module()
            if not mod:_log("[-]",f"Settings load failed: {module_path}");return None
        else:
            spec=importlib.util.spec_from_file_location("dynmod",module_path)
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        cls=getattr(mod,attr,None)
        if cls is None:_log("[-]",f"Attr missing: {attr} in {module_path}");return None
        w=cls()
        if isinstance(w,QWidget):_log("[+]",f"Widget loaded: {module_path}::{attr}");return w
        _log("[-]",f"Invalid widget type: {module_path}::{attr}");return None
    except Exception as e:
        _log("[!]",f"Widget load error: {module_path} ({e})");return None
def _auto_backup_if_needed():
    try:
        mod=_load_settings_module()
        fn=getattr(mod,"auto_backup_if_needed",None) if mod else None
        if callable(fn):
            ok,msg=fn()
            if ok:_log("[+]",f"Auto backup: {msg}")
            else:_log("[*]",f"Auto backup: {msg}")
    except Exception as e:
        _log("[-]",f"Auto backup failed ({e})")
def _security_unlock_if_needed(owner=None):
    try:
        mod=_load_settings_module()
        fn=getattr(mod,"security_unlock_if_needed",None) if mod else None
        if callable(fn):return bool(fn(owner))
    except Exception as e:
        _log("[!]",f"Security unlock failed ({e})")
    return True
def _security_encrypt_on_exit():
    try:
        mod=_load_settings_module()
        fn=getattr(mod,"security_encrypt_on_exit",None) if mod else None
        if callable(fn):fn()
    except Exception as e:
        _log("[!]",f"Encrypt on exit failed ({e})")
class NavBtn(QToolButton):
    def __init__(self,icon_path,text,parent=None):
        super().__init__(parent)
        self._txt=text;self.btn_size=52
        self.setCheckable(True);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self.btn_size);self.setIconSize(QSize(20,20))
        if icon_path and os.path.isfile(icon_path):self.setIcon(QIcon(icon_path))
        f=self.font();f.setBold(True);self.setFont(f)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setStyleSheet("QToolButton{padding-left:12px;text-align:left;}")
        self.setText(f"\u2003{text}")
class SideBar(QFrame):
    def __init__(self,on_select,parent=None):
        super().__init__(parent)
        self.on_select=on_select
        self.setObjectName("SideBar")
        self.expanded_w=170;self.collapsed_w=72;self._expanded=True
        self._side_pad=10
        self.setMinimumWidth(self.expanded_w);self.setMaximumWidth(self.expanded_w)
        self.anim_max=QPropertyAnimation(self,b"maximumWidth");self.anim_min=QPropertyAnimation(self,b"minimumWidth")
        for a in (self.anim_max,self.anim_min):a.setDuration(220);a.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.v=QVBoxLayout(self);self.v.setContentsMargins(self._side_pad,self._side_pad,self._side_pad,self._side_pad);self.v.setSpacing(8)
        self.toggle=QToolButton(self);self.toggle.setObjectName("SideToggle");self.toggle.setCursor(Qt.CursorShape.PointingHandCursor);self.toggle.setFixedSize(52,52);self.toggle.setText("")
        ico=_abs("Assets","Side_Bar.png")
        if os.path.isfile(ico):self.toggle.setIcon(QIcon(ico));self.toggle.setIconSize(QSize(20,20))
        self.toggle.clicked.connect(self._toggle)
        self.v.addWidget(self.toggle,0,Qt.AlignmentFlag.AlignHCenter)
        self.btn_chat=NavBtn(_abs("Assets","AI.png"),"LOYA")
        self.btn_notes=NavBtn(_abs("Assets","Home.png"),"Notes")
        self.btn_commands=NavBtn(_abs("Assets","command-line.png"),"Commands")
        self.btn_target=NavBtn(_abs("Assets","Target.png"),"Targets")
        self.btn_search=NavBtn(_abs("Assets","Search.png"),"Snippets")
        self.btn_settings=NavBtn(_abs("Assets","Setting.png"),"Settings")
        self.btn_chat.clicked.connect(lambda:self.on_select("chat"))
        self.btn_notes.clicked.connect(lambda:self.on_select("notes"))
        self.btn_commands.clicked.connect(lambda:self.on_select("commands"))
        self.btn_target.clicked.connect(lambda:self.on_select("targets"))
        self.btn_search.clicked.connect(lambda:self.on_select("searchcopy"))
        self.btn_settings.clicked.connect(lambda:self.on_select("settings"))
        self.v.addWidget(self.btn_chat)
        self.v.addWidget(self.btn_notes)
        self.v.addWidget(self.btn_commands)
        self.v.addWidget(self.btn_target)
        self.v.addWidget(self.btn_search)
        self.v.addStretch(1)
        self.v.addWidget(self.btn_settings)
        self.set_expanded(True,instant=True)
        _log("[+]",f"Sidebar ready expanded_w={self.expanded_w} collapsed_w={self.collapsed_w}")
    def resizeEvent(self,e):
        if e is None:
            return
        super().resizeEvent(e)
    def set_expanded(self,expanded,instant=False):
        self._expanded=expanded
        self.v.setContentsMargins(self._side_pad,self._side_pad,self._side_pad,self._side_pad)
        btns=[self.btn_chat,self.btn_notes,self.btn_commands,self.btn_target,self.btn_search,self.btn_settings]
        for b in btns:
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if expanded:
                b.setText(f"\u2003{b._txt}");b.setMinimumWidth(0);b.setMaximumWidth(16777215)
            else:
                b.setText("");s=getattr(b,"btn_size",44);b.setMinimumWidth(s);b.setMaximumWidth(s)
        w=self.expanded_w if expanded else self.collapsed_w
        _log("[*]",f"Sidebar {'expanded' if expanded else 'collapsed'} width={w}")
        if instant:self.setMinimumWidth(w);self.setMaximumWidth(w);self.resizeEvent(None);return
        for a in (self.anim_max,self.anim_min):
            a.stop()
            a.setStartValue(self.maximumWidth() if a is self.anim_max else self.minimumWidth())
            a.setEndValue(w)
            a.start()
    def _toggle(self):self.set_expanded(not self._expanded)
    def select(self,key):
        self.btn_chat.setChecked(key=="chat")
        self.btn_notes.setChecked(key=="notes")
        self.btn_commands.setChecked(key=="commands")
        self.btn_target.setChecked(key=="targets")
        self.btn_search.setChecked(key=="searchcopy")
        self.btn_settings.setChecked(key=="settings")
class PlaceholderPage(QWidget):
    def __init__(self,title,subtitle="Coming soon...",parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        v=QVBoxLayout(self);v.setContentsMargins(22,22,22,22);v.setSpacing(10)
        t=QLabel(title);t.setObjectName("PageTitle")
        s=QLabel(subtitle);s.setObjectName("PageSubTitle");s.setWordWrap(True)
        v.addWidget(t);v.addWidget(s);v.addStretch(1)
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setObjectName("MainWindow")
        self.setWindowTitle(f"{APP_NAME} v{APP_VER}")
        g=QApplication.primaryScreen().availableGeometry()
        min_w=min(980,max(640,int(g.width()*0.6)))
        min_h=min(620,max(420,int(g.height()*0.6)))
        self.setMinimumSize(min_w,min_h)
        ico=_abs("Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico));_log("[+]",f"Window icon set: {ico}")
        else:_log("[-]",f"Window icon missing: {ico}")
        win_w=max(min_w,int(g.width()*0.8))
        win_h=max(min_h,int(g.height()*0.8))
        self.resize(min(win_w,g.width()),min(win_h,g.height()))
        self.root=QWidget();self.root.setObjectName("Root");self.setCentralWidget(self.root)
        compact=(g.width()<1100 or g.height()<700)
        pad=10 if compact else 14
        gap=8 if compact else 12
        h=QHBoxLayout(self.root);h.setContentsMargins(pad,pad,pad,pad);h.setSpacing(gap)
        self.sidebar=SideBar(self.on_nav)
        self.content=QFrame();self.content.setObjectName("ContentFrame")
        ch=QVBoxLayout(self.content);ch.setContentsMargins(0,0,0,0);ch.setSpacing(0)
        self.stack=QStackedWidget();self.stack.setObjectName("Stack")
        ch.addWidget(self.stack)
        h.addWidget(self.sidebar);h.addWidget(self.content,1)
        if compact:self.sidebar.set_expanded(False,instant=True)
        self.page_chat=self._build_chat()
        self.page_notes=self._build_notes()
        self.page_commands=self._build_commands()
        self.page_targets=self._build_targets()
        self.page_searchcopy=self._build_searchcopy()
        self._settings_loaded=False
        self.page_settings=PlaceholderPage("Settings","Loading settings...")
        self._mini_window=None
        self._mini_pending=False
        self._wire_live_db_refresh()
        self._start_log_cleanup()
        self._start_auto_backup()
        self.stack.addWidget(self.page_chat)
        self.stack.addWidget(self.page_notes)
        self.stack.addWidget(self.page_commands)
        self.stack.addWidget(self.page_targets)
        self.stack.addWidget(self.page_searchcopy)
        self.stack.addWidget(self.page_settings)
        self.on_nav("chat")
        _log("[+]",f"MainWindow ready")
    def _build_chat(self):
        w=_load_widget(_abs("Cores","LOYA_Chat","LOYA_Chat.py"),"Widget")
        return w if w else PlaceholderPage("LOYA","Coming soon...")
    def _build_notes(self):
        w=_load_widget(_abs("Cores","Note.py"),"Widget")
        return w if w else PlaceholderPage("Notes","Coming soon...")
    def _build_commands(self):
        w=_load_widget(_abs("Cores","CommandsNotes.py"),"Widget")
        return w if w else PlaceholderPage("Commands","Coming soon...")
    def _build_targets(self):
        w=_load_widget(_abs("Cores","Target.py"),"Widget")
        return w if w else PlaceholderPage("Targets","Coming soon.")
    def _build_searchcopy(self):
        w=_load_widget(_abs("Cores","SearchCore.py"),"Widget")
        return w if w else PlaceholderPage("Snippets","Coming soon...")
    def _build_settings(self):
        w=_load_widget(_abs("Cores","Settings.py"),"Widget")
        return w if w else PlaceholderPage("Settings","Coming soon...")
    def _ensure_settings_loaded(self):
        if self._settings_loaded:
            return
        old=self.page_settings
        new=self._build_settings()
        if not new:
            new=PlaceholderPage("Settings","Settings unavailable.")
        idx=self.stack.indexOf(old)
        if idx<0:
            idx=self.stack.count()
        try:
            self.stack.removeWidget(old)
            old.setParent(None)
        except Exception:
            pass
        self.page_settings=new
        if idx<=self.stack.count():
            self.stack.insertWidget(idx,new)
        else:
            self.stack.addWidget(new)
        self._settings_loaded=True
    def on_nav(self,key):
        if self._mini_window and self._mini_window.isVisible():
            try:self._mini_window.hide()
            except:pass
        try:self.show()
        except:pass
        self.sidebar.select(key)
        m={"chat":0,"notes":1,"commands":2,"targets":3,"searchcopy":4,"settings":5}
        if key=="settings":
            self._ensure_settings_loaded()
        self.stack.setCurrentIndex(m.get(key,0))
        _log("[*]",f"Nav: {key}")
    def changeEvent(self,e):
        try:
            if self.isMinimized():
                if not getattr(self,"_mini_pending",False):
                    self._mini_pending=True
                    QTimer.singleShot(0,self._open_mini_from_minimize)
        except Exception:
            pass
        try:super().changeEvent(e)
        except Exception:pass
    def _open_mini_from_minimize(self):
        self._mini_pending=False
        if self._mini_window and self._mini_window.isVisible():
            try:self._mini_window.raise_();self._mini_window.activateWindow()
            except Exception:pass
            return
        try:self.setWindowState(self.windowState()&~Qt.WindowState.WindowMinimized)
        except Exception:pass
        self.open_mini()
    def open_mini(self):
        if self._mini_window is None:
            p=_abs("Cores","MiniWindow.py")
            if os.path.isfile(p):
                try:
                    spec=importlib.util.spec_from_file_location("mini_window",p)
                    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
                    cls=getattr(mod,"MiniWindow",None)
                    if cls:self._mini_window=cls(owner=self)
                except Exception as e:
                    _log("[!]",f"MiniWindow load error: {p} ({e})")
        if not self._mini_window:
            return
        try:
            self._mini_window.show()
            self._mini_window.raise_()
            self._mini_window.activateWindow()
            self.hide()
        except Exception:
            pass
    def restore_from_mini(self):
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        if self._mini_window:
            try:self._mini_window.hide()
            except Exception:pass
    def _wire_live_db_refresh(self):
        n=getattr(self,"page_notes",None)
        c=getattr(self,"page_commands",None)
        s=getattr(self,"page_searchcopy",None)
        t=getattr(self,"page_targets",None)
        def _refresh_all():
            for w in (c,s,t):
                if not w:continue
                try:
                    if hasattr(w,"reload"):w.reload()
                    elif hasattr(w,"refresh"):w.refresh()
                except:pass
        if n and hasattr(n,"note_saved"):
            try:n.note_saved.connect(_refresh_all)
            except:pass
        if c and hasattr(c,"command_saved"):
            try:c.command_saved.connect(_refresh_all)
            except:pass
    def _start_log_cleanup(self):
        self._log_timer=QTimer(self);self._log_timer.setInterval(21600000);self._log_timer.timeout.connect(lambda:_purge_old_logs(30));self._log_timer.start();_purge_old_logs(30)
    def _start_auto_backup(self):
        QTimer.singleShot(1500,_auto_backup_if_needed)
def _set_windows_app_id():
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.{APP_VER}")
        _log("[+]",f"AppUserModelID set: {APP_NAME}.{APP_VER}")
    except Exception as e:
        _log("[-]",f"AppUserModelID failed ({e})")
def main():
    _log("[*]",f"Start {APP_NAME} v{APP_VER}")
    _set_windows_app_id()
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME);app.setApplicationDisplayName(APP_NAME)
    ico=_abs("Assets","logox.png")
    if os.path.isfile(ico):
        qi=QIcon(ico);app.setWindowIcon(qi);_log("[+]",f"App icon set: {ico}")
    else:_log("[-]",f"App icon missing: {ico}")
    qss=_load_qss()
    if qss:app.setStyleSheet(qss);_log("[+]",f"Theme applied")
    if not _security_unlock_if_needed(None):
        _log("[*]","Security unlock cancelled")
        sys.exit(0)
    try:app.aboutToQuit.connect(_security_encrypt_on_exit)
    except:pass
    w=MainWindow();w.show();_log("[+]",f"Window shown")
    r=app.exec();_log("[*]",f"Exit code: {r}");sys.exit(r)
if __name__=="__main__":main()
