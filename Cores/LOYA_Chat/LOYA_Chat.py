import os,json,logging,importlib.util,hashlib,re,sqlite3,textwrap
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QTimer,pyqtSignal
from PyQt6.QtGui import QTextCursor,QColor,QTextCharFormat,QSyntaxHighlighter,QFontMetricsF,QGuiApplication
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QFrame,QPlainTextEdit,QLabel,QHBoxLayout,QToolButton
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _root_abs(*p):return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..",*p))
def _log_setup():
    d=_root_abs("Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("LOYA_Chat");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"LOYA_Chat_log.log"))
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
def _questions_path():return _abs("qustions.json")
def _read_questions(path):
    d=None
    try:
        if os.path.isfile(path):
            with open(path,"r",encoding="utf-8") as f:d=json.load(f)
    except Exception as e:
        _log("[-]",f"Questions load error ({e})")
    if not isinstance(d,dict):d={"version":1,"queries":[]}
    if not isinstance(d.get("queries"),list):d["queries"]=[]
    return d
def _load_commands(data):
    out=[]
    try:
        for it in data.get("queries",[]):
            if not isinstance(it,dict):continue
            k=str(it.get("key","") or "").strip()
            if k:out.append(k)
    except Exception:pass
    low={c.lower() for c in out}
    if "clear" not in low:out.append("clear")
    if "search" not in low:out.append("search")
    for k in ("history","open","use","add","select","back","exit","reset"):
        if k not in low:out.append(k)
    return out
_LOGICS_MOD=None
def _load_logic():
    global _LOGICS_MOD
    if _LOGICS_MOD is not None:return _LOGICS_MOD
    p=_abs("questions_logics.py")
    if not os.path.isfile(p):return None
    try:
        spec=importlib.util.spec_from_file_location("loya_questions_logics",p)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        _LOGICS_MOD=mod;return mod
    except Exception as e:
        _log("[!]",f"Logic load error: {p} ({e})");return None
def _logic_reply(query,questions,context=None):
    mod=_load_logic()
    if not mod:return None
    fn=getattr(mod,"handle_query",None)
    if not callable(fn):return None
    try:return fn(query,questions,context)
    except Exception as e:
        _log("[!]",f"Logic error ({e})");return None
def _norm(s):return (str(s) if s is not None else "").strip()
def _kci(s):return _norm(s).lower()
def _now():return datetime.now(timezone.utc).isoformat()
def _targets_path():
    d=_root_abs("Data")
    p1=os.path.join(d,"Targets.json")
    p2=os.path.join(d,"Targes.json")
    if os.path.isfile(p1) or not os.path.isfile(p2):return p1
    return p2
def _target_values_path():
    return _root_abs("Data","target_values.json")
def _history_path():
    return _root_abs("Data","LOYA_Chat_history.json")
def _saved_searches_path():
    return _root_abs("Data","LOYA_Chat_saved_searches.json")
def _db_path():
    return _root_abs("Data","Note_LOYA_V1.db")
def _read_json(p,default):
    try:
        if not os.path.isfile(p):return default
        with open(p,"r",encoding="utf-8") as f:return json.load(f)
    except Exception:
        return default
def _write_json(p,obj):
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        t=p+".tmp"
        with open(t,"w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(t,p);return True
    except Exception:
        try:
            if os.path.isfile(t):os.remove(t)
        except Exception:pass
        return False
def _sid(s):
    return hashlib.sha256(_kci(s).encode("utf-8")).hexdigest()[:16]
def _clamp_u16(n):
    try:n=int(n)
    except Exception:return None
    if n<0:n=0
    if n>65535:n=65535
    return n
def _db_table_cols(con,table):
    try:
        cur=con.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []
def _db_has_table(con,table):
    try:
        cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
        return bool(cur.fetchone())
    except Exception:
        return False
class _PromptHighlighter(QSyntaxHighlighter):
    def __init__(self,doc):
        super().__init__(doc)
        self._prompt_fmt=QTextCharFormat()
        self._prompt_fmt.setForeground(QColor("#0069ff"))
        self._prompt_fmt.setFontWeight(800)
        self._prompt_fmt.setFontFamily("Consolas")
        self._cmd_fmt=QTextCharFormat()
        self._cmd_fmt.setForeground(QColor("#6bb6ff"))
        self._cmd_fmt.setFontWeight(700)
        self._cmd_fmt.setFontFamily("Consolas")
        self._cmd_words=set()
    def set_command_words(self,words):
        self._cmd_words={str(w).strip().lower() for w in (words or []) if str(w).strip()}
    def highlightBlock(self,text):
        if text.startswith("LOYA "):
            end=text.find(">")
            if end!=-1:
                self.setFormat(0,end+1,self._prompt_fmt)
                i=end+1
                while i<len(text) and text[i].isspace():
                    i+=1
                j=i
                while j<len(text) and not text[j].isspace():
                    j+=1
                if j>i and text[i:j].strip().lower() in self._cmd_words:
                    self.setFormat(i,j-i,self._cmd_fmt)
        tab=text.find("\t")
        if tab>0:
            self.setFormat(0,tab,self._cmd_fmt)
class _TerminalEdit(QPlainTextEdit):
    command_submitted=pyqtSignal(str)
    tab_complete=pyqtSignal(str)
    history_prev=pyqtSignal()
    history_next=pyqtSignal()
    def __init__(self,parent=None,prompt="LOYA > "):
        super().__init__(parent)
        self._prompt=prompt
        self._input_pos=0
        self._font_size=self._init_font_size()
        self._output_fmt=QTextCharFormat()
        self._output_fmt.setForeground(QColor("#dcdcdc"))
        self._system_fmt=QTextCharFormat()
        self._system_fmt.setForeground(QColor("#8a8a8a"))
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._highlighter=_PromptHighlighter(self.document())
        self.reset()
    def set_command_words(self,words):
        try:self._highlighter.set_command_words(words)
        except Exception:pass
    def _init_font_size(self):
        f=self.font()
        try:sz=float(f.pointSizeF())
        except Exception:sz=0
        if sz<=0:sz=13.0
        f.setPointSizeF(sz)
        self.setFont(f)
        self._update_tab_stops()
        return sz
    def _update_tab_stops(self):
        try:
            fm=QFontMetricsF(self.font())
            self.setTabStopDistance(fm.horizontalAdvance("M")*20)
        except Exception:
            pass
    def set_prompt(self,prompt):
        self._prompt=prompt or "LOYA > "
    def current_input(self):
        return self._current_input()
    def _zoom(self,delta):
        sz=max(9.0,min(28.0,float(self._font_size)+float(delta)))
        if sz==self._font_size:return
        self._font_size=sz
        f=self.font()
        f.setPointSizeF(sz)
        self.setFont(f)
        self._update_tab_stops()
    def reset(self):
        self.setPlainText(self._prompt)
        self._input_pos=len(self.toPlainText())
        self._move_cursor_end()
        self._apply_char_format(self._output_fmt)
    def _move_cursor_end(self):
        cursor=self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
    def _current_input(self):
        text=self.toPlainText()
        if self._input_pos>len(text):return ""
        return text[self._input_pos:]
    def set_input_text(self,text,cursor_pos=None):
        cursor=self.textCursor()
        cursor.setPosition(self._input_pos)
        cursor.movePosition(QTextCursor.MoveOperation.End,QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        if cursor_pos is None:
            self.setTextCursor(cursor)
        else:
            try:
                pos=self._input_pos+max(0,int(cursor_pos))
            except Exception:
                pos=self._input_pos+len(text)
            cursor.setPosition(min(pos,len(self.toPlainText())))
            self.setTextCursor(cursor)
    def _insert_text_at_end(self,text,fmt=None):
        cursor=self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if fmt:cursor.insertText(text,fmt)
        else:cursor.insertText(text)
        self.setTextCursor(cursor)
    def _apply_char_format(self,fmt):
        try:
            self.setCurrentCharFormat(fmt)
            cursor=self.textCursor()
            cursor.setCharFormat(fmt)
            self.setTextCursor(cursor)
        except Exception:
            pass
    def _write_text(self,text,fmt):
        if text is None:return
        if text!="":
            if not self.toPlainText().endswith("\n"):
                self._insert_text_at_end("\n",fmt)
            self._insert_text_at_end(str(text),fmt)
        self.show_prompt()
    def write_output(self,text):
        self._write_text(text,self._output_fmt)
    def write_system(self,text):
        self._write_text(text,self._system_fmt)
    def show_prompt(self):
        if not self.toPlainText().endswith("\n"):
            self._insert_text_at_end("\n")
        self._insert_text_at_end(self._prompt)
        self._input_pos=len(self.toPlainText())
        self._move_cursor_end()
        self._scroll_to_bottom()
        self._apply_char_format(self._output_fmt)
    def _scroll_to_bottom(self):
        try:
            bar=self.verticalScrollBar()
            bar.setValue(bar.maximum())
        except Exception:pass
    def mousePressEvent(self,e):
        super().mousePressEvent(e)
    def keyPressEvent(self,e):
        key=e.key()
        mods=e.modifiers()
        if mods==(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):
            if key in (Qt.Key.Key_Plus,Qt.Key.Key_Equal):
                self._zoom(1.0);e.accept();return
            if key==Qt.Key.Key_Minus:
                self._zoom(-1.0);e.accept();return
        if key==Qt.Key.Key_Up and mods==Qt.KeyboardModifier.NoModifier:
            self.history_prev.emit();e.accept();return
        if key==Qt.Key.Key_Down and mods==Qt.KeyboardModifier.NoModifier:
            self.history_next.emit();e.accept();return
        if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
            cmd=self._current_input()
            self.command_submitted.emit(cmd)
            e.accept();return
        if key==Qt.Key.Key_Tab:
            self.tab_complete.emit(self._current_input())
            e.accept();return
        if key==Qt.Key.Key_V and (mods==(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)):
            cursor=self.textCursor()
            if cursor.position()<self._input_pos:
                cursor.setPosition(self._input_pos);self.setTextCursor(cursor)
            self.paste();e.accept();return
        cursor=self.textCursor()
        if key==Qt.Key.Key_Backspace:
            if cursor.hasSelection():
                if cursor.selectionStart()<self._input_pos:e.accept();return
            else:
                if cursor.position()<=self._input_pos:e.accept();return
            super().keyPressEvent(e);return
        if key==Qt.Key.Key_Delete:
            if cursor.hasSelection():
                if cursor.selectionStart()<self._input_pos:e.accept();return
            else:
                if cursor.position()<self._input_pos:e.accept();return
            super().keyPressEvent(e);return
        if key in (Qt.Key.Key_Left,Qt.Key.Key_Home):
            if cursor.position()<=self._input_pos:e.accept();return
        if cursor.position()<self._input_pos and e.text():
            cursor.setPosition(self._input_pos);self.setTextCursor(cursor)
        super().keyPressEvent(e)
        cursor=self.textCursor()
        if not cursor.hasSelection() and cursor.position()<self._input_pos:
            cursor.setPosition(self._input_pos);self.setTextCursor(cursor)
class Widget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("LOYAPage")
        self._questions=_read_questions(_questions_path())
        self._commands=_load_commands(self._questions)
        cmd_words={_kci(c).split()[0] for c in self._commands if _norm(c)}
        self._history=self._load_history()
        self._history_idx=None
        self._history_temp=""
        self._selected_target=None
        self._base_prompt="LOYA > "
        self._page_step=10
        self._default_limits={"notes":10,"commands":10,"targets":10,"targets_value":10}
        self._last_search=None
        self._saved_searches=self._load_saved_searches()
        self._suggest_cache={"targets":[],"categories":[],"tags":[]}
        self._suggest_cache_mtime={"targets":None,"db":None}
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        frame=QFrame(self);root.addWidget(frame,1)
        v=QVBoxLayout(frame);v.setContentsMargins(12,12,12,12);v.setSpacing(0)
        self.term_frame=QFrame(frame);self.term_frame.setObjectName("LOYATerminalFrame")
        tf=QVBoxLayout(self.term_frame);tf.setContentsMargins(6,6,6,6);tf.setSpacing(0)
        self.terminal=_TerminalEdit(self.term_frame);self.terminal.setObjectName("LOYATerminal")
        self.terminal.set_prompt(self._base_prompt)
        self.terminal.set_command_words(cmd_words)
        tf.addWidget(self.terminal,1)
        self.status=QLabel(self.term_frame);self.status.setObjectName("LOYATargetStatus")
        self.status.setText("Target: none");self.status.setWordWrap(True)
        tf.addWidget(self.status,0)
        self.suggest=QLabel(self.terminal.viewport());self.suggest.setObjectName("LOYAInlineSuggest")
        self.suggest.setWordWrap(False)
        self.suggest.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.suggest.hide()
        self._bottom_row=QFrame(self.term_frame)
        hb=QHBoxLayout(self._bottom_row);hb.setContentsMargins(0,0,0,0);hb.setSpacing(8)
        self.show_more_btn=QToolButton(self._bottom_row);self.show_more_btn.setObjectName("LOYAShowMoreBtn")
        self.show_more_btn.setText("more");self.show_more_btn.setToolTip("Show more results")
        self.show_more_btn.setAutoRaise(True);self.show_more_btn.hide()
        hb.addStretch(1)
        hb.addWidget(self.show_more_btn,0,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        tf.addWidget(self._bottom_row,0)
        v.addWidget(self.term_frame,1)
        self.terminal.command_submitted.connect(self._on_submit)
        self.terminal.tab_complete.connect(self._on_tab_complete)
        self.terminal.history_prev.connect(self._on_history_prev)
        self.terminal.history_next.connect(self._on_history_next)
        self.terminal.textChanged.connect(self._on_text_changed)
        self.terminal.cursorPositionChanged.connect(self._hide_suggest)
        self.terminal.verticalScrollBar().valueChanged.connect(self._hide_suggest)
        self.show_more_btn.clicked.connect(self._on_show_more)
        QTimer.singleShot(0,self._focus_terminal)
        _log("[+]", "LOYA terminal ready")
        self._update_status()
    def _focus_terminal(self):
        try:self.terminal.setFocus()
        except:pass
    def _on_tab_complete(self,text):
        raw=str(text or "")
        clean=raw.strip()
        if not clean:return
        if " " not in raw:
            matches=[c for c in self._commands if c.lower().startswith(clean.lower())]
            if len(matches)==1:
                self.terminal.set_input_text(matches[0]);self._hide_suggest();return
            if len(matches)>1:
                self._show_suggest("suggest",matches,raw);return
            self._hide_suggest();return
            return
        if self._tab_complete_help(raw):return
        if self._tab_complete_open(raw):return
        if self._tab_complete_search_scope(raw):return
        if self._tab_complete_target(raw):return
        if self._tab_complete_filter_key(raw):return
        if self._tab_complete_filter_value(raw):return
        self._hide_suggest()
    def _tab_complete_help(self,raw):
        m=re.match(r"^\s*help\s*(.*)$",raw,re.I)
        if not m:return False
        prefix=_norm(m.group(1))
        matches=[c for c in self._commands if _kci(c).startswith(_kci(prefix))]
        if len(matches)==1:
            self.terminal.set_input_text("help "+matches[0])
            self._hide_suggest()
            return True
        if len(matches)>1:
            self._show_suggest("commands",matches,raw)
            return True
        self._hide_suggest()
        return True
    def _tab_complete_open(self,raw):
        m=re.match(r"^\s*open\s+(.+)$",raw,re.I)
        if not m:return False
        prefix=_norm(m.group(1))
        opts=["notes","commands","targets","settings"]
        matches=[o for o in opts if _kci(o).startswith(_kci(prefix))]
        if len(matches)==1:
            self.terminal.set_input_text("open "+matches[0])
            self._hide_suggest()
            return True
        if len(matches)>1:
            self._show_suggest("options",matches,raw)
            return True
        self._hide_suggest()
        return True
    def _tab_complete_search_scope(self,raw):
        m=re.match(r"^\s*search\s+in\s+(.+)$",raw,re.I)
        if not m:return False
        rest=_norm(m.group(1))
        if " for " in " "+rest+" ":return False
        opts=["notes","commands","targets","targets value"]
        matches=[o for o in opts if _kci(o).startswith(_kci(rest))]
        if len(matches)==1:
            self.terminal.set_input_text("search in "+matches[0]+" ")
            self._hide_suggest()
            return True
        if len(matches)>1:
            self._show_suggest("scopes",matches,raw)
            return True
        self._hide_suggest()
        return True
    def _tab_complete_target(self,raw):
        m=re.match(r"^\s*(use\s+target|select\s+target|select\s+from\s+targets)\s+(.+)$",raw,re.I)
        if not m:return False
        name_part=m.group(2)
        block=""
        if "{" in name_part and "}" in name_part:
            name_part,block=self._split_block(name_part)
        prefix=_norm(name_part)
        if prefix.startswith("\"") or prefix.startswith("'"):prefix=prefix[1:]
        prefix=self._strip_quotes(prefix)
        items=self._match_prefix(self._get_target_names(),prefix)
        if len(items)==1:
            new_name=self._quote_value(items[0],name_part)
            tail=f" {{ {block} }}" if block else ""
            new_text=f"{m.group(1)} {new_name}{tail}"
            self.terminal.set_input_text(new_text)
            self._hide_suggest()
            return True
        if len(items)>1:
            self._show_suggest("targets",items,raw)
            return True
        self._hide_suggest()
        return True
    def _tab_complete_filter_value(self,raw):
        if not re.match(r"^\s*search\b",raw,re.I):return False
        info=self._extract_filter_prefix(raw,("target_name","category","tags"))
        if not info:return False
        key=info["key"]
        prefix=info["prefix"]
        if key=="target_name":items=self._match_prefix(self._get_target_names(),prefix)
        elif key=="category":items=self._match_prefix(self._get_categories(),prefix)
        elif key=="tags":items=self._match_prefix(self._get_tags(),prefix)
        else:items=[]
        if len(items)==1:
            new_val=self._quote_value(items[0],info["raw"])
            new_text=raw[:info["start"]]+new_val
            self.terminal.set_input_text(new_text)
            self._hide_suggest()
            return True
        if len(items)>1:
            label="targets" if key=="target_name" else ("categories" if key=="category" else "tags")
            self._show_suggest(label,items,raw)
            return True
        self._hide_suggest()
        return True
    def _tab_complete_filter_key(self,raw):
        m=re.match(r"^\s*search\s+in\s+(.+?)\s+for\s+(.*)$",raw,re.I)
        if not m:return False
        scope_raw=" ".join(_kci(m.group(1)).split())
        scope="targets_value" if scope_raw in ("targets value","target values","target value","targets values","values") else scope_raw
        keys=self._filter_keys_for_scope(scope)
        if not keys:return False
        tail=m.group(2)
        tail_rstrip=tail.rstrip()
        if tail_rstrip=="":
            self._show_suggest("filters",[self._filter_key_template(k)[0] for k in keys],raw)
            return True
        last=tail_rstrip.split()[-1]
        if last.lower() in ("and","or","not"):
            self._show_suggest("filters",[self._filter_key_template(k)[0] for k in keys],raw)
            return True
        if "=" in last:return False
        last_idx=tail_rstrip.rfind(last)
        start=m.start(2)+last_idx
        end=start+len(last)
        prefix=_norm(last)
        matches=[k for k in keys if _kci(k).startswith(_kci(prefix))]
        if len(matches)==1:
            key=matches[0]
            new_token,cursor_pos_rel=self._filter_key_template(key)
            new_text=raw[:start]+new_token+raw[end:]
            cursor_pos=start+cursor_pos_rel
            self.terminal.set_input_text(new_text,cursor_pos)
            self._hide_suggest()
            return True
        if len(matches)>1:
            self._show_suggest("filters",[self._filter_key_template(k)[0] for k in matches],raw)
            return True
        self._hide_suggest()
        return True
    def _on_submit(self,text):
        raw=str(text or "")
        clean=raw.strip()
        self._history_idx=None
        self._history_temp=""
        if not clean:
            self.terminal.show_prompt()
            return
        self._clear_more_state()
        self._push_history(clean)
        base,pipes=self._split_pipes(clean)
        if pipes:
            if not base:
                self.terminal.write_system("Missing command before pipe.")
                return
            if not re.match(r"^search\\b",base,re.I):
                self.terminal.write_system("Pipe only supports search right now.")
                return
            reply_text,reply_kind=self._get_reply(base)
            if reply_text:
                if reply_kind=="system":self.terminal.write_system(reply_text)
                else:self.terminal.write_output(reply_text)
                for msg in self._apply_pipes(pipes,reply_text):
                    if msg:self.terminal.write_system(msg)
            return
        handled,out=self._handle_command(clean)
        if handled:
            if out is not None:
                self.terminal.write_system(out)
            return
        reply,kind=self._get_reply(clean)
        if kind=="system":self.terminal.write_system(reply)
        else:self.terminal.write_output(reply)
    def _push_history(self,cmd):
        c=_norm(cmd)
        if c:
            self._history.append(c)
            self._save_history()
    def _history_lines(self,limit=20):
        total=len(self._history)
        items=self._history[-limit:] if total>limit else list(self._history)
        lines=[f"History: {total}"]
        start=max(1,total-len(items)+1)
        for i,cmd in enumerate(items,start):
            lines.append(f"{i}. {cmd}")
        if total>limit:lines.append(f"... {total-limit} more")
        return "\n".join(lines)
    def _load_history(self):
        data=_read_json(_history_path(),[])
        if not isinstance(data,list):return []
        out=[]
        for it in data:
            s=_norm(it)
            if s:out.append(s)
        return out
    def _save_history(self):
        keep=500
        _write_json(_history_path(),self._history[-keep:])
    def _load_saved_searches(self):
        data=_read_json(_saved_searches_path(),{})
        if not isinstance(data,dict):return {}
        out={}
        for k,v in data.items():
            kk=_norm(k)
            vv=_norm(v)
            if kk and vv:out[kk]=vv
        return out
    def _save_saved_searches(self):
        return _write_json(_saved_searches_path(),self._saved_searches or {})
    def _help_text(self):
        items=self._questions.get("queries") if isinstance(self._questions,dict) else []
        lines=["Commands:"]
        if isinstance(items,list):
            for it in items:
                if not isinstance(it,dict):continue
                key=_norm(it.get("key",""))
                desc=_norm(it.get("description",""))
                if not key:continue
                lines+=self._format_help_row(key,desc)
        if len(lines)>1:
            lines.append("")
            lines.append("Use: help <command>")
        return "\n".join(lines) if len(lines)>1 else "No commands available."
    def _help_command(self,name):
        key=_kci(name)
        items=self._questions.get("queries") if isinstance(self._questions,dict) else []
        if not isinstance(items,list):items=[]
        exact=[it for it in items if _kci(it.get("key",""))==key]
        if exact:
            it=exact[0]
        else:
            starts=[it for it in items if _kci(it.get("key","")).startswith(key)]
            if len(starts)==1:it=starts[0]
            elif starts:
                opts=", ".join([_norm(x.get("key","")) for x in starts if _norm(x.get("key",""))])
                return f"Matches: {opts}"
            else:
                return "Command not found."
        desc=_norm(it.get("description",""))
        lines=[]
        lines+=self._format_help_row(_norm(it.get("key","")),desc)
        examples=it.get("examples")
        if isinstance(examples,list) and examples:
            lines.append("")
            lines.append("\texamples:")
            for ex in examples:
                exn=_norm(ex)
                if exn:lines.append(f"\t- {exn}")
        return "\n".join(lines)
    def _help_wrap_width(self):
        try:
            fm=QFontMetricsF(self.terminal.font())
            cols=int(self.terminal.viewport().width()/max(1.0,fm.horizontalAdvance("M")))
            return max(50,cols-2)
        except Exception:
            return 90
    def _format_help_row(self,key,desc):
        k=_norm(key)
        d=_norm(desc)
        if not d:return [k] if k else []
        max_cols=self._help_wrap_width()
        indent=20
        wrap=max(20,max_cols-indent-4)
        if wrap>70:wrap=70
        parts=textwrap.wrap(d,width=wrap) or [d]
        lines=[f"{k}\t{parts[0]}"]
        for p in parts[1:]:
            lines.append(f"\t{p}")
        return lines
    def _default_limit_for_scope(self,scope):
        return self._default_limits.get(scope,self._page_step) if hasattr(self,"_default_limits") else self._page_step
    def _match_prefix(self,items,prefix):
        pre=_kci(prefix)
        if not items:return []
        if not pre:return list(items)
        return [it for it in items if _kci(it).startswith(pre)]
    def _quote_value(self,value,raw_value):
        v=_norm(value)
        raw=_norm(raw_value)
        if not v:return v
        if raw.startswith("\"") or raw.startswith("'"):
            q=raw[0]
            return q+v+q
        if " " in v:return "\""+v+"\""
        return v
    def _extract_filter_prefix(self,raw,keys):
        if not raw or not keys:return None
        keys_pat="|".join([re.escape(k) for k in keys])
        pat=r"(?:\b("+keys_pat+r")\b)\s*=\s*(\"[^\"]*\"|\"[^\"]*|\'[^\']*\'|\'[^\']*|[^\s\"]*)$"
        m=re.search(pat,raw,re.I)
        if not m:return None
        key=_kci(m.group(1))
        raw_val=_norm(m.group(2))
        val=raw_val
        if raw_val.startswith("\"") or raw_val.startswith("'"):
            q=raw_val[0]
            val=raw_val[1:]
            if val.endswith(q):val=val[:-1]
        return {"key":key,"prefix":val,"raw":raw_val,"start":m.start(2)}
    def _load_target_names_cache(self):
        p=_targets_path()
        mtime=os.path.getmtime(p) if os.path.isfile(p) else None
        if self._suggest_cache_mtime.get("targets")==mtime:return
        self._suggest_cache_mtime["targets"]=mtime
        data=_read_json(p,[])
        names={}
        if isinstance(data,list):
            for it in data:
                if not isinstance(it,dict):continue
                n=_norm(it.get("name",""))
                k=_kci(n)
                if n and k not in names:names[k]=n
        self._suggest_cache["targets"]=sorted(names.values())
    def _load_db_cache(self):
        p=_db_path()
        mtime=os.path.getmtime(p) if os.path.isfile(p) else None
        if self._suggest_cache_mtime.get("db")==mtime:return
        self._suggest_cache_mtime["db"]=mtime
        cats={}
        tags={}
        if not os.path.isfile(p):
            self._suggest_cache["categories"]=[]
            self._suggest_cache["tags"]=[]
            return
        try:
            con=sqlite3.connect(p,timeout=3)
        except Exception:
            self._suggest_cache["categories"]=[]
            self._suggest_cache["tags"]=[]
            return
        try:
            for table in ("Commands","CommandsNotes"):
                if not _db_has_table(con,table):continue
                cols=set(_db_table_cols(con,table))
                if "category" in cols:
                    cur=con.cursor();cur.execute(f"SELECT DISTINCT category FROM {table}")
                    for (c,) in cur.fetchall():
                        c=_norm(c);k=_kci(c)
                        if c and k not in cats:cats[k]=c
                if "tags" in cols:
                    cur=con.cursor();cur.execute(f"SELECT DISTINCT tags FROM {table}")
                    for (t,) in cur.fetchall():
                        for part in re.split(r"[;,]+",_norm(t)):
                            p=_norm(part);k=_kci(p)
                            if p and k not in tags:tags[k]=p
        finally:
            try:con.close()
            except Exception:pass
        self._suggest_cache["categories"]=sorted(cats.values())
        self._suggest_cache["tags"]=sorted(tags.values())
    def _get_target_names(self):
        self._load_target_names_cache()
        return self._suggest_cache.get("targets",[])
    def _get_categories(self):
        self._load_db_cache()
        return self._suggest_cache.get("categories",[])
    def _get_tags(self):
        self._load_db_cache()
        return self._suggest_cache.get("tags",[])
    def _suggest_value_matches(self,raw):
        m=re.match(r"^\s*(use\s+target|select\s+target|select\s+from\s+targets)\s+(.+)$",raw,re.I)
        if m:
            name_part=m.group(2)
            if "{" in name_part:
                name_part=name_part.split("{",1)[0].strip()
            prefix=_norm(name_part)
            if prefix.startswith("\"") or prefix.startswith("'"):prefix=prefix[1:]
            prefix=self._strip_quotes(prefix)
            return self._format_suggest("targets",self._match_prefix(self._get_target_names(),prefix))
        if not re.match(r"^\s*search\b",raw,re.I):return ""
        info=self._extract_filter_prefix(raw,("target_name","category","tags"))
        if not info:return ""
        key=info["key"];prefix=info["prefix"]
        if key=="target_name":
            return self._format_suggest("targets",self._match_prefix(self._get_target_names(),prefix))
        if key=="category":
            return self._format_suggest("categories",self._match_prefix(self._get_categories(),prefix))
        if key=="tags":
            return self._format_suggest("tags",self._match_prefix(self._get_tags(),prefix))
        return ""
    def _format_suggest(self,label,items,limit=6):
        items=[_norm(x) for x in (items or []) if _norm(x)]
        if not items:return ""
        shown=items[:limit]
        tail=" | ..." if len(items)>limit else ""
        lab=_norm(label)
        if lab=="suggest":lab="suggestions"
        if lab:
            return f"{lab}: " + " | ".join(shown) + tail
        return " | ".join(shown) + tail
    def _position_inline_suggest(self,text=None):
        try:
            rect=self.terminal.cursorRect()
            viewport=self.terminal.viewport()
            max_w=max(120,viewport.width()-rect.left()-6)
            self.suggest.setMaximumWidth(max_w)
            if text is not None:
                fm=QFontMetricsF(self.suggest.font())
                el=fm.elidedText(text,Qt.TextElideMode.ElideRight,max_w)
                self.suggest.setText(el)
            self.suggest.adjustSize()
            x=rect.left()
            y=rect.bottom()+2
            if y+self.suggest.height()>viewport.height():
                y=rect.top()-self.suggest.height()-2
                if y<0:y=0
            self.suggest.move(x,max(0,y))
        except Exception:
            pass
    def _show_suggest(self,label,items,raw=None,limit=6):
        msg=self._format_suggest(label,items,limit)
        if not msg:
            self._hide_suggest();return
        self.suggest.show()
        self._position_inline_suggest(msg)
    def _hide_suggest(self):
        self.suggest.hide()
    def _auto_suggest_filters(self,raw):
        m=re.match(r"^\s*search\s+in\s+(.+?)\s+for\s*(.*)$",raw,re.I)
        if not m:return False
        scope_raw=" ".join(_kci(m.group(1)).split())
        scope="targets_value" if scope_raw in ("targets value","target values","target value","targets values","values") else scope_raw
        keys=self._filter_keys_for_scope(scope)
        common=self._common_filter_keys_for_scope(scope)
        if not keys:return False
        tail=_norm(m.group(2))
        if not tail:
            base=common if common else keys
            self._show_suggest("filters",[self._filter_key_template(k)[0] for k in base],limit=3)
            return True
        last=tail.split()[-1]
        if last.lower() in ("and","or","not"):
            base=common if common else keys
            self._show_suggest("filters",[self._filter_key_template(k)[0] for k in base],limit=3)
            return True
        if "=" in last:
            self._hide_suggest()
            return True
        matches=[k for k in keys if _kci(k).startswith(_kci(last))]
        if matches:
            self._show_suggest("filters",[self._filter_key_template(k)[0] for k in matches],limit=3)
            return True
        self._hide_suggest()
        return True
    def _on_text_changed(self):
        raw=self.terminal.current_input()
        if self._auto_suggest_filters(raw):return
        self._hide_suggest()
    def _split_pipes(self,text):
        if "|" not in text:return text,[]
        parts=[]
        buf=[]
        quote=None
        for ch in text:
            if ch in ("\"","'"):
                if quote is None:quote=ch
                elif quote==ch:quote=None
                buf.append(ch);continue
            if ch=="|" and quote is None:
                parts.append("".join(buf).strip());buf=[]
                continue
            buf.append(ch)
        parts.append("".join(buf).strip())
        base=parts[0] if parts else text
        pipes=[p for p in parts[1:] if p]
        return base,pipes
    def _parse_export_path(self,pipe):
        rest=_norm(pipe)
        if not rest:return ""
        parts=rest.split(None,1)
        if len(parts)==1:return ""
        arg=_norm(parts[1])
        if arg.lower().startswith("path="):
            arg=_norm(arg[5:])
        return self._strip_quotes(arg)
    def _parse_open_id(self,pipe):
        rest=_norm(pipe)
        if not rest:return ""
        parts=rest.split(None,1)
        if len(parts)==1:return ""
        arg=_norm(parts[1])
        if arg.lower().startswith("id="):
            arg=_norm(arg[3:])
        return self._strip_quotes(arg)
    def _default_export_path(self,base="search"):
        d=_root_abs("Data","LOYA_Chat_exports")
        os.makedirs(d,exist_ok=True)
        ts=datetime.now().strftime("%Y%m%d_%H%M%S")
        name=f"{_norm(base) or 'export'}_{ts}.txt"
        return os.path.join(d,name)
    def _export_text(self,text,path_hint=""):
        if not _norm(text):return False,"Nothing to export."
        path=_norm(path_hint)
        if not path:
            path=self._default_export_path("search")
        elif not os.path.isabs(path):
            path=os.path.join(_root_abs("Data","LOYA_Chat_exports"),path)
        try:
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with open(path,"w",encoding="utf-8") as f:f.write(str(text))
            return True,f"Exported to {path}"
        except Exception:
            return False,"Export failed."
    def _apply_pipes(self,pipes,text):
        msgs=[]
        for p in pipes:
            low=_kci(p)
            if low=="copy":
                if not _norm(text):
                    msgs.append("Nothing to copy.")
                    continue
                try:
                    QGuiApplication.clipboard().setText(str(text))
                    msgs.append("Copied to clipboard.")
                except Exception:
                    msgs.append("Copy failed.")
                continue
            if low.startswith("export"):
                path_hint=self._parse_export_path(p)
                ok,msg=self._export_text(text,path_hint)
                msgs.append(msg)
                continue
            if low.startswith("open"):
                cid=self._parse_open_id(p)
                ok,msg=self._pipe_open(cid)
                msgs.append(msg)
                continue
            if low.startswith("use target"):
                name=self._strip_quotes(p[len("use target"):])
                name=_norm(name)
                if not name:
                    msgs.append("Target name is required.")
                    continue
                ok,msg,_t=self._set_live_target(name)
                if ok:
                    self._selected_target=_t
                    self._update_prompt()
                msgs.append(msg)
                continue
            msgs.append(f"Unknown pipe: {p}")
        return msgs
    def _safe_int(self,val,default=0):
        try:return int(val)
        except Exception:return default
    def _clear_more_state(self):
        self._last_search=None
        try:self.show_more_btn.hide()
        except Exception:pass
    def _apply_search_state(self,query,reply):
        if not isinstance(reply,dict):
            self._clear_more_state();return
        remaining=self._safe_int(reply.get("remaining",0),0)
        if remaining<=0:
            self._clear_more_state();return
        limit=max(1,self._safe_int(reply.get("limit",self._page_step),self._page_step))
        self._last_search={
            "query":query,
            "offset":self._safe_int(reply.get("offset",0),0),
            "limit":limit,
            "total":self._safe_int(reply.get("total",0),0),
            "remaining":remaining,
            "scope":_norm(reply.get("scope","")),
        }
        label="more"
        if remaining>0:label=f"more ({remaining})"
        self.show_more_btn.setText(label)
        self.show_more_btn.show()
    def _build_context(self,pagination=None):
        ctx={}
        if isinstance(self._selected_target,dict):
            ctx["target"]=self._selected_target
            ctx["target_values"]=self._selected_target.get("values",{})
        if isinstance(pagination,dict):
            ctx["pagination"]=pagination
        return ctx
    def _on_show_more(self):
        state=self._last_search
        if not isinstance(state,dict):return
        total=self._safe_int(state.get("total",0),0)
        limit=max(1,self._safe_int(state.get("limit",self._page_step),self._page_step))
        offset=self._safe_int(state.get("offset",0),0)
        next_offset=offset+limit
        if total and next_offset>=total:
            self._clear_more_state()
            return
        ctx=self._build_context({"offset":next_offset,"limit":limit})
        reply=_logic_reply(state.get("query",""),self._questions,ctx)
        if isinstance(reply,dict) and "text" in reply:
            self._apply_search_state(state.get("query",""),reply)
            kind=_kci(reply.get("kind",""))
            if kind=="system":self.terminal.write_system(reply.get("text",""))
            else:self.terminal.write_output(reply.get("text",""))
        elif reply:
            self._clear_more_state()
            self.terminal.write_output(str(reply))
        else:
            self._clear_more_state()
    def _on_history_prev(self):
        if not self._history:return
        if self._history_idx is None:
            self._history_idx=len(self._history)
            self._history_temp=self.terminal.current_input()
        if self._history_idx>0:self._history_idx-=1
        self.terminal.set_input_text(self._history[self._history_idx])
    def _on_history_next(self):
        if self._history_idx is None:return
        if self._history_idx<len(self._history)-1:
            self._history_idx+=1
            self.terminal.set_input_text(self._history[self._history_idx])
            return
        self._history_idx=None
        self.terminal.set_input_text(self._history_temp or "")
    def _strip_quotes(self,s):
        t=_norm(s)
        if len(t)>=2 and ((t[0]=="\"" and t[-1]=="\"") or (t[0]=="'" and t[-1]=="'")):
            return t[1:-1]
        return t
    def _filter_keys_for_scope(self,scope):
        base=["keyword","general","limit","date_from","date_to","has","missing"]
        if scope=="notes":
            return base+["note_name","tags","command_keyword","category","sub_category","description_keyword","command_tittle","command_title","cmd_note_title","command"]
        if scope=="commands":
            return base+["command_tittle","command_title","cmd_note_title","category","sub_category","description_keyword","tags","command_keyword","command"]
        if scope=="targets":
            return base+["target_name","target_value"]
        if scope=="targets_value":
            return base+["target_value"]
        return base
    def _common_filter_keys_for_scope(self,scope):
        if scope=="notes":
            return ["keyword","note_name","tags","category","command_keyword","limit"]
        if scope=="commands":
            return ["keyword","command","tags","category","description_keyword","limit"]
        if scope=="targets":
            return ["target_name","target_value","limit"]
        if scope=="targets_value":
            return ["target_value","limit"]
        return ["keyword","limit"]
    def _filter_key_template(self,key):
        k=_norm(key)
        if k in ("has","missing","limit","date_from","date_to"):
            return k+"=",len(k)+1
        return k+"=\"\"",len(k)+2
    def _split_block(self,raw):
        text=_norm(raw)
        if "{" in text and "}" in text:
            a=text.find("{");b=text.rfind("}")
            name=text[:a].strip()
            block=text[a+1:b].strip()
            return name,block
        return text,""
    def _parse_assignments(self,text):
        out={}
        pat=r'([A-Za-z0-9_]+)\s*=\s*(\"[^\"]*\"|\'[^\']*\'|[^\s\"]+)'
        for m in re.finditer(pat,text or ""):
            k=_norm(m.group(1))
            v=_norm(m.group(2))
            if len(v)>=2 and ((v[0]=="\"" and v[-1]=="\"") or (v[0]=="'" and v[-1]=="'")):
                v=v[1:-1]
            if k and _norm(v):out[k]=v
        return out
    def _update_prompt(self):
        name=_norm(self._selected_target.get("name","")) if isinstance(self._selected_target,dict) else ""
        prompt=f"LOYA ${name} > " if name else self._base_prompt
        self.terminal.set_prompt(prompt)
        self._update_status()
    def _update_status(self):
        name=_norm(self._selected_target.get("name","")) if isinstance(self._selected_target,dict) else ""
        status=_kci(self._selected_target.get("status","")) if isinstance(self._selected_target,dict) else ""
        if not name:
            self.status.setText("Target: none");return
        tail=" (live)" if status=="live" else ""
        self.status.setText(f"Target: {name}{tail}")
    def _nav(self,key):
        try:w=self.window()
        except Exception:return False
        if w and hasattr(w,"on_nav"):
            try:w.on_nav(key);return True
            except Exception:pass
        return False
    def _open_note_by_id(self,nid):
        try:note_id=int(str(nid).strip())
        except Exception:return False,"Invalid note id."
        self._nav("notes")
        w=self.window()
        page=getattr(w,"page_notes",None) if w else None
        if page and hasattr(page,"open_note_by_id"):
            try:
                page.open_note_by_id(note_id)
                return True,f"Opened note id={note_id}."
            except Exception:
                return False,"Open note failed."
        return False,"Notes page not available."
    def _fetch_command_item(self,cid):
        try:cid=int(str(cid).strip())
        except Exception:return None
        dbp=_db_path()
        if not os.path.isfile(dbp):return None
        try:
            con=sqlite3.connect(dbp,timeout=5)
        except Exception:
            return None
        try:
            for table in ("Commands","CommandsNotes"):
                if not _db_has_table(con,table):continue
                cols=set(_db_table_cols(con,table))
                if "id" not in cols:continue
                sel=[]
                for c in ("id","note_id","note_name","cmd_note_title","category","sub_category","tags","description","command"):
                    if c in cols:sel.append(c)
                cur=con.cursor()
                cur.execute("SELECT "+",".join(sel)+f" FROM {table} WHERE id=?",(cid,))
                r=cur.fetchone()
                if not r:continue
                data={}
                for i,c in enumerate(sel):
                    data[c]=r[i] if i<len(r) else ""
                title=_norm(data.get("cmd_note_title","")) or _norm(data.get("note_name",""))
                return {
                    "id":cid,
                    "note_id":data.get("note_id",None),
                    "note_name":data.get("note_name",""),
                    "title":title,
                    "category":data.get("category",""),
                    "sub":data.get("sub_category",""),
                    "tags":data.get("tags",""),
                    "description":data.get("description",""),
                    "command":data.get("command",""),
                    "src":table,
                    "db":dbp,
                }
        finally:
            try:con.close()
            except Exception:pass
        return None
    def _open_command_by_id(self,cid):
        item=self._fetch_command_item(cid)
        if not item:return False,"Command not found."
        self._nav("commands")
        w=self.window()
        page=getattr(w,"page_commands",None) if w else None
        if page and hasattr(page,"open_command_info"):
            try:
                page.open_command_info(item)
                return True,f"Opened command id={cid}."
            except Exception:
                return False,"Open command failed."
        return False,"Commands page not available."
    def _pipe_open(self,cid):
        if not cid:return False,"Open requires an id."
        scope=_norm(self._last_search.get("scope","")) if isinstance(self._last_search,dict) else ""
        if scope=="notes":
            return self._open_note_by_id(cid)
        if scope=="commands":
            return self._open_command_by_id(cid)
        return False,"Open not supported for this search."
    def _ell_text(self,text,limit=220):
        s=_norm(text)
        if len(s)<=limit:return s
        return s[:max(0,limit-3)]+"..."
    def _preview_note_by_id(self,nid):
        try:nid=int(str(nid).strip())
        except Exception:return False,"Invalid note id."
        dbp=_db_path()
        if not os.path.isfile(dbp):return False,"Notes database not found."
        try:
            con=sqlite3.connect(dbp,timeout=5)
        except Exception:
            return False,"Notes database not available."
        try:
            if not _db_has_table(con,"Notes"):return False,"Notes table not found."
            cols=set(_db_table_cols(con,"Notes"))
            if "id" not in cols:return False,"Notes table not found."
            sel=["note_name","content","updated_at","created_at"]
            sel=[c for c in sel if c in cols]
            if not sel:sel=["note_name","content"]
            cur=con.cursor()
            cur.execute("SELECT "+",".join(sel)+" FROM Notes WHERE id=?",(nid,))
            r=cur.fetchone()
            if not r:return False,"Note not found."
            data={sel[i]:r[i] for i in range(len(sel))}
            name=_norm(data.get("note_name","")) or "(no name)"
            content=_norm(data.get("content",""))
            content=re.sub(r"<[^>]+>"," ",content)
            content=re.sub(r"\\s+"," ",content).strip()
            snippet=self._ell_text(content,240)
            return True,f"Note {nid}: {name}\n{snippet}"
        finally:
            try:con.close()
            except Exception:pass
    def _preview_command_by_id(self,cid):
        item=self._fetch_command_item(cid)
        if not item:return False,"Command not found."
        title=_norm(item.get("title","")) or "(no title)"
        cmd=_norm(item.get("command",""))
        desc=_norm(item.get("description",""))
        lines=[f"Command {cid}: {title}"]
        if cmd:lines.append("cmd: "+self._ell_text(cmd,240))
        if desc:lines.append("desc: "+self._ell_text(desc,200))
        return True,"\n".join(lines)
    def _show_preview(self,sid):
        if not isinstance(self._last_search,dict):return False,"No search context."
        scope=_norm(self._last_search.get("scope",""))
        if scope=="notes":
            return self._preview_note_by_id(sid)
        if scope=="commands":
            return self._preview_command_by_id(sid)
        return False,"Preview not supported for this search."
    def _load_targets(self):
        data=_read_json(_targets_path(),[])
        return data if isinstance(data,list) else []
    def _load_target_values(self):
        data=_read_json(_target_values_path(),{})
        return data if isinstance(data,dict) else {}
    def _save_targets(self,targets):
        return _write_json(_targets_path(),targets)
    def _find_target(self,targets,name=None,tid=None):
        if tid:
            for i,t in enumerate(targets or []):
                if _norm(t.get("id",""))==tid:return i,t
        if name:
            key=_kci(name)
            for i,t in enumerate(targets or []):
                if _kci(t.get("name",""))==key:return i,t
        return None,None
    def _merge_values(self,base,updates):
        out={}
        if isinstance(base,dict):
            for k,v in base.items():
                if _norm(k) and _norm(v):out[str(k)]=str(v)
        for k,v in (updates or {}).items():
            kk=_norm(k);vv=_norm(v)
            if not kk or not vv:continue
            hit=None
            for ex in out.keys():
                if _kci(ex)==_kci(kk):hit=ex;break
            out[hit if hit else kk]=vv
        return out
    def _missing_target_key(self,updates):
        values=self._load_target_values()
        keys={_kci(k) for k in values.keys()}
        for k in (updates or {}).keys():
            if _kci(k) not in keys:
                return k
        return ""
    def _normalize_update_keys(self,updates):
        values=self._load_target_values()
        key_map={_kci(k):k for k in values.keys()}
        out={}
        for k,v in (updates or {}).items():
            kk=_kci(k)
            canon=key_map.get(kk,k)
            out[canon]=v
        return out
    def _set_live_target(self,name):
        nm=_norm(name)
        if not nm:return False,"Target name is required.",None
        targets=self._load_targets()
        idx,t=self._find_target(targets,name=nm)
        if t is None:return False,"Target not found.",None
        now=_now()
        for i,it in enumerate(targets):
            want="live" if i==idx else "not_used"
            if _kci(it.get("status","not_used"))!=want:
                it["status"]=want
                it["updated"]=now
        if not self._save_targets(targets):return False,"Save failed.",None
        return True,f"Using target: {nm}",targets[idx]
    def _select_target(self,name,set_live=False):
        nm=_norm(name)
        if not nm:return False,"Target name is required."
        targets=self._load_targets()
        idx,t=self._find_target(targets,name=nm)
        if t is None:return False,"Target not found."
        if set_live:
            ok,msg,sel=self._set_live_target(nm)
            if not ok:return False,msg
            self._selected_target=sel
            self._update_prompt()
            return True,msg
        self._selected_target=t
        self._update_prompt()
        return True,f"Selected target: {nm}"
    def _add_target(self,name):
        nm=_norm(name)
        if not nm:return False,"Target name is required."
        targets=self._load_targets()
        if self._find_target(targets,name=nm)[1] is not None:return False,"Target already exists."
        now=_now()
        targets.append({"id":_sid(nm+now),"name":nm,"status":"not_used","values":{},"created":now,"updated":now})
        if not self._save_targets(targets):return False,"Save failed."
        return True,f"Target added: {nm}"
    def _add_element(self,key,val):
        k=_norm(key)
        if not k:return False,"Key is required."
        v=_clamp_u16(val)
        if v is None:return False,"Value must be a number (0-65535)."
        values=self._load_target_values()
        for ex in values.keys():
            if _kci(ex)==_kci(k):return False,"Element already exists."
        values[k]={"priority":v}
        if not _write_json(_target_values_path(),values):return False,"Save failed."
        return True,f"Element added: {k}={v}"
    def _update_selected_target(self,updates):
        if not isinstance(self._selected_target,dict):return False,"No target selected."
        tid=_norm(self._selected_target.get("id",""))
        name=_norm(self._selected_target.get("name",""))
        targets=self._load_targets()
        idx,t=self._find_target(targets,name=name,tid=tid if tid else None)
        if t is None:return False,"Target not found."
        vals=self._merge_values(t.get("values",{}),updates)
        t["values"]=vals
        t["updated"]=_now()
        if not self._save_targets(targets):return False,"Save failed."
        self._selected_target=t
        return True,f"Target updated: {name}"
    def _handle_command(self,clean):
        low=_kci(clean)
        if low=="clear":
            self._update_prompt()
            self.terminal.reset()
            return True,None
        if low=="reset":
            self._history=[]
            self._history_idx=None
            self._history_temp=""
            self._selected_target=None
            self._save_history()
            self._update_prompt()
            self.terminal.reset()
            return True,None
        if low in ("clear history","history clear"):
            self._history=[]
            self._history_idx=None
            self._history_temp=""
            self._save_history()
            return True,"History cleared."
        if low=="history":
            return True,self._history_lines()
        if low=="help":
            return True,self._help_text()
        m=re.match(r"^help\s+(.+)$",clean,re.I)
        if m:
            return True,self._help_command(m.group(1))
        if low in ("more","next"):
            if not self._last_search:return True,"No active search."
            self._on_show_more()
            return True,None
        m=re.match(r"^save\s+search\s+(.+)$",clean,re.I)
        if m:
            rest=_norm(m.group(1))
            if not rest:return True,"Search name is required."
            name,tail=(rest.split(None,1)+[""])[:2]
            name=self._strip_quotes(name)
            query=_norm(tail)
            if query.startswith("="):query=_norm(query[1:])
            if not query:
                if not isinstance(self._last_search,dict):return True,"No recent search to save."
                query=_norm(self._last_search.get("query",""))
            if not query:return True,"Search query is required."
            self._saved_searches[_norm(name)]=query
            self._save_saved_searches()
            return True,f"Saved search: {name}"
        m=re.match(r"^run\s+search\s+(.+)$",clean,re.I)
        if m:
            name=self._strip_quotes(m.group(1))
            query=_norm(self._saved_searches.get(name,""))
            if not query:return True,"Saved search not found."
            reply,kind=self._get_reply(query)
            if kind=="system":self.terminal.write_system(reply)
            else:self.terminal.write_output(reply)
            return True,None
        m=re.match(r"^show\s+(.+)$",clean,re.I)
        if m:
            sid=_norm(m.group(1))
            ok,msg=self._show_preview(sid)
            if msg:
                if ok:self.terminal.write_output(msg)
                else:self.terminal.write_system(msg)
            return True,None
        if low in ("back","exit"):
            if not self._selected_target:return True,"No target selected."
            name=_norm(self._selected_target.get("name",""))
            self._selected_target=None
            self._update_prompt()
            return True,(f"Exited target: {name}" if name else "Exited target.")
        if low in ("notes","commands","targets","settings"):
            ok=self._nav(low)
            return True,(f"Opened {low}." if ok else f"Open {low} failed.")
        m=re.match(r"^open\s+(\w+)$",clean,re.I)
        if m:
            key=_kci(m.group(1))
            nav_map={"note":"notes","notes":"notes","command":"commands","commands":"commands","target":"targets","targets":"targets","setting":"settings","settings":"settings"}
            if key in nav_map:
                ok=self._nav(nav_map[key])
                return True,(f"Opened {key}." if ok else f"Open {key} failed.")
        m=re.match(r"^add\s+element\s+(.+)$",clean,re.I)
        if m:
            rest=_norm(m.group(1))
            mm=re.match(r'(\"[^\"]*\"|\'[^\']*\'|\S+)\s+(\S+)',rest)
            if not mm:return True,"Usage: add element KEY VALUE"
            key=self._strip_quotes(mm.group(1))
            val=mm.group(2)
            ok,msg=self._add_element(key,val)
            return True,msg
        m=re.match(r"^use\s+target\s+(.+)$",clean,re.I)
        if m:
            name=self._strip_quotes(m.group(1))
            ok,msg,target=self._set_live_target(name)
            if ok:
                self._selected_target=target
                self._update_prompt()
            return True,msg
        m=re.match(r"^add\s+(new\s+)?target\s+(.+)$",clean,re.I)
        if m:
            name=self._strip_quotes(m.group(2))
            ok,msg=self._add_target(name)
            return True,msg
        m=re.match(r"^select\s+from\s+targets\s+(.+)$",clean,re.I)
        if not m:m=re.match(r"^select\s+target\s+(.+)$",clean,re.I)
        if m:
            name,block=self._split_block(m.group(1))
            name=self._strip_quotes(name)
            ok,msg=self._select_target(name,set_live=False)
            if not ok:return True,msg
            adds=self._parse_assignments(block)
            if adds:
                miss=self._missing_target_key(adds)
                if miss:return True,f"{miss} is not exist add it first in Targets>Set Elements"
                adds=self._normalize_update_keys(adds)
                ok2,msg2=self._update_selected_target(adds)
                return True,(msg+" | "+msg2)
            return True,msg
        if re.match(r"^add\s+",clean,re.I):
            if not self._selected_target:return True,"No target selected."
            adds=self._parse_assignments(clean)
            if not adds:return True,"No fields found."
            miss=self._missing_target_key(adds)
            if miss:return True,f"{miss} is not exist add it first in Targets>Set Elements"
            adds=self._normalize_update_keys(adds)
            ok,msg=self._update_selected_target(adds)
            return True,msg
        return False,None
    def _get_reply(self,text):
        ctx=self._build_context()
        reply=_logic_reply(text,self._questions,ctx)
        if isinstance(reply,dict) and "text" in reply:
            self._apply_search_state(text,reply)
            kind=_kci(reply.get("kind","")) or "output"
            return str(reply.get("text","")),kind
        if reply:return str(reply),"output"
        return "not configered yet","system"
