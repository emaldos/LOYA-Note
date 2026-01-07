import os,json,logging,hashlib,re
from logging.handlers import RotatingFileHandler
from datetime import datetime,timezone
from PyQt6.QtCore import Qt,QSize,QTimer
from PyQt6.QtGui import QColor,QIcon,QIntValidator
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QToolButton,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QComboBox,QTabWidget,QSplitter,QPlainTextEdit,QAbstractItemView,QDialog,QApplication,QScrollArea,QGridLayout
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("Target");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"Target_log.log"))
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
def _data_dir():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True);return d
def _paths():
    d=_data_dir()
    vp=os.path.join(d,"target_values.json")
    p_new=os.path.join(d,"Targets.json")
    p_old=os.path.join(d,"Targes.json")
    tp=p_new if os.path.isfile(p_new) or not os.path.isfile(p_old) else p_old
    return vp,tp
def _now():return datetime.now(timezone.utc).isoformat()
def _norm(s):return (str(s) if s is not None else "").strip()
def _kci(s):return _norm(s).lower()
def _sid(s):return hashlib.sha256(_norm(s).lower().encode("utf-8")).hexdigest()[:16]
def _clamp_u16(n):
    try:n=int(n)
    except:return 0
    if n<0:n=0
    if n>65535:n=65535
    return n
def _priority_from(v):
    if isinstance(v,dict):
        return v.get("priority",v.get("value",0))
    return v
def _read_json(p,default):
    try:
        if not os.path.isfile(p):return default
        with open(p,"r",encoding="utf-8") as f:
            v=json.load(f)
            return v if v is not None else default
    except Exception as e:
        _log("[!]",f"Read JSON failed: {p} ({e})")
        return default
def _write_json(p,obj):
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        t=p+".tmp"
        with open(t,"w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(t,p)
        return True
    except Exception as e:
        _log("[!]",f"Write JSON failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _pretty(obj):return json.dumps(obj,ensure_ascii=False,indent=2)
def _asset_icon(*names):
    for n in names:
        p=_abs("..","Assets",n)
        if os.path.isfile(p):return QIcon(p)
    return QIcon()
class Store:
    def __init__(self):
        self.values_path,self.targets_path=_paths()
        self.values=self._load_values()
        self.targets=self._load_targets()
        self._prune_targets_to_current_keys(save=True)
    def ordered_keys(self):
        items=[(k,_clamp_u16(_priority_from(v))) for k,v in self.values.items()]
        items.sort(key=lambda x:(x[1],x[0].lower()))
        return [k for k,_ in items]
    def _load_values(self):
        d=_read_json(self.values_path,{"IP":"","URL":""})
        out={}
        def addk(k,val):
            nk=_norm(k)
            if not nk:return
            lk=_kci(nk)
            for ex in list(out.keys()):
                if _kci(ex)==lk:return
            out[nk]={"priority":_clamp_u16(val)}
        if isinstance(d,list):
            for it in d:
                if isinstance(it,str):addk(it,0)
                elif isinstance(it,dict):
                    k=it.get("key") if "key" in it else it.get("name")
                    addk(k,it.get("priority",it.get("value",0)))
        elif isinstance(d,dict):
            for k,v in d.items():
                if isinstance(v,dict):addk(k,v.get("priority",v.get("value",0)))
                elif isinstance(v,int):addk(k,v)
                else:addk(k,0)
        if not out:out={"IP":{"priority":0},"URL":{"priority":1}}
        changed=False
        for k,v in out.items():
            if not isinstance(v,dict) or "priority" not in v:
                out[k]={"priority":_clamp_u16(_priority_from(v))};changed=True
            else:
                vv=_clamp_u16(v.get("priority",0))
                if vv!=v.get("priority"):out[k]["priority"]=vv;changed=True
        if changed or not (isinstance(d,dict) and all(isinstance(v,dict) and "priority" in v for v in d.values())):_write_json(self.values_path,out)
        _log("[+]",f"Values loaded: {len(out)}")
        return out
    def _load_targets(self):
        d=_read_json(self.targets_path,[])
        if not isinstance(d,list):d=[]
        out=[]
        for t in d:
            if not isinstance(t,dict):continue
            name=_norm(t.get("name",""))
            if not name:continue
            st=_kci(t.get("status","not_used"))
            st="live" if st=="live" else "not_used"
            vals=t.get("values",{})
            if not isinstance(vals,dict):vals={}
            out.append({"id":t.get("id") or _sid(name),"name":name,"status":st,"values":{str(k):("" if v is None else str(v)) for k,v in vals.items()},"created":t.get("created") or _now(),"updated":t.get("updated") or _now()})
        _log("[+]",f"Targets loaded: {len(out)}")
        return out
    def save_values(self):return _write_json(self.values_path,{k:{"priority":_clamp_u16(_priority_from(v))} for k,v in self.values.items()})
    def save_targets(self):
        for t in self.targets:
            v=t.get("values",{})
            if not isinstance(v,dict):v={}
            t["values"]={k:_norm(vv) for k,vv in v.items() if _norm(k) and _norm(vv)}
        return _write_json(_abs("..","Data","Targets.json"),self.targets)
    def _sync_targets_keys(self,save=False):
        keys=self.ordered_keys()
        kset_ci={_kci(k) for k in keys}
        changed=False
        for t in self.targets:
            v=t.get("values",{})
            if not isinstance(v,dict):v={}
            nv={}
            for k in keys:nv[k]="" if v.get(k) is None else str(v.get(k,""))
            for k0,val0 in v.items():
                if _kci(k0) in kset_ci and k0 not in nv:
                    for kk in keys:
                        if _kci(kk)==_kci(k0):nv[kk]="" if val0 is None else str(val0);break
            if nv!=v:
                t["values"]=nv
                t["updated"]=_now()
                changed=True
        if save and changed:self.save_targets()
    def add_key(self,k,val):
        nk=_norm(k)
        if not nk:return False,"Key is empty"
        lk=_kci(nk)
        if lk in {_kci(x) for x in self.values.keys()}:return False,"Key already exists (case-insensitive)"
        self.values[nk]={"priority":_clamp_u16(val)}
        if not self.save_values():return False,"Save failed"
        return True,"Added"
    def remove_key(self,k):
        lk=_kci(k)
        found=None
        for kk in list(self.values.keys()):
            if _kci(kk)==lk:found=kk;break
        if not found:return False,"Key not found"
        self.values.pop(found,None)
        if not self.values:self.values={"IP":{"priority":0},"URL":{"priority":1}}
        if not self.save_values():return False,"Save failed"
        self._prune_targets_to_current_keys(save=True)
        return True,"Removed"
    def apply_values_json(self,raw):
        out={}
        def addk(k,val):
            nk=_norm(k)
            if not nk:return
            lk=_kci(nk)
            for ex in list(out.keys()):
                if _kci(ex)==lk:return
            out[nk]={"priority":_clamp_u16(val)}
        if isinstance(raw,dict):
            for k,v in raw.items():
                if isinstance(v,dict):addk(k,v.get("priority",v.get("value",0)))
                elif isinstance(v,int):addk(k,v)
                else:addk(k,0)
        elif isinstance(raw,list):
            for it in raw:
                if isinstance(it,dict):addk(it.get("key") if "key" in it else it.get("name"),it.get("priority",it.get("value",0)))
                elif isinstance(it,str):addk(it,0)
        else:return False,"JSON must be an object or a list"
        if not out:return False,"At least one key is required"
        self.values=out
        if not self.save_values():return False,"Save failed"
        self._prune_targets_to_current_keys(save=True)
        return True,"Applied"
    def upsert_target(self,tid,name,status,vals):
        name=_norm(name)
        if not name:return False,"Target name is required"
        keys=self.ordered_keys()
        nv={}
        if isinstance(vals,dict):
            for k in keys:
                vv=_norm(vals.get(k,""))
                if vv:nv[k]=vv
            for k0,val0 in vals.items():
                for kk in keys:
                    if _kci(kk)==_kci(k0) and kk not in nv:
                        vv=_norm(val0)
                        if vv:nv[kk]=vv
                        break
        now=_now()
        if tid:
            for t in self.targets:
                if t["id"]==tid:
                    t["name"]=name
                    t["values"]=nv
                    t["updated"]=now
                    return (True,"Updated") if self.save_targets() else (False,"Save failed")
        if _kci(name) in {_kci(t["name"]) for t in self.targets}:return False,"Target name already exists (case-insensitive)"
        self.targets.append({"id":_sid(name+now),"name":name,"status":"not_used","values":nv,"created":now,"updated":now})
        return (True,"Created") if self.save_targets() else (False,"Save failed")
    def delete_target(self,tid):
        before=len(self.targets)
        self.targets=[t for t in self.targets if t["id"]!=tid]
        if len(self.targets)==before:return False,"Not found"
        return (True,"Deleted") if self.save_targets() else (False,"Save failed")
    def set_live_target(self,tid):
        tid=_norm(tid)
        if not tid:return False,"Missing id"
        found=None
        for t in self.targets:
            if t.get("id")==tid:found=t;break
        if not found:return False,"Not found"
        was_live=_kci(found.get("status","not_used"))=="live"
        changed=False
        now=_now()
        if was_live:
            for t in self.targets:
                cur=_kci(t.get("status","not_used"))
                if cur!="not_used":
                    t["status"]="not_used"
                    t["updated"]=now
                    changed=True
            if not changed:return True,"No change"
            return (True,"Cleared") if self.save_targets() else (False,"Save failed")
        for t in self.targets:
            cur=_kci(t.get("status","not_used"))
            want="live" if t.get("id")==tid else "not_used"
            if cur!=want:
                t["status"]=want
                t["updated"]=now
                changed=True
        if not changed:return True,"No change"
        return (True,"Using") if self.save_targets() else (False,"Save failed")
    def _prune_targets_to_current_keys(self,save=False):
        keys_ci={_kci(k) for k in self.ordered_keys()}
        changed=False
        for t in self.targets:
            v=t.get("values",{})
            if not isinstance(v,dict):v={}
            nv={}
            for k,val in v.items():
                kk=_norm(k)
                vv=_norm(val)
                if not kk or not vv:continue
                if _kci(kk) in keys_ci:nv[kk]=vv
            if nv!=v:
                t["values"]=nv
                t["updated"]=_now()
                changed=True
        if save and changed:self.save_targets()
    def set_target_status(self,tid,status):
        st="live" if _kci(status)=="live" else "not_used"
        now=_now()
        for t in self.targets:
            if t.get("id")==tid:
                t["status"]=st
                t["updated"]=now
                return (True,"Updated") if self.save_targets() else (False,"Save failed")
        return False,"Not found"
class _Toast(QFrame):
    def __init__(self,parent,msg=""):
        super().__init__(None)
        self._parent=parent
        self.setObjectName("Toast")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
        v=QVBoxLayout(self);v.setContentsMargins(14,12,14,12);v.setSpacing(0)
        self.lbl=QLabel(msg,self);self.lbl.setObjectName("ToastMsg");self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.lbl,1)
        self._t=QTimer(self);self._t.setSingleShot(True);self._t.timeout.connect(self.close)
    def show_msg(self,msg,ms=3000):
        self.lbl.setText(msg)
        self.adjustSize()
        self._center()
        self.show()
        self.raise_()
        self._t.start(ms)
    def _center(self):
        try:
            p=self._parent.window() if self._parent and self._parent.window() else self._parent
            if not p:return
            g=p.frameGeometry()
            x=g.x()+(g.width()-self.width())//2
            y=g.y()+(g.height()-self.height())//2
            self.move(max(0,x),max(0,y))
        except:pass
class TargetEditorDialog(QDialog):
    def __init__(self,owner,store,target=None):
        super().__init__(owner)
        self.store=store
        self.target=target if isinstance(target,dict) else None
        self._editing_id=(self.target.get("id") if self.target else None)
        self.setObjectName("TargetDialog")
        self.setWindowTitle("Edit Target" if self.target else "Add Target")
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        self.resize(900,640)
        lay=QVBoxLayout(self);lay.setContentsMargins(14,14,14,14);lay.setSpacing(12)
        box=QFrame(self);box.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(box);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        head=QHBoxLayout();head.setSpacing(10)
        self.title=QLabel("Edit Target" if self.target else "Add Target",box);self.title.setObjectName("TargetFormTitle")
        head.addWidget(self.title,1)
        v.addLayout(head)
        r1=QHBoxLayout();r1.setSpacing(10)
        self.in_name=QLineEdit(box);self.in_name.setObjectName("TargetName");self.in_name.setPlaceholderText("Target name")
        r1.addWidget(QLabel("Name:",box),0);r1.addWidget(self.in_name,1)
        v.addLayout(r1)
        r2=QHBoxLayout();r2.setSpacing(10)
        self.find=QLineEdit(box);self.find.setObjectName("TargetFieldSearch");self.find.setPlaceholderText("Search field (e.g., IP, URL, MAC) ...")
        self.find.textChanged.connect(self._on_find_preview)
        self.find.returnPressed.connect(self._focus_first_match)
        r2.addWidget(QLabel("Find:",box),0);r2.addWidget(self.find,1)
        v.addLayout(r2)
        self.scroll=QScrollArea(box);self.scroll.setObjectName("TargetFieldsScroll");self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.wrap=QFrame(self.scroll);self.wrap.setObjectName("TargetFieldsWrap")
        self.grid=QGridLayout(self.wrap);self.grid.setContentsMargins(0,0,0,0);self.grid.setHorizontalSpacing(12);self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(1,1);self.grid.setColumnStretch(3,1)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.wrap)
        v.addWidget(self.scroll,1)
        fb=QHBoxLayout();fb.setSpacing(10)
        self.btn_save=QToolButton(box);self.btn_save.setObjectName("TargetSaveBtn");self.btn_save.setText("Save");self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel=QToolButton(box);self.btn_cancel.setObjectName("TargetCancelBtn");self.btn_cancel.setText("Cancel");self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(self.reject)
        fb.addStretch(1);fb.addWidget(self.btn_save,0);fb.addWidget(self.btn_cancel,0)
        v.addLayout(fb)
        lay.addWidget(box,1)
        self._fields={}
        self._labels={}
        self._rows={}
        self._order=[]
        self._rebuild_fields(self.target.get("values",{}) if self.target else {})
        if self.target:self.in_name.setText(_norm(self.target.get("name","")))
        self.in_name.setFocus()
    def _clear_grid(self):
        while self.grid.count():
            it=self.grid.takeAt(0)
            w=it.widget()
            if w:w.deleteLater()
    def _rebuild_fields(self,preserve):
        preserve=preserve if isinstance(preserve,dict) else {}
        self._fields={};self._labels={};self._rows={};self._order=[]
        self._clear_grid()
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        keys=self.store.ordered_keys()
        r=0;c=0
        for k in keys:
            le=QLineEdit(self.wrap);le.setObjectName("TargetField");le.setPlaceholderText(f"{k} value")
            le.setText("" if preserve.get(k) is None else str(preserve.get(k,"")))
            lab=QLabel(k+":",self.wrap)
            base=c*2
            self.grid.addWidget(lab,r,base,1,1)
            self.grid.addWidget(le,r,base+1,1,1)
            self._fields[k]=le
            self._labels[k]=lab
            self._rows[k]=r
            self._order.append(k)
            c+=1
            if c==2:c=0;r+=1
        used_rows=(len(keys)+1)//2
        self.grid.setRowStretch(used_rows,1)
    def _match_key(self,txt):
        q=_kci(txt)
        if not q:return None
        for k in self._order:
            if _kci(k)==q:return k
        for k in self._order:
            if q in _kci(k):return k
        return None
    def _scroll_to_key(self,k):
        try:
            r=self._rows.get(k,0)
            y=max(0,(r*44)-10)
            self.scroll.verticalScrollBar().setValue(y)
        except:pass
    def _focus_key(self,k):
        w=self._fields.get(k)
        if not w:return False
        self._scroll_to_key(k)
        w.setFocus()
        w.selectAll()
        return True
    def _on_find_preview(self,t):
        q=_kci(t)
        toks=[x for x in re.split(r"[,\s]+",q) if x]
        if not toks:
            for k in self._order:
                self._labels[k].setVisible(True)
                self._fields[k].setVisible(True)
            return
        first=None
        for k in self._order:
            kk=_kci(k)
            ok=any(x in kk for x in toks)
            self._labels[k].setVisible(ok)
            self._fields[k].setVisible(ok)
            if ok and first is None:first=k
        if first:self._scroll_to_key(first)
    def _focus_first_match(self):
        k=self._match_key(self.find.text())
        if k:self._focus_key(k)
    def _on_find(self,t):
        q=_norm(t)
        if not q:
            try:self.in_name.setFocus()
            except:pass
            return
        k=self._match_key(q)
        if k:self._focus_key(k)
    def _save(self):
        name=_norm(self.in_name.text())
        vals={k:w.text() for k,w in self._fields.items()}
        ok,msg=self.store.upsert_target(self._editing_id,name,None,vals)
        if not ok:
            QMessageBox.warning(self,"Save Target",msg)
            return
        self.accept()
class Widget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.store=Store()
        self._toast=_Toast(self)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("TargetFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        self.tabs=QTabWidget(self.frame);self.tabs.setObjectName("TargetTabs")
        v.addWidget(self.tabs,1)
        self.tab_targets=QWidget();self.tab_targets.setObjectName("Page")
        self.tab_elements=QWidget();self.tab_elements.setObjectName("Page")
        self.tabs.addTab(self.tab_targets,"Targets")
        self.tabs.addTab(self.tab_elements,"Set Elements")
        self._build_targets_tab()
        self._build_elements_tab()
        QTimer.singleShot(0,self._render_targets)
        QTimer.singleShot(0,self._render_keys)
        _log("[+]",f"Target ready")
    def _build_targets_tab(self):
        lay=QVBoxLayout(self.tab_targets);lay.setContentsMargins(0,0,0,0);lay.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.btn_add=QToolButton(self.tab_targets);self.btn_add.setObjectName("TargetAddBtn");self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.btn_add.setText("\u2003\u2003Add");self.btn_add.setIconSize(QSize(18,18))
        fa=self.btn_add.font();fa.setBold(True);fa.setWeight(800);self.btn_add.setFont(fa)
        self.btn_add.setIcon(_asset_icon("add.png","Add.png"))
        self.btn_add.clicked.connect(self._open_add)
        self.search=QLineEdit(self.tab_targets);self.search.setObjectName("TargetSearch");self.search.setPlaceholderText("Search targets...")
        self.search.textChanged.connect(lambda _:self._render_targets())
        top.addWidget(self.btn_add,0);top.addWidget(self.search,1)
        self.tbl_wrap=QFrame(self.tab_targets);self.tbl_wrap.setObjectName("TargetTableFrame")
        tw=QVBoxLayout(self.tbl_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.table=QTableWidget(self.tbl_wrap);self.table.setObjectName("TargetTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Target","Status","#","X"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.cellClicked.connect(self._on_target_cell)
        self.table.cellDoubleClicked.connect(self._on_target_double)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        fh=h.font();fh.setBold(True);fh.setWeight(800);h.setFont(fh)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2,44);self.table.setColumnWidth(3,44)
        tw.addWidget(self.table,1)
        lay.addLayout(top)
        lay.addWidget(self.tbl_wrap,1)
    def _build_elements_tab(self):
        lay=QVBoxLayout(self.tab_elements);lay.setContentsMargins(0,0,0,0);lay.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.key_in=QLineEdit(self.tab_elements);self.key_in.setObjectName("TargetKeyInput");self.key_in.setPlaceholderText("Key (e.g., IP, URL)")
        self.key_val=QLineEdit(self.tab_elements);self.key_val.setObjectName("TargetKeyInput");self.key_val.setPlaceholderText("Priority (0-65535)")
        self.key_val.setValidator(QIntValidator(0,65535,self.key_val))
        self.key_in.returnPressed.connect(self._add_key)
        self.key_val.returnPressed.connect(self._add_key)
        self.btn_key_add=QToolButton(self.tab_elements);self.btn_key_add.setObjectName("TargetMiniBtn");self.btn_key_add.setText("Add");self.btn_key_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_key_reload=QToolButton(self.tab_elements);self.btn_key_reload.setObjectName("TargetMiniBtn");self.btn_key_reload.setText("Reload");self.btn_key_reload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_json_apply=QToolButton(self.tab_elements);self.btn_json_apply.setObjectName("TargetMiniBtn");self.btn_json_apply.setText("Apply JSON");self.btn_json_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_key_add.clicked.connect(self._add_key)
        self.btn_key_reload.clicked.connect(self._reload_elements)
        self.btn_json_apply.clicked.connect(self._apply_json)
        top.addWidget(self.key_in,2);top.addWidget(self.key_val,1);top.addWidget(self.btn_key_add,0);top.addWidget(self.btn_key_reload,0);top.addWidget(self.btn_json_apply,0)
        lay.addLayout(top)
        sp=QSplitter(self.tab_elements);sp.setOrientation(Qt.Orientation.Horizontal)
        left=QFrame(sp);left.setObjectName("TargetKeysFrame")
        lv=QVBoxLayout(left);lv.setContentsMargins(10,10,10,10);lv.setSpacing(10)
        self.keys_table=QTableWidget(left);self.keys_table.setObjectName("TargetKeysTable")
        self.keys_table.setColumnCount(3)
        self.keys_table.setHorizontalHeaderLabels(["Key","Priority","X"])
        self.keys_table.verticalHeader().setVisible(False)
        self.keys_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.keys_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.keys_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.keys_table.setSortingEnabled(False)
        self.keys_table.setAlternatingRowColors(False)
        self.keys_table.setShowGrid(True)
        self.keys_table.cellClicked.connect(self._on_key_cell)
        kh=self.keys_table.horizontalHeader()
        kh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        kf=kh.font();kf.setBold(True);kf.setWeight(800);kh.setFont(kf)
        kh.setStretchLastSection(False)
        kh.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        kh.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        kh.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        self.keys_table.setColumnWidth(2,44)
        lv.addWidget(self.keys_table,1)
        right=QFrame(sp);right.setObjectName("TargetJsonFrame")
        rv=QVBoxLayout(right);rv.setContentsMargins(10,10,10,10);rv.setSpacing(10)
        self.json_edit=QPlainTextEdit(right);self.json_edit.setObjectName("TargetJsonEdit");self.json_edit.setPlaceholderText('{\n  "IP": { "priority": 0 },\n  "URL": { "priority": 1 }\n}')
        rv.addWidget(self.json_edit,1)
        sp.addWidget(left);sp.addWidget(right)
        sp.setStretchFactor(0,1);sp.setStretchFactor(1,2)
        lay.addWidget(sp,1)
    def _show_toast(self,msg,ms=3000):
        try:self._toast.show_msg(msg,ms)
        except:pass
    def _reload_elements(self):
        self._render_keys()
        self._render_targets()
    def _render_keys(self):
        items=[(k,_clamp_u16(_priority_from(v))) for k,v in self.store.values.items()]
        items.sort(key=lambda x:(x[1],x[0].lower()))
        self.keys_table.setRowCount(len(items))
        for r,(k,val) in enumerate(items):
            it=QTableWidgetItem(k);it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            v=QTableWidgetItem(str(val));v.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);v.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            x=QTableWidgetItem("X");x.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);x.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            f=x.font();f.setBold(True);f.setWeight(800);x.setFont(f)
            self.keys_table.setItem(r,0,it);self.keys_table.setItem(r,1,v);self.keys_table.setItem(r,2,x)
            self.keys_table.setRowHeight(r,44)
        self.keys_table.clearSelection()
        self.json_edit.setPlainText(_pretty({k:{"priority":_clamp_u16(_priority_from(v))} for k,v in self.store.values.items()}))
        _log("[*]",f"Keys rendered: {len(items)}")
    def _on_key_cell(self,row,col):
        if col!=2:return
        it=self.keys_table.item(row,0)
        if not it:return
        k=_norm(it.text())
        mods=QApplication.keyboardModifiers()
        if not (mods & Qt.KeyboardModifier.ShiftModifier):
            w=self.window() if self.window() else self
            if QMessageBox.question(w,"Remove Key",f"Remove key: {k}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        ok,msg=self.store.remove_key(k)
        if not ok:
            QMessageBox.warning(self,"Remove Key",msg)
            return
        self._reload_elements()
    def _add_key(self):
        k=_norm(self.key_in.text())
        vv=_norm(self.key_val.text())
        val=_clamp_u16(vv if vv!="" else 0)
        ok,msg=self.store.add_key(k,val)
        if not ok:
            QMessageBox.warning(self,"Add Key",msg)
            return
        self.key_in.clear();self.key_val.clear()
        self._reload_elements()
    def _apply_json(self):
        raw=_norm(self.json_edit.toPlainText())
        try:d=json.loads(raw or "{}")
        except Exception as e:
            QMessageBox.warning(self,"Apply JSON",f"Invalid JSON: {e}")
            return
        ok,msg=self.store.apply_values_json(d)
        if not ok:
            QMessageBox.warning(self,"Apply JSON",msg)
            return
        self._reload_elements()
        self._show_toast("Applied successfully",3000)
    def _status_text(self,st):
        st=_kci(st)
        return ("● Live",QColor(50,220,140)) if st=="live" else ("Not Used",QColor(220,220,220))
    def _render_targets(self):
        q=_kci(self.search.text())
        rows=[]
        for t in self.store.targets:
            blob=(t.get("name","")+" "+json.dumps(t.get("values",{}),ensure_ascii=False)).lower()
            if q and q not in blob:continue
            rows.append(t)
        rows.sort(key=lambda x:x.get("name","").lower())
        self.table.setRowCount(len(rows))
        for r,t in enumerate(rows):
            name=QTableWidgetItem(_norm(t.get("name","")));name.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);name.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            fn=name.font();fn.setBold(True);fn.setWeight(800);name.setFont(fn)
            name.setData(Qt.ItemDataRole.UserRole,t)
            st_txt,st_col=self._status_text(t.get("status","not_used"))
            st=QTableWidgetItem(st_txt);st.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);st.setTextAlignment(Qt.AlignmentFlag.AlignCenter);st.setForeground(st_col)
            ed=QTableWidgetItem("#");ed.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);ed.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            xd=QTableWidgetItem("X");xd.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);xd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fe=ed.font();fe.setBold(True);fe.setWeight(800);ed.setFont(fe);xd.setFont(fe)
            self.table.setItem(r,0,name);self.table.setItem(r,1,st);self.table.setItem(r,2,ed);self.table.setItem(r,3,xd)
            self.table.setRowHeight(r,44)
        self.table.clearSelection()
        _log("[*]",f"Targets rendered: {len(rows)}")
    def _row_target(self,row):
        it=self.table.item(row,0)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _open_add(self):
        dlg=TargetEditorDialog(self,self.store,None)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.store=dlg.store
            self._render_targets()
            _log("[+]",f"Target added")
    def _edit_target(self,t):
        dlg=TargetEditorDialog(self,self.store,t)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.store=dlg.store
            self._render_targets()
            _log("[+]",f"Target updated")
    def _delete_target(self,t,skip_confirm=False):
        name=_norm(t.get("name",""))
        if not skip_confirm:
            w=self.window() if self.window() else self
            if QMessageBox.question(w,"Delete",f"Delete target: {name}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        ok,msg=self.store.delete_target(t.get("id"))
        if not ok:
            QMessageBox.critical(self,"Delete",msg)
            return
        _log("[+]",f"Deleted target: {name}")
        self._render_targets()
    def _on_target_cell(self,row,col):
        t=self._row_target(row)
        if not t:return
        if col in (0,1):
            was_live=_kci(t.get("status","not_used"))=="live"
            ok,msg=self.store.set_live_target(t.get("id"))
            if not ok:QMessageBox.warning(self,"Use Target",msg);return
            self._render_targets()
            if was_live:self._show_toast("No target in use now",3000)
            else:self._show_toast(f"Using target: {t.get('name','')}",3000)
            return
        if col==2:return self._edit_target(t)
        if col==3:
            mods=QApplication.keyboardModifiers()
            return self._delete_target(t,skip_confirm=bool(mods & Qt.KeyboardModifier.ShiftModifier))
    def _on_target_double(self,row,col):
        t=self._row_target(row)
        if not t:return
        self._edit_target(t)
