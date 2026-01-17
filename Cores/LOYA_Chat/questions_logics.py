import os,json,sqlite3,re,difflib,shlex
from datetime import datetime
def _root_abs(*p):return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","..",*p))
def _db_path():return _root_abs("Data","Note_LOYA_V1.db")
def _targets_path():
    p1=_root_abs("Data","Targets.json")
    p2=_root_abs("Data","Targes.json")
    if os.path.isfile(p1) or not os.path.isfile(p2):return p1
    return p2
def _norm(s):return (str(s) if s is not None else "").strip()
def _low(s):return _norm(s).lower()
def _ell(s,n=60):
    s=_norm(s)
    return (s[:max(0,n-3)]+"...") if len(s)>n else s
def _read_json(p,default):
    try:
        if not os.path.isfile(p):return default
        with open(p,"r",encoding="utf-8") as f:return json.load(f)
    except Exception:return default
def _table_cols(con,t):
    try:
        cur=con.cursor()
        cur.execute(f"PRAGMA table_info({t})")
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []
def _has_table(con,t):
    try:
        cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(t,))
        return bool(cur.fetchone())
    except Exception:
        return False
def _split_tokens(text):
    try:
        return shlex.split(text)
    except Exception:
        return _norm(text).split()
def _expand_shortcuts(text,scope):
    if not text:return text
    scope=_low(scope)
    if scope=="notes":
        m={"n":"note_name=","c":"command_keyword=","t":"tags="}
    elif scope=="commands":
        m={"n":"command_tittle=","c":"command=","t":"tags="}
    elif scope=="targets":
        m={"n":"target_name=","c":"target_value=","t":"target_value="}
    elif scope=="targets_value":
        m={"n":"target_value=","c":"target_value=","t":"target_value="}
    else:
        m={}
    def repl(mm):
        k=_low(mm.group(1))
        return m.get(k,mm.group(0))
    return re.sub(r"\b([nct]):",repl,text)
def _parse_search_expr(raw,scope):
    text=_norm(raw)
    text=_expand_shortcuts(text,scope)
    tokens=_split_tokens(text)
    groups=[[]]
    limit_vals=[]
    used_keys=[]
    neg=False
    for tok in tokens:
        low=_low(tok)
        if low in ("and","or"):
            if low=="or" and groups[-1]:
                groups.append([])
            neg=False
            continue
        if low=="not":
            neg=not neg
            continue
        m=re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(!~|!=|~|=|:)(.*)$",tok)
        if not m:
            continue
        key=_low(m.group(1))
        op=m.group(2)
        val=_norm(m.group(3))
        if key=="limit":
            if val:limit_vals.append(val)
            neg=False
            continue
        if not val:
            neg=False
            continue
        neg_flag=neg
        neg=False
        if op.startswith("!"):
            op=op[1:]
            neg_flag=not neg_flag
        if op==":":op="="
        cond={"key":key,"op":op,"value":val,"neg":neg_flag}
        groups[-1].append(cond)
        used_keys.append(key)
    groups=[g for g in groups if g]
    return {"groups":groups,"limit_vals":limit_vals,"keys":used_keys}
def _limit_from_values(values,default=50):
    for v in (values or []):
        try:
            n=int(str(v).strip())
            if n>0:return min(200,n)
        except Exception:
            continue
    return default
def _scope_key(raw):
    s=" ".join(_low(raw).split())
    if s in ("notes","note"):return "notes"
    if s in ("commands","command"):return "commands"
    if s in ("targets","target"):return "targets"
    if s in ("targets value","target values","target value","targets values","values"):return "targets_value"
    return ""
_DEFAULT_LIMITS={
    "notes":10,
    "commands":10,
    "targets":10,
    "targets_value":10,
}
_ALLOWED_FILTERS={
    "notes":{"keyword","general","note_name","tags","command_keyword","category","sub_category","description_keyword","command_tittle","command_title","cmd_note_title","command","date_from","date_to","has","missing","limit"},
    "commands":{"keyword","general","command_tittle","command_title","cmd_note_title","category","sub_category","description_keyword","tags","command_keyword","command","date_from","date_to","has","missing","limit"},
    "targets":{"keyword","general","target_name","target_value","has","missing","limit"},
    "targets_value":{"keyword","general","target_value","has","missing","limit"},
}
def _like(val):return f"%{_low(val)}%"
def _format_header(title,count,offset=0,shown=0):
    if count>0 and shown>0:
        return f"{title}: {count} (showing {offset+1}-{offset+shown})"
    return f"{title}: {count}"
def _result(text,total=0,shown=0,offset=0,limit=0,scope="",kind="output"):
    remaining=max(0,total-(offset+shown))
    return {
        "text":text,
        "total":total,
        "shown":shown,
        "offset":offset,
        "limit":limit,
        "remaining":remaining,
        "has_more":remaining>0,
        "scope":scope,
        "kind":kind,
    }
def _unknown_filter_message(keys,scope,field_values=None):
    allowed=_ALLOWED_FILTERS.get(scope,set())
    unknown=[k for k in (keys or []) if k not in allowed]
    if not unknown:return ""
    choices=sorted(allowed)
    suggestions=[]
    for k in unknown:
        match=difflib.get_close_matches(k,choices,n=1,cutoff=0.6)
        if match:suggestions.append((k,match[0]))
    if len(unknown)==1 and suggestions:
        return f"Unknown filter: {unknown[0]}. Did you mean {suggestions[0][1]}?"
    if suggestions:
        pairs=", ".join([f"{a}->{b}" for a,b in suggestions])
        return f"Unknown filters: {', '.join(unknown)}. Did you mean: {pairs}?"
    return f"Unknown filters: {', '.join(unknown)}."
def _pagination_from_context(context,limit):
    offset=0
    if isinstance(context,dict):
        pag=context.get("pagination")
        if isinstance(pag,dict):
            if "offset" in pag:
                try:offset=max(0,int(str(pag.get("offset")).strip()))
                except Exception:offset=0
            if "limit" in pag:
                try:
                    n=int(str(pag.get("limit")).strip())
                    if n>0:limit=min(200,n)
                except Exception:
                    pass
    return offset,limit
def _target_map_from_context(context):
    if not isinstance(context,dict):return {}
    vals=context.get("target_values")
    if vals is None and isinstance(context.get("target"),dict):
        vals=context.get("target",{}).get("values")
    if not isinstance(vals,dict):return {}
    out={}
    for k,v in vals.items():
        kk=_low(k);vv=_norm(v)
        if kk and vv:out[kk]=vv
    return out
def _apply_target(cmd,target_map):
    s=_norm(cmd)
    if not s or not target_map:return s
    rx=re.compile(r"\{([^{}]+)\}")
    def repl(m):
        k=_low(m.group(1))
        return target_map.get(k,"{"+m.group(1)+"}")
    try:return rx.sub(repl,s)
    except Exception:return s
def _apply_target_warn(cmd,target_map):
    s=_norm(cmd)
    if not s or not target_map:return s,[]
    rx=re.compile(r"\{([^{}]+)\}")
    missing=[]
    def repl(m):
        k=_low(m.group(1))
        if k in target_map:return target_map[k]
        missing.append(m.group(1))
        return "{"+m.group(1)+"}"
    try:
        out=rx.sub(repl,s)
    except Exception:
        return s,[]
    dedup=[]
    seen=set()
    for k in missing:
        kk=_low(k)
        if kk in seen:continue
        seen.add(kk);dedup.append(k)
    return out,dedup
def _parse_date(val):
    v=_norm(val)
    if not v:return None
    try:
        if v.endswith("Z"):v=v[:-1]+"+00:00"
        return datetime.fromisoformat(v)
    except Exception:
        try:return datetime.strptime(v,"%Y-%m-%d")
        except Exception:return None
def _row_date(row):
    for k in ("updated_at","created_at"):
        dt=_parse_date(row.get(k,""))
        if dt:return dt
    return None
def _match_text(hay,val,op):
    h=_low(hay)
    v=_low(val)
    if not v:return False
    if op=="=":
        return v in h
    if op=="~":
        if v in h:return True
        try:
            return difflib.SequenceMatcher(None,h,v).ratio()>=0.6
        except Exception:
            return False
    return False
def _split_multi(val):
    s=_norm(val)
    if not s:return []
    parts=[_norm(p) for p in s.split(",")]
    return [p for p in parts if p]
def _match_all(hay,vals,op):
    for v in vals:
        if not _match_text(hay,v,op):
            return False
    return True
def _target_values_text(values):
    if not isinstance(values,dict):return ""
    parts=[]
    for k,v in values.items():
        kk=_norm(k);vv=_norm(v)
        if kk:parts.append(kk)
        if vv:parts.append(vv)
    return " ".join(parts)
def _field_present(row,scope,field):
    f=_low(field)
    if scope=="notes":
        if f=="note_name":return bool(_norm(row.get("note_name","")))
        if f in ("content","command","tags","category","sub_category","description_keyword","command_keyword","command_tittle","command_title","cmd_note_title","keyword","general"):
            return bool(_norm(row.get("content","")))
        if f in ("updated_at","created_at"):return bool(_norm(row.get(f,"")))
    if scope=="commands":
        if f in ("command_tittle","command_title","cmd_note_title"):return bool(_norm(row.get("cmd_note_title","") or row.get("note_name","")))
        if f in ("category","sub_category"):return bool(_norm(row.get(f,"")))
        if f=="description_keyword":return bool(_norm(row.get("description","")))
        if f=="tags":return bool(_norm(row.get("tags","")))
        if f in ("command_keyword","command"):return bool(_norm(row.get("command","")))
        if f in ("updated_at","created_at"):return bool(_norm(row.get(f,"")))
    if scope=="targets":
        if f=="target_name":return bool(_norm(row.get("name","")))
        if f=="target_value":return bool(_target_values_text(row.get("values",{})))
        values=row.get("values",{})
        if isinstance(values,dict):
            for k,v in values.items():
                if _low(k)==f and _norm(v):return True
    if scope=="targets_value":
        if f=="target_value":return bool(_norm(row.get("key","")))
    return False
def _match_condition(row,scope,cond):
    key=cond.get("key","")
    op=cond.get("op","=")
    val=cond.get("value","")
    if key in ("date_from","date_to"):
        dt=_row_date(row)
        if not dt:return False
        dv=_parse_date(val)
        if not dv:return False
        return dt>=dv if key=="date_from" else dt<=dv
    if key in ("has","missing"):
        hit=_field_present(row,scope,val)
        return hit if key=="has" else (not hit)
    vals=_split_multi(val)
    if not vals:return False
    if scope=="notes":
        if key in ("keyword","general"):
            blob=" ".join([row.get("note_name",""),row.get("content","")])
            return _match_all(blob,vals,op)
        if key=="note_name":
            return _match_all(row.get("note_name",""),vals,op)
        if key in ("tags","command_keyword","category","sub_category","description_keyword","command_tittle","command_title","cmd_note_title","command"):
            return _match_all(row.get("content",""),vals,op)
        if key=="content":
            return _match_all(row.get("content",""),vals,op)
    if scope=="commands":
        if key in ("keyword","general"):
            blob=" ".join([row.get("note_name",""),row.get("cmd_note_title",""),row.get("category",""),row.get("sub_category",""),row.get("description",""),row.get("tags",""),row.get("command","")])
            return _match_all(blob,vals,op)
        if key in ("command_tittle","command_title","cmd_note_title"):
            title=row.get("cmd_note_title","") or row.get("note_name","")
            return _match_all(title,vals,op)
        if key=="category":
            return _match_all(row.get("category",""),vals,op)
        if key=="sub_category":
            return _match_all(row.get("sub_category",""),vals,op)
        if key=="description_keyword":
            return _match_all(row.get("description",""),vals,op)
        if key=="tags":
            return _match_all(row.get("tags",""),vals,op)
        if key in ("command_keyword","command"):
            return _match_all(row.get("command",""),vals,op)
    if scope=="targets":
        if key in ("keyword","general"):
            blob=_norm(row.get("name",""))+" "+_target_values_text(row.get("values",{}))
            return _match_all(blob,vals,op)
        if key=="target_name":
            return _match_all(row.get("name",""),vals,op)
        if key=="target_value":
            return _match_all(_target_values_text(row.get("values",{})),vals,op)
    if scope=="targets_value":
        if key in ("keyword","general","target_value"):
            return _match_all(row.get("key",""),vals,op)
    return False
def _match_groups(row,scope,groups):
    if not groups:return False,0
    best=-1
    for group in groups:
        ok=True
        score=0
        for cond in group:
            hit=_match_condition(row,scope,cond)
            if cond.get("neg"):hit=not hit
            if not hit:
                ok=False;break
            if hit and not cond.get("neg") and cond.get("key") not in ("date_from","date_to","has","missing"):
                score+=1
        if ok and score>best:best=score
    return best>=0,best
def _search_notes(groups,limit=50,offset=0):
    dbp=_db_path()
    if not os.path.isfile(dbp):return _result("Notes database not found.",0,0,offset,limit,"notes","system")
    try:
        con=sqlite3.connect(dbp,timeout=5)
    except Exception:
        return _result("Notes database not available.",0,0,offset,limit,"notes","system")
    try:
        if not _has_table(con,"Notes"):
            return _result("Notes table not found.",0,0,offset,limit,"notes","system")
        cols=set(_table_cols(con,"Notes"))
        sel=["id"]
        for c in ("note_name","content","created_at","updated_at"):
            if c in cols:sel.append(c)
        sql="SELECT "+",".join(sel)+" FROM Notes"
        cur=con.cursor();cur.execute(sql)
        rows=[]
        for r in cur.fetchall():
            item={}
            for i,c in enumerate(sel):
                item[c]=r[i] if i<len(r) else ""
            ok,score=_match_groups(item,"notes",groups)
            if ok:
                item["score"]=score
                rows.append(item)
        total=len(rows)
        if not rows:return _result("No notes found.",0,0,offset,limit,"notes","system")
        rows.sort(key=lambda x:(int(x.get("score",0)),_row_date(x) or datetime.min),reverse=True)
        if offset>=total:return _result("No more results.",total,0,offset,limit,"notes","system")
        chunk=rows[offset:offset+limit]
        lines=[_format_header("Notes",total,offset,len(chunk))]
        for i,it in enumerate(chunk,offset+1):
            nid=it.get("id","")
            n=_norm(it.get("note_name","")) or "(no name)"
            u=_norm(it.get("updated_at","") or it.get("created_at","")).replace("T"," ")[:19]
            tail=f" id={nid}" if str(nid).isdigit() else ""
            if u:tail+=f" updated={u}"
            lines.append(f"{i}. {n}{tail}")
        if total>offset+limit:lines.append(f"... {total-(offset+limit)} more")
        return _result("\n".join(lines),total,len(chunk),offset,limit,"notes")
    finally:
        try:con.close()
        except Exception:pass
def _query_commands(con,table):
    if not _has_table(con,table):return []
    cols=set(_table_cols(con,table))
    if not cols:return []
    sel=[]
    if "id" in cols:sel.append("id")
    else:sel.append("rowid as id")
    for c in ("note_name","cmd_note_title","category","sub_category","description","tags","command","created_at","updated_at"):
        if c in cols:sel.append(c)
    sql="SELECT "+",".join(sel)+f" FROM {table}"
    cur=con.cursor();cur.execute(sql)
    rows=cur.fetchall()
    out=[]
    for r in rows:
        item={};idx=0
        for col in sel:
            key=col.split(" as ")[-1]
            item[key]=r[idx] if idx<len(r) else ""
            idx+=1
        item["source"]=table
        out.append(item)
    return out
def _search_commands(groups,limit=50,target_map=None,offset=0):
    dbp=_db_path()
    if not os.path.isfile(dbp):return _result("Commands database not found.",0,0,offset,limit,"commands","system")
    try:
        con=sqlite3.connect(dbp,timeout=5)
    except Exception:
        return _result("Commands database not available.",0,0,offset,limit,"commands","system")
    try:
        rows=[]
        rows+=_query_commands(con,"Commands")
        rows+=_query_commands(con,"CommandsNotes")
        matched=[]
        for it in rows:
            ok,score=_match_groups(it,"commands",groups)
            if ok:
                it["score"]=score
                matched.append(it)
        total=len(matched)
        if not matched:return _result("No commands found.",0,0,offset,limit,"commands","system")
        matched.sort(key=lambda x:(int(x.get("score",0)),_row_date(x) or datetime.min),reverse=True)
        if offset>=total:return _result("No more results.",total,0,offset,limit,"commands","system")
        chunk=matched[offset:offset+limit]
        lines=[_format_header("Commands",total,offset,len(chunk))]
        for i,it in enumerate(chunk,offset+1):
            title=_norm(it.get("cmd_note_title") or it.get("note_name") or "")
            if not title:title="(no title)"
            cat=_norm(it.get("category",""))
            sub=_norm(it.get("sub_category",""))
            tags=_norm(it.get("tags",""))
            cmd_raw=it.get("command","")
            cmd_adj,missing=_apply_target_warn(cmd_raw,target_map)
            cmd=_ell(cmd_adj,70)
            seg=[]
            if cat or sub:seg.append(f"{cat}/{sub}".strip("/"))
            cid=_norm(it.get("id",""))
            if cid:seg.append(f"id={cid}")
            if tags:seg.append(f"tags={tags}")
            if cmd:
                if missing:seg.append(f"cmd={cmd} [missing: {', '.join(missing)}]")
                else:seg.append(f"cmd={cmd}")
            meta=" | ".join(seg) if seg else ""
            lines.append(f"{i}. {title}" + (f" | {meta}" if meta else ""))
        if total>offset+limit:lines.append(f"... {total-(offset+limit)} more")
        return _result("\n".join(lines),total,len(chunk),offset,limit,"commands")
    finally:
        try:con.close()
        except Exception:pass
def _search_targets(groups,limit=50,offset=0):
    p=_targets_path()
    data=_read_json(p,[])
    if not isinstance(data,list):data=[]
    rows=[]
    for t in data:
        if not isinstance(t,dict):continue
        name=_norm(t.get("name",""))
        values=t.get("values",{})
        if not isinstance(values,dict):values={}
        item={"name":name,"values":values,"status":_norm(t.get("status",""))}
        ok,score=_match_groups(item,"targets",groups)
        if ok:
            item["score"]=score
            rows.append(item)
    total=len(rows)
    if not rows:return _result("No targets found.",0,0,offset,limit,"targets","system")
    rows.sort(key=lambda x:_low(x.get("name","")))
    rows.sort(key=lambda x:int(x.get("score",0)),reverse=True)
    if offset>=total:return _result("No more results.",total,0,offset,limit,"targets","system")
    chunk=rows[offset:offset+limit]
    lines=[_format_header("Targets",total,offset,len(chunk))]
    for i,it in enumerate(chunk,offset+1):
        pairs=[]
        for k,v in (it.get("values") or {}).items():
            vv=_norm(v)
            if vv:pairs.append(f"{k}={vv}")
        val_txt=_ell(", ".join(pairs),80)
        tail=f" | {val_txt}" if val_txt else ""
        lines.append(f"{i}. {it.get('name','')}{tail}")
    if total>offset+limit:lines.append(f"... {total-(offset+limit)} more")
    return _result("\n".join(lines),total,len(chunk),offset,limit,"targets")
def _search_target_values(groups,limit=50,offset=0):
    p=_root_abs("Data","target_values.json")
    data=_read_json(p,{})
    if not isinstance(data,dict):data={}
    keys=[_norm(k) for k in data.keys() if _norm(k)]
    if not keys:return _result("No target values found.",0,0,offset,limit,"targets_value","system")
    rows=[]
    for k in keys:
        item={"key":k}
        ok,score=_match_groups(item,"targets_value",groups)
        if ok:
            item["score"]=score
            rows.append(item)
    total=len(rows)
    if not rows:return _result("No target values found.",0,0,offset,limit,"targets_value","system")
    if offset>=total:return _result("No more results.",total,0,offset,limit,"targets_value","system")
    rows.sort(key=lambda x:_low(x.get("key","")))
    rows.sort(key=lambda x:int(x.get("score",0)),reverse=True)
    chunk=rows[offset:offset+limit]
    lines=[_format_header("Target values",total,offset,len(chunk))]
    for i,it in enumerate(chunk,offset+1):
        lines.append(f"{i}. {it.get('key','')}")
    if total>offset+limit:lines.append(f"... {total-(offset+limit)} more")
    return _result("\n".join(lines),total,len(chunk),offset,limit,"targets_value")
def handle_query(query, questions=None, context=None):
    q=_norm(query)
    if not q:return None
    m=re.match(r"^search\s+in\s+(.+?)\s+for\s+(.+)$",q,re.I)
    if not m:return None
    scope=_scope_key(m.group(1))
    if not scope:return _result("Unknown search scope.",0,0,0,0,"","system")
    parsed=_parse_search_expr(m.group(2),scope)
    groups=parsed.get("groups",[])
    if not groups:return _result("No filters found.",0,0,0,0,scope,"system")
    keys=parsed.get("keys",[])
    hint=_unknown_filter_message(keys,scope)
    limit=_limit_from_values(parsed.get("limit_vals",[]),_DEFAULT_LIMITS.get(scope,10))
    offset,limit=_pagination_from_context(context,limit)
    if hint:return _result(hint,0,0,offset,limit,scope,"system")
    if any(k in ("has","missing") for k in keys):
        allowed_fields={k for k in _ALLOWED_FILTERS.get(scope,set()) if k not in ("limit","date_from","date_to","has","missing")}
        bad=[]
        for g in groups:
            for c in g:
                if c.get("key") in ("has","missing"):
                    fv=_low(c.get("value",""))
                    if fv and fv not in allowed_fields:bad.append(fv)
        if bad:
            bad=list(dict.fromkeys(bad))
            return _result(f"Unknown field: {', '.join(bad)}.",0,0,offset,limit,scope,"system")
    target_map=_target_map_from_context(context)
    if scope=="notes":return _search_notes(groups,limit,offset)
    if scope=="commands":return _search_commands(groups,limit,target_map,offset)
    if scope=="targets":return _search_targets(groups,limit,offset)
    if scope=="targets_value":return _search_target_values(groups,limit,offset)
    return _result("Unknown search scope.",0,0,offset,limit,scope,"system")
