import os,sqlite3,hashlib,json,base64
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QListWidget,QListWidgetItem,QAbstractItemView,QToolButton
from Cores import common_db as _common_db
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _norm(s):return ("" if s is None else str(s)).strip()
def _table_cols(cur,t):return _common_db.table_cols(cur,t)
def _ensure_schema(con):_common_db.ensure_schema(con)
def _clean_cmd(s):return ("" if s is None else str(s)).strip()
def cmd_norm_data(d):
    d=d or {}
    title=d.get("cmd_note_title","") if "cmd_note_title" in d else (d.get("title","") or d.get("note_name",""))
    return {"cmd_note_title":_norm(title),"category":_norm(d.get("category","")),"sub_category":_norm(d.get("sub_category","") or d.get("sub","")),"description":_norm(d.get("description","")),"tags":_norm(d.get("tags","")),"command":(d.get("command","") or "").rstrip()}
def cmd_id(d):
    x=cmd_norm_data(d);raw="|".join([x.get("cmd_note_title",""),x.get("category",""),x.get("sub_category",""),x.get("description",""),x.get("tags",""),_norm(x.get("command",""))])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12] if raw else ""
def encode_cmd_data(d):
    x=cmd_norm_data(d);x["cid"]=cmd_id(x)
    return base64.urlsafe_b64encode(json.dumps(x,ensure_ascii=False).encode("utf-8")).decode("ascii").rstrip("=")
def _command_rows(dbp):
    out=[]
    if not dbp or not os.path.isfile(dbp):return out
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con);cur=con.cursor();cols=set(_table_cols(cur,"Commands"))
            if not {"id","note_name","category","sub_category","command","tags"}.issubset(cols):return out
            has_desc="description" in cols;has_title="cmd_note_title" in cols;has_note_id="note_id" in cols
            sel="id"+(",note_id" if has_note_id else "")+",note_name,category,sub_category,command,tags"+(",description" if has_desc else "")+(",cmd_note_title" if has_title else "")
            cur.execute(f"SELECT {sel} FROM Commands")
            for r in cur.fetchall():
                i=0;rid=r[i];i+=1;nid=(r[i] if has_note_id else None);i+=1 if has_note_id else 0;nn=r[i];i+=1;cat=r[i];i+=1;sub=r[i];i+=1;cmd=r[i];i+=1;tags=r[i];i+=1;desc=(r[i] if has_desc else "");i+=1 if has_desc else 0;ttl=(r[i] if has_title else "")
                raw_ttl=_norm(ttl)
                out.append({"id":int(rid),"src":"Commands","note_id":int(nid) if str(nid).isdigit() else None,"note_name":_norm(nn),"cmd_note_title":raw_ttl,"title":raw_ttl or _norm(nn),"category":_norm(cat),"sub":_norm(sub),"sub_category":_norm(sub),"description":_norm(desc),"tags":_norm(tags),"command":_clean_cmd(cmd),"db":dbp})
    except Exception:return []
    return out
def related_command_rows(dbp,item):
    if not isinstance(item,dict) or item.get("src")!="Commands":return []
    rows=_command_rows(dbp);target=None;fallback=None
    try:item_id=int(item.get("id")) if item.get("id") is not None else None
    except Exception:item_id=None
    for r in rows:
        if item_id is not None and r.get("id")==item_id:
            target=cmd_id(r);fallback=r;break
    if not target:target=cmd_id(item)
    out=[r for r in rows if cmd_id(r)==target]
    if not out and fallback:out=[fallback]
    return out
def related_notes(dbp,item):
    rows=related_command_rows(dbp,item);ids=[];names=[];seen=set()
    for r in rows:
        if r.get("note_id") is not None:ids.append(int(r.get("note_id")))
        elif _norm(r.get("note_name","")):names.append(_norm(r.get("note_name","")))
    notes=[]
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con);cur=con.cursor();cols=set(_table_cols(cur,"Notes"))
            if {"id","note_name"}.issubset(cols):
                sel="id,note_name"+(",group_name" if "group_name" in cols else "")
                if ids:
                    q=",".join("?" for _ in sorted(set(ids)));cur.execute(f"SELECT {sel} FROM Notes WHERE id IN ({q})",sorted(set(ids)))
                    for r in cur.fetchall():
                        grp=_norm(r[2]) if "group_name" in cols and len(r)>2 else "";notes.append({"note_id":int(r[0]),"note_name":_norm(r[1]),"group_name":grp})
                if names:
                    q=",".join("?" for _ in sorted(set(names)));cur.execute(f"SELECT {sel} FROM Notes WHERE note_name IN ({q})",sorted(set(names)))
                    for r in cur.fetchall():
                        grp=_norm(r[2]) if "group_name" in cols and len(r)>2 else "";notes.append({"note_id":int(r[0]),"note_name":_norm(r[1]),"group_name":grp})
    except Exception:pass
    for r in rows:
        if r.get("note_id") is not None:key=("id",int(r.get("note_id")))
        else:key=("name",_norm(r.get("note_name","")).lower())
        if key in seen:continue
        seen.add(key)
        if any((n.get("note_id") is not None and n.get("note_id")==r.get("note_id")) or (_norm(n.get("note_name","")).lower()==_norm(r.get("note_name","")).lower()) for n in notes):continue
        if r.get("note_id") is not None or _norm(r.get("note_name","")):notes.append({"note_id":r.get("note_id"),"note_name":_norm(r.get("note_name","")),"group_name":_norm(r.get("group_name",""))})
    uniq=[];seen=set()
    for n in notes:
        key=n.get("note_id") if n.get("note_id") is not None else _norm(n.get("note_name","")).lower()
        if key in ("",None) or key in seen:continue
        seen.add(key);uniq.append(n)
    return uniq
class RelatedNotesDialog(QDialog):
    def __init__(self,parent,notes):
        super().__init__(parent);self.setObjectName("RelatedNotesDialog");self.setWindowTitle("Related Notes");self._notes=list(notes or [])
        self.resize(460,420)
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        root=QVBoxLayout(self);root.setContentsMargins(14,14,14,14);root.setSpacing(10)
        frame=QFrame(self);frame.setObjectName("TargetDialogFrame");v=QVBoxLayout(frame);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        title=QLabel(f"This command is used in {len(self._notes)} notes",frame);title.setObjectName("TargetFormTitle")
        hint=QLabel("Select one note to open.",frame);hint.setObjectName("SnippetMeta")
        self.list=QListWidget(frame);self.list.setObjectName("CmdElementList");self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for n in self._notes:
            name=_norm(n.get("note_name","")) or "Untitled";grp=_norm(n.get("group_name",""));txt=name+(f"  |  {grp}" if grp else "")
            it=QListWidgetItem(txt);it.setData(Qt.ItemDataRole.UserRole,n);self.list.addItem(it)
        if self.list.count():self.list.setCurrentRow(0);self.list.item(0).setSelected(True)
        self.list.itemDoubleClicked.connect(lambda it:(self.list.clearSelection(),it.setSelected(True),self.accept()))
        b=QHBoxLayout();b.setContentsMargins(0,0,0,0);b.setSpacing(8)
        ok=QToolButton(frame);ok.setObjectName("CmdSaveBtn");ok.setCursor(Qt.CursorShape.PointingHandCursor);ok.setText("Open")
        ca=QToolButton(frame);ca.setObjectName("CmdCancelBtn");ca.setCursor(Qt.CursorShape.PointingHandCursor);ca.setText("Cancel")
        ok.clicked.connect(self.accept);ca.clicked.connect(self.reject)
        b.addStretch(1);b.addWidget(ok,0);b.addWidget(ca,0)
        v.addWidget(title,0);v.addWidget(hint,0);v.addWidget(self.list,1);v.addLayout(b);root.addWidget(frame,1)
    def selected_notes(self):
        it=self.list.currentItem() or (self.list.selectedItems()[0] if self.list.selectedItems() else None)
        d=it.data(Qt.ItemDataRole.UserRole) if it else None
        return [d] if isinstance(d,dict) else []
def choose_related_notes(parent,notes):
    rows=list(notes or [])
    if len(rows)<=1:return rows
    dlg=RelatedNotesDialog(parent,rows)
    return dlg.selected_notes() if dlg.exec()==QDialog.DialogCode.Accepted else None
def open_note_rows(page,notes):
    ok=False
    for n in notes or []:
        try:
            if hasattr(page,"open_note_ref") and page.open_note_ref(note_id=n.get("note_id"),note_name=n.get("note_name","")):ok=True;continue
        except Exception:pass
        try:
            if n.get("note_id") is not None and hasattr(page,"open_note_by_id") and page.open_note_by_id(n.get("note_id")):ok=True;continue
        except Exception:pass
        try:
            if n.get("note_name") and hasattr(page,"open_note_by_name") and page.open_note_by_name(n.get("note_name","")):ok=True
        except Exception:pass
    return ok
def open_related_notes(parent,item,dbp,page_getter):
    rows=choose_related_notes(parent,related_notes(dbp,item))
    if rows is None:return None
    if not rows:return False
    page=page_getter() if callable(page_getter) else None
    if not page:return False
    return open_note_rows(page,rows)
