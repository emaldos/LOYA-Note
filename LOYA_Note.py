import os,sys,importlib.util,logging,time,subprocess
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QSize,QPropertyAnimation,QEasingCurve,QTimer
from PyQt6.QtGui import QIcon,QCursor
from PyQt6.QtWidgets import QApplication,QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QFrame,QLabel,QStackedWidget,QSizePolicy,QToolButton,QMessageBox,QLineEdit,QComboBox,QSpinBox,QTextEdit,QPlainTextEdit,QTextBrowser,QPushButton,QSizeGrip
from Cores.Update import health_check as _health_check
from Cores.Update import APP_NAME as _UPDATE_APP_NAME
from Cores.Update import DEFAULT_APP_VERSION as _DEFAULT_APP_VERSION
from Cores.Update import ensure_runtime_files as _ensure_update_runtime
from Cores.Update import finalize_pending_update_on_launch as _finalize_pending_update_on_launch
from Cores.Update import get_app_version as _get_app_version
from Cores.Update import get_windows_app_id as _get_windows_app_id
from Cores.Update import sync_installed_version as _sync_installed_version
APP_NAME=_UPDATE_APP_NAME
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _app_version():
    try:return _get_app_version()
    except Exception:return _DEFAULT_APP_VERSION
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
def _console_python():
    py=os.path.abspath(sys.executable)
    if os.name=="nt" and py.lower().endswith("pythonw.exe"):
        alt=py[:-5]+".exe"
        if os.path.isfile(alt):return alt
    return py
def _open_recovery_mode(reason=""):
    script=_abs("RunNote.py")
    if not os.path.isfile(script):return False
    cmd=[_console_python(),script,"--recovery"]
    if reason:cmd+=["--reason",str(reason)]
    try:
        if os.name=="nt":subprocess.Popen(cmd,cwd=_abs(),stdin=subprocess.DEVNULL,creationflags=0x00000010)
        else:subprocess.Popen(cmd,cwd=_abs(),stdin=subprocess.DEVNULL,start_new_session=True)
        return True
    except Exception as e:
        _log("[!]",f"Recovery launcher failed ({e})")
        return False
def _show_health_failure(text):
    try:
        mb=QMessageBox()
        mb.setIcon(QMessageBox.Icon.Critical)
        mb.setWindowTitle("Startup Health Check")
        mb.setText(text)
        brec=mb.addButton("Open Recovery",QMessageBox.ButtonRole.ActionRole)
        mb.addButton("Close",QMessageBox.ButtonRole.RejectRole)
        mb.exec()
        return mb.clickedButton()==brec
    except Exception:
        return False
def _on_app_about_to_quit():
    _security_encrypt_on_exit()
    try:_health_check.mark_launch_completed(True)
    except Exception as e:_log("[!]",f"Launch state completion failed ({e})")
class BottomNavBtn(QToolButton):
    def __init__(self,icon_path,text,parent=None):
        super().__init__(parent)
        self._txt=text
        self.setObjectName("BottomNavBtn")
        self.setCheckable(True);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        self.setFixedSize(78,50);self.setIconSize(QSize(18,18))
        if icon_path and os.path.isfile(icon_path):self.setIcon(QIcon(icon_path))
        f=self.font();f.setBold(True);self.setFont(f)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setText(text)
class BottomNav(QFrame):
    def __init__(self,on_select,parent=None):
        super().__init__(parent)
        self.on_select=on_select
        self.setObjectName("BottomNav")
        self.collapsed_h=12;self.expanded_h=76;self._expanded=False
        self.setMouseTracking(True);self.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed);self.setFixedWidth(490)
        self.setMinimumHeight(self.collapsed_h);self.setMaximumHeight(self.collapsed_h)
        self.anim_max=QPropertyAnimation(self,b"maximumHeight");self.anim_min=QPropertyAnimation(self,b"minimumHeight")
        for a in (self.anim_max,self.anim_min):a.setDuration(220);a.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.v=QVBoxLayout(self);self.v.setContentsMargins(8,3,8,6);self.v.setSpacing(4)
        self.handle=QFrame(self);self.handle.setObjectName("BottomNavHandle");self.handle.setFixedSize(90,4)
        self.row=QFrame(self);self.row.setObjectName("BottomNavRow")
        r=QHBoxLayout(self.row);r.setContentsMargins(0,0,0,0);r.setSpacing(8)
        self.btn_notes=BottomNavBtn(_abs("Assets","Home.png"),"Notes")
        self.btn_commands=BottomNavBtn(_abs("Assets","command-line.png"),"Commands")
        self.btn_target=BottomNavBtn(_abs("Assets","Target.png"),"Targets")
        self.btn_search=BottomNavBtn(_abs("Assets","Search.png"),"Snippets")
        self.btn_settings=BottomNavBtn(_abs("Assets","Setting.png"),"Settings")
        self.btn_notes.clicked.connect(lambda:self.on_select("notes"))
        self.btn_commands.clicked.connect(lambda:self.on_select("commands"))
        self.btn_target.clicked.connect(lambda:self.on_select("targets"))
        self.btn_search.clicked.connect(lambda:self.on_select("searchcopy"))
        self.btn_settings.clicked.connect(lambda:self.on_select("settings"))
        r.addStretch(1)
        for b in (self.btn_notes,self.btn_commands,self.btn_target,self.btn_search,self.btn_settings):r.addWidget(b)
        r.addStretch(1)
        self.v.addWidget(self.handle,0,Qt.AlignmentFlag.AlignHCenter)
        self.v.addWidget(self.row,0)
        self.set_expanded(False,instant=True)
        _log("[+]",f"Bottom nav ready expanded_h={self.expanded_h} collapsed_h={self.collapsed_h}")
    def set_expanded(self,expanded,instant=False):
        if self._expanded==expanded and not instant:return
        self._expanded=expanded
        h=self.expanded_h if expanded else self.collapsed_h
        if expanded:self.row.setVisible(True)
        _log("[*]",f"Bottom nav {'expanded' if expanded else 'collapsed'} height={h}")
        if instant:
            self.setMinimumHeight(h);self.setMaximumHeight(h);self.row.setVisible(expanded);return
        for a in (self.anim_max,self.anim_min):
            a.stop()
            a.setStartValue(self.maximumHeight() if a is self.anim_max else self.minimumHeight())
            a.setEndValue(h)
            a.start()
        if not expanded:QTimer.singleShot(230,self._hide_row_if_collapsed)
    def _hide_row_if_collapsed(self):
        if not self._expanded:self.row.setVisible(False)
    def enterEvent(self,e):
        self.set_expanded(True)
        try:super().enterEvent(e)
        except Exception:pass
    def leaveEvent(self,e):
        QTimer.singleShot(140,self._hide_if_out)
        try:super().leaveEvent(e)
        except Exception:pass
    def _hide_if_out(self):
        try:
            if self.rect().contains(self.mapFromGlobal(QCursor.pos())):return
        except Exception:pass
        self.set_expanded(False)
    def select(self,key):
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
class AppTitleBar(QFrame):
    def __init__(self,owner,parent=None):
        super().__init__(parent)
        self.owner=owner
        self._drag_pos=None
        self.setObjectName("AppTitleBar")
        self.setFixedHeight(42)
        self.setMouseTracking(True)
        h=QHBoxLayout(self);h.setContentsMargins(12,0,8,0);h.setSpacing(8)
        self.ico=QLabel(self);self.ico.setObjectName("AppTitleIcon");self.ico.setFixedSize(24,24)
        ip=_abs("Assets","logox.png")
        if os.path.isfile(ip):self.ico.setPixmap(QIcon(ip).pixmap(QSize(22,22)))
        self.title=QLabel(f"{APP_NAME} v{_app_version()}",self);self.title.setObjectName("AppTitleText")
        self.btn_shrink=self._btn("WindowShrinkBtn","Mini Screen",_abs("Assets","Shrink.png"),"")
        self.btn_min=self._btn("WindowControlBtn","Minimize",_abs("Assets","minimize-sign.png"),"-")
        self.btn_max=self._btn("WindowControlBtn","Maximize",_abs("Assets","window.png"),"[]")
        self.btn_close=self._btn("WindowCloseBtn","Close",_abs("Assets","Close.png"),"X")
        self.btn_shrink.clicked.connect(owner.open_mini)
        self.btn_min.clicked.connect(owner.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(owner.close)
        h.addWidget(self.ico,0);h.addWidget(self.title,0);h.addStretch(1)
        for b in (self.btn_shrink,self.btn_min,self.btn_max,self.btn_close):h.addWidget(b,0)
    def _btn(self,obj,tip,icon_path="",text=""):
        b=QToolButton(self);b.setObjectName(obj);b.setCursor(Qt.CursorShape.PointingHandCursor);b.setToolTip(tip);b.setFixedSize(34,30)
        if icon_path and os.path.isfile(icon_path):b.setIcon(QIcon(icon_path));b.setIconSize(QSize(16,16));b.setText("")
        else:b.setText(text)
        return b
    def _set_btn_icon(self,b,path,text):
        if path and os.path.isfile(path):b.setIcon(QIcon(path));b.setIconSize(QSize(16,16));b.setText("")
        else:b.setIcon(QIcon());b.setText(text)
    def _toggle_max(self):
        if self.owner.isMaximized():self.owner.showNormal()
        else:self.owner.showMaximized()
        self.sync_state()
    def sync_state(self):
        try:
            if self.owner.isMaximized():
                self._set_btn_icon(self.btn_max,_abs("Assets","maximize.png"),"[]");self.btn_max.setToolTip("Restore")
            else:
                self._set_btn_icon(self.btn_max,_abs("Assets","window.png"),"[]");self.btn_max.setToolTip("Maximize")
        except Exception:pass
    def mouseDoubleClickEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:self._toggle_max();e.accept();return
        try:super().mouseDoubleClickEvent(e)
        except Exception:pass
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._drag_pos=e.globalPosition().toPoint()-self.owner.frameGeometry().topLeft();e.accept();return
        try:super().mousePressEvent(e)
        except Exception:pass
    def mouseMoveEvent(self,e):
        if self._drag_pos is not None and e.buttons()&Qt.MouseButton.LeftButton:
            if self.owner.isMaximized():
                ratio=e.position().x()/max(1,self.width())
                self.owner.showNormal()
                geo=self.owner.frameGeometry()
                self.owner.move(e.globalPosition().toPoint().x()-int(geo.width()*ratio),max(0,e.globalPosition().toPoint().y()-20))
                self._drag_pos=e.globalPosition().toPoint()-self.owner.frameGeometry().topLeft()
            self.owner.move(e.globalPosition().toPoint()-self._drag_pos);e.accept();return
        try:super().mouseMoveEvent(e)
        except Exception:pass
    def mouseReleaseEvent(self,e):
        self._drag_pos=None
        try:super().mouseReleaseEvent(e)
        except Exception:pass
def _apply_control_sizing(root):
    try:
        for b in root.findChildren((QToolButton,QPushButton)):
            if b.objectName() in ("BottomNavBtn","WindowControlBtn","WindowCloseBtn","WindowShrinkBtn","MiniQuickBtn"):continue
            try:b.setFixedHeight(38)
            except Exception:pass
        for w in root.findChildren((QLineEdit,QComboBox,QSpinBox)):
            if not w.objectName():continue
            try:w.setFixedHeight(38)
            except Exception:pass
        for w in root.findChildren((QTextEdit,QPlainTextEdit,QTextBrowser)):
            name=w.objectName()
            if not name:continue
            if name=="CmdBoxCommand":continue
            try:w.setMinimumWidth(260)
            except Exception:pass
            try:
                if name in ("NoteArea","NoteNavDisplay","TargetJsonEdit","LOYATerminal"):w.setMinimumHeight(180)
                elif "Command" in name or "Cmd" in name:w.setMinimumHeight(110)
            except Exception:pass
        for w in root.findChildren((QLineEdit,QComboBox)):
            name=w.objectName()
            if not name:continue
            try:
                if "PerPage" in name:w.setMinimumWidth(88);w.setMaximumWidth(100)
                elif name in ("TargetStatus",):w.setMinimumWidth(120);w.setMaximumWidth(150)
                elif "Search" in name or name=="AIPathInput":w.setMinimumWidth(260)
                elif "Filter" in name:w.setMinimumWidth(220)
                elif "Description" in name or "Tags" in name or "Program" in name:w.setMinimumWidth(240)
                elif "Category" in name or "SubCategory" in name or name in ("NoteGroup","CmdNoteName","LOYASessionCombo"):w.setMinimumWidth(170)
                elif "Name" in name or "Title" in name:w.setMinimumWidth(220)
                elif "Field" in name or "KeyInput" in name:w.setMinimumWidth(160)
            except Exception:pass
    except Exception:pass
class MainWindow(QMainWindow):
    def __init__(self,startup_report=None):
        super().__init__()
        self._startup_report=startup_report
        self.setObjectName("MainWindow")
        self.setWindowTitle(f"{APP_NAME} v{_app_version()}")
        self.setWindowFlags(self.windowFlags()|Qt.WindowType.FramelessWindowHint)
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
        v=QVBoxLayout(self.root);v.setContentsMargins(pad,pad,pad,pad);v.setSpacing(gap)
        self.title_bar=AppTitleBar(self,self.root)
        self.content=QFrame();self.content.setObjectName("ContentFrame")
        ch=QVBoxLayout(self.content);ch.setContentsMargins(0,0,0,0);ch.setSpacing(0)
        self.stack=QStackedWidget();self.stack.setObjectName("Stack")
        ch.addWidget(self.stack)
        self.nav=BottomNav(self.on_nav)
        v.addWidget(self.title_bar,0);v.addWidget(self.content,1);v.addWidget(self.nav,0,Qt.AlignmentFlag.AlignHCenter)
        self.page_notes=self._build_notes()
        self.page_commands=self._build_commands()
        self.page_targets=self._build_targets()
        self.page_searchcopy=self._build_searchcopy()
        self._settings_loaded=False
        self.page_settings=PlaceholderPage("Settings","Loading settings...")
        self._mini_window=None
        self.size_grip=QSizeGrip(self.root);self.size_grip.setObjectName("WindowSizeGrip");self.size_grip.setFixedSize(18,18);self.size_grip.raise_()
        self._wire_live_db_refresh()
        self._start_log_cleanup()
        self._start_auto_backup()
        self.stack.addWidget(self.page_notes)
        self.stack.addWidget(self.page_commands)
        self.stack.addWidget(self.page_targets)
        self.stack.addWidget(self.page_searchcopy)
        self.stack.addWidget(self.page_settings)
        _apply_control_sizing(self)
        self.on_nav("notes")
        QTimer.singleShot(0,self._show_startup_notice)
        _log("[+]",f"MainWindow ready")
    def resizeEvent(self,e):
        try:self.title_bar.sync_state()
        except Exception:pass
        try:self.size_grip.move(max(0,self.root.width()-22),max(0,self.root.height()-22));self.size_grip.raise_()
        except Exception:pass
        try:super().resizeEvent(e)
        except Exception:pass
    def changeEvent(self,e):
        try:self.title_bar.sync_state()
        except Exception:pass
        try:super().changeEvent(e)
        except Exception:pass
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
        _apply_control_sizing(new)
    def on_nav(self,key):
        if self._mini_window and self._mini_window.isVisible():
            try:self._mini_window.hide()
            except:pass
        self.nav.select(key)
        m={"notes":0,"commands":1,"targets":2,"searchcopy":3,"settings":4}
        if key=="settings":
            self._ensure_settings_loaded()
        self.stack.setCurrentIndex(m.get(key,0))
        if key=="settings":
            try:
                hook=getattr(self.page_settings,"on_page_activated",None)
                if callable(hook):hook()
            except Exception:
                pass
        if key=="searchcopy":
            try:
                s=getattr(self,"page_searchcopy",None)
                if hasattr(s,"reload"):s.reload()
                elif hasattr(s,"refresh"):s.refresh()
            except Exception:
                pass
        _apply_control_sizing(self)
        QTimer.singleShot(0,lambda:_apply_control_sizing(self))
        _log("[*]",f"Nav: {key}")
    def open_mini(self):
        if self._mini_window is None:
            p=_abs("Cores","MiniWindow.py")
            if os.path.isfile(p):
                try:
                    spec=importlib.util.spec_from_file_location("mini_window",p)
                    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
                    cls=getattr(mod,"MiniWindow",None)
                    if cls:self._mini_window=cls(owner=self);_apply_control_sizing(self._mini_window)
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
    def _show_startup_notice(self):
        rep=self._startup_report
        if not rep or not rep.has_notice():
            return
        if rep.warnings:
            self.on_nav("settings")
        try:QMessageBox.information(self,"Startup Health Check",rep.notice_text())
        except Exception:pass
def _set_windows_app_id():
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        app_id=_get_windows_app_id(_app_version())
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        _log("[+]",f"AppUserModelID set: {app_id}")
    except Exception as e:
        _log("[-]",f"AppUserModelID failed ({e})")
def main():
    try:
        _ensure_update_runtime()
        _sync_installed_version()
    except Exception as e:
        _log("[!]",f"Update runtime init failed ({e})")
    app_ver=_app_version()
    _log("[*]",f"Start {APP_NAME} v{app_ver}")
    _set_windows_app_id()
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME);app.setApplicationDisplayName(APP_NAME)
    ico=_abs("Assets","logox.png")
    if os.path.isfile(ico):
        qi=QIcon(ico);app.setWindowIcon(qi);_log("[+]",f"App icon set: {ico}")
    else:_log("[-]",f"App icon missing: {ico}")
    qss=_load_qss()
    if qss:app.setStyleSheet(qss);_log("[+]",f"Theme applied")
    startup_report=_health_check.run_health_check(after_security=False)
    if startup_report.fatal:
        _log("[-]",startup_report.fatal_text().replace("\n"," | "))
        try:_health_check.mark_launch_completed(False,startup_report.fatal_text())
        except Exception as e:_log("[!]",f"Launch failure record failed ({e})")
        if _show_health_failure(startup_report.fatal_text()):_open_recovery_mode(startup_report.fatal_text())
        return 8
    if not _security_unlock_if_needed(None):
        _log("[*]","Security unlock cancelled")
        sys.exit(0)
    post_security_report=_health_check.run_health_check(after_security=True)
    startup_report.merge(post_security_report)
    if startup_report.fatal:
        _log("[-]",startup_report.fatal_text().replace("\n"," | "))
        try:_health_check.mark_launch_completed(False,startup_report.fatal_text())
        except Exception as e:_log("[!]",f"Launch failure record failed ({e})")
        if _show_health_failure(startup_report.fatal_text()):_open_recovery_mode(startup_report.fatal_text())
        return 8
    try:_health_check.mark_launch_started()
    except Exception as e:_log("[!]",f"Launch state start failed ({e})")
    try:app.aboutToQuit.connect(_on_app_about_to_quit)
    except:pass
    try:
        w=MainWindow(startup_report=startup_report);w.show();_log("[+]",f"Window shown")
        try:
            fin=_finalize_pending_update_on_launch(_app_version())
            if fin.get("completed"):
                _log("[+]",f"Update confirmed after startup: {fin.get('version','')}")
        except Exception as e:_log("[!]",f"Update finalize after startup failed ({e})")
    except Exception as e:
        msg=f"Window startup failed ({e})"
        _log("[!]",msg)
        try:_health_check.mark_launch_completed(False,msg)
        except Exception as state_exc:_log("[!]",f"Launch state failure record failed ({state_exc})")
        if _show_health_failure(msg):_open_recovery_mode(msg)
        return 9
    r=app.exec();_log("[*]",f"Exit code: {r}");sys.exit(r)
if __name__=="__main__":raise SystemExit(main())
