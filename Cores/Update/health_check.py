import json
import os
import sqlite3
import time
from dataclasses import dataclass,field
from pathlib import Path
from Cores import common_db
from Cores import recycle_bin
from . import update_helpers as _update_helpers
from . import update_service as _update_service
DEFAULT_APP_VERSION=_update_helpers.DEFAULT_APP_VERSION
@dataclass
class HealthReport:
    repairs:list[str]=field(default_factory=list)
    warnings:list[str]=field(default_factory=list)
    errors:list[str]=field(default_factory=list)
    db_deferred:bool=False

    @property
    def fatal(self):
        return bool(self.errors)

    def has_notice(self):
        return bool(self.repairs or self.warnings)

    def merge(self,other):
        if not other:
            return self
        self.repairs.extend(other.repairs)
        self.warnings.extend(other.warnings)
        self.errors.extend(other.errors)
        self.db_deferred=self.db_deferred or bool(other.db_deferred)
        return self

    def notice_text(self):
        lines=[]
        if self.repairs:
            lines.append("Startup repairs completed:")
            lines.extend(f"- {item}" for item in self.repairs)
        if self.warnings:
            if lines:
                lines.append("")
            lines.append("Startup warnings:")
            lines.extend(f"- {item}" for item in self.warnings)
        return "\n".join(lines).strip() or "Startup health check completed."

    def fatal_text(self):
        lines=["Startup health check failed."]
        if self.errors:
            lines.append("")
            lines.extend(f"- {item}" for item in self.errors)
        if self.repairs or self.warnings:
            lines.append("")
            lines.append(self.notice_text())
        return "\n".join(lines).strip()
def _root_dir():
    return Path(__file__).resolve().parents[2]
def data_dir():
    return str(_root_dir().joinpath("Data"))
def logs_dir():
    return str(_root_dir().joinpath("Logs"))
def backups_dir():
    return str(_root_dir().joinpath("Backups"))
def update_dir():
    return str(_root_dir().joinpath("Cores","Update"))
def old_versions_dir():
    return os.path.join(update_dir(),"OldVersions")
def db_path():
    return common_db.db_path()
def settings_path():
    return os.path.join(data_dir(),"settings.json")
def target_values_path():
    return os.path.join(data_dir(),"target_values.json")
def targets_path():
    return os.path.join(data_dir(),"Targets.json")
def legacy_targets_path():
    return os.path.join(data_dir(),"Targes.json")
def version_info_path():
    return str(_update_helpers.version_info_path())
def update_state_path():
    return str(_update_helpers.update_state_path())
def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def default_settings():
    return {
        "backup":{"auto_enabled":False,"interval_hours":24,"keep":20},
        "chat_output":{"structured_output":False},
        "security":{
            "app_lock_enabled":False,
            "pin_salt":"",
            "pin_hash":"",
            "enc_enabled":False,
            "enc_salt":"",
        },
        "targets":{"allow_dots_colons":False},
        "update":{"auto_enabled":False,"check_interval_hours":24,"repo_url":_update_helpers.OFFICIAL_SOURCE_REPO,"manifest_url":_update_helpers.GITHUB_RELEASES_API_URL,"last_checked":"","last_channel":"stable"},
    }
def default_target_values():
    return {}
def default_targets():
    return []
def default_update_state(current_version=DEFAULT_APP_VERSION):
    return _update_service.default_update_state(current_version)
def _write_json(path,obj):
    tmp=path+".tmp"
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(tmp,"w",encoding="utf-8") as fh:
        json.dump(obj,fh,ensure_ascii=False,indent=2)
    os.replace(tmp,path)
def _quarantine_file(path):
    stamp=time.strftime("%Y%m%d-%H%M%S")
    new_path=f"{path}.broken-{stamp}"
    os.replace(path,new_path)
    return os.path.basename(new_path)
def _ensure_dir(path,label,report):
    if os.path.isdir(path):
        return
    os.makedirs(path,exist_ok=True)
    report.repairs.append(f"Created {label}")
def _load_json_checked(path,label,valid_types,report,repair_on_invalid=False,default_value=None):
    if not os.path.isfile(path):
        _write_json(path,default_value)
        report.repairs.append(f"Created {label}")
        return default_value
    try:
        with open(path,"r",encoding="utf-8") as fh:
            data=json.load(fh)
    except Exception as exc:
        if repair_on_invalid:
            broken_name=_quarantine_file(path)
            _write_json(path,default_value)
            report.repairs.append(f"Rebuilt {label}")
            report.warnings.append(f"{label} was invalid and was replaced. Old copy saved as {broken_name}.")
            return default_value
        report.errors.append(f"{label} is invalid JSON and cannot be repaired safely ({exc}).")
        return None
    if valid_types and not isinstance(data,valid_types):
        if repair_on_invalid:
            broken_name=_quarantine_file(path)
            _write_json(path,default_value)
            report.repairs.append(f"Rebuilt {label}")
            report.warnings.append(f"{label} had the wrong structure and was replaced. Old copy saved as {broken_name}.")
            return default_value
        names=", ".join(t.__name__ for t in valid_types)
        report.errors.append(f"{label} must be {names}.")
        return None
    return data
def _ensure_version_info(report):
    path=version_info_path()
    legacy_path=str(_update_helpers.legacy_version_info_path())
    if not os.path.isfile(path) and os.path.isfile(legacy_path):
        legacy_ver=_update_helpers.coerce_local_version(_update_helpers.read_text(legacy_path,""),"")
        if legacy_ver:
            _update_service.write_current_version(legacy_ver)
            report.repairs.append("Created Cores/Update/CurrentVersion.info from legacy CurentVersion.info")
            return legacy_ver
    if not os.path.isfile(path):
        ver=_update_service.write_current_version(DEFAULT_APP_VERSION)
        report.repairs.append("Created Cores/Update/CurrentVersion.info")
        return ver
    try:
        text=_update_helpers.read_text(path,"").strip()
    except Exception as exc:
        report.errors.append(f"Cores/Update/CurrentVersion.info could not be read ({exc}).")
        return DEFAULT_APP_VERSION
    ver=_update_helpers.coerce_local_version(text,"")
    if ver:
        if text!=ver or not os.path.isfile(legacy_path):
            _update_service.write_current_version(ver)
            report.repairs.append("Normalized Cores/Update/CurrentVersion.info")
        return ver
    ver=_update_service.write_current_version(DEFAULT_APP_VERSION)
    report.repairs.append("Reset invalid Cores/Update/CurrentVersion.info")
    report.warnings.append("CurrentVersion.info had a non-semantic version and was reset to the default manifest version.")
    return ver
def _ensure_targets_file(report):
    target_file=targets_path()
    legacy_file=legacy_targets_path()
    if os.path.isfile(target_file):
        return _load_json_checked(target_file,"Data/Targets.json",(list,),report,False,default_targets())
    if os.path.isfile(legacy_file):
        data=_load_json_checked(legacy_file,"Data/Targes.json",(list,),report,False,default_targets())
        if data is None:
            return None
        _write_json(target_file,data)
        report.repairs.append("Created Data/Targets.json from legacy Data/Targes.json")
        return data
    _write_json(target_file,default_targets())
    report.repairs.append("Created Data/Targets.json")
    return default_targets()
def _normalize_update_state(data,current_version):
    return _update_service.normalize_update_state(data,current_version)
def _check_update_runtime_state(state_data,report):
    if not isinstance(state_data,dict):
        return
    pending=str(state_data.get("pending_version","") or "").strip()
    current=str(state_data.get("current_version","") or "").strip()
    err=str(state_data.get("last_launch_error","") or state_data.get("last_error","") or "").strip()
    recovery_reason=str(state_data.get("recovery_reason","") or "").strip()
    pending_matches=_update_service.pending_update_matches_current_install(state_data,current)
    if state_data.get("recovery_required"):
        if recovery_reason:
            report.warnings.append(f"Recovery mode is recommended: {recovery_reason}")
        else:
            report.warnings.append("Recovery mode is recommended before normal startup.")
    if state_data.get("update_in_progress"):
        if pending and pending_matches:
            if err:
                report.warnings.append(f"Installed update {pending} is still waiting for launch confirmation: {err}")
        elif pending:
            report.warnings.append(f"Update state shows an unfinished update to {pending}. Review recovery options before continuing.")
        else:
            report.warnings.append("Update state shows an unfinished update. Review recovery options before continuing.")
    elif pending:
        report.warnings.append(f"Pending update state detected for version {pending}.")
    if state_data.get("last_launch_ok") is False:
        if err:
            report.warnings.append(f"Previous launch did not exit cleanly: {err}")
        else:
            report.warnings.append("Previous launch did not exit cleanly.")
def _security_state(settings_data):
    if not isinstance(settings_data,dict):
        return False,""
    sec=settings_data.get("security",{})
    if not isinstance(sec,dict):
        return False,""
    return bool(sec.get("enc_enabled",False)),str(sec.get("enc_salt","") or "").strip()
def _check_database(report,after_security,settings_data):
    dbp=db_path()
    enc_path=dbp+".enc"
    enc_enabled,enc_salt=_security_state(settings_data)
    if os.path.isfile(enc_path) and not enc_enabled:
        report.errors.append("Encrypted database file exists but settings.json does not enable encryption.")
        return
    if enc_enabled and not enc_salt:
        report.errors.append("Encryption is enabled in settings.json but enc_salt is missing.")
        return
    if not after_security and enc_enabled and os.path.isfile(enc_path) and not os.path.isfile(dbp):
        report.db_deferred=True
        report.warnings.append("Encrypted database detected. Database migration will run after unlock.")
        return
    created=not os.path.isfile(dbp)
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            common_db.ensure_schema(con)
    except Exception as exc:
        report.errors.append(f"Database validation failed ({exc}).")
        return
    if created:
        report.repairs.append("Initialized Data/Note_LOYA_V1.db")
    try:
        purged=int(recycle_bin.purge_expired(dbp))
    except Exception:
        purged=0
    if purged:
        report.repairs.append(f"Purged {purged} expired Recycle Bin item(s)")
def _read_current_version():
    return _update_service.get_app_version()
def _load_update_state_loose(current_version):
    return _update_service.get_update_state(current_version)
def mark_launch_started():
    current_version=_read_current_version()
    os.makedirs(update_dir(),exist_ok=True)
    state_data=_load_update_state_loose(current_version)
    state_data["current_version"]=current_version
    state_data["last_launch_started_at"]=_utc_now()
    state_data["last_launch_ok"]=False
    state_data["last_launch_error"]=""
    _write_json(update_state_path(),state_data)
def mark_launch_completed(ok=True,error=""):
    current_version=_read_current_version()
    os.makedirs(update_dir(),exist_ok=True)
    state_data=_load_update_state_loose(current_version)
    err=str(error or "").strip()
    state_data["current_version"]=current_version
    state_data["last_launch_completed_at"]=_utc_now()
    state_data["last_launch_ok"]=bool(ok)
    state_data["last_launch_error"]=err
    if ok:
        state_data["last_good_version"]=state_data.get("current_version") or current_version
        state_data["last_error"]=""
        state_data["recovery_required"]=False
        state_data["recovery_reason"]=""
    elif err:
        state_data["last_error"]=err
        state_data["recovery_required"]=True
        state_data["recovery_reason"]=err
    elif not ok:
        state_data["recovery_required"]=True
        state_data["recovery_reason"]="The previous launch did not exit cleanly."
    _write_json(update_state_path(),state_data)
def run_health_check(after_security=False):
    report=HealthReport()
    _ensure_dir(data_dir(),"Data/",report)
    _ensure_dir(logs_dir(),"Logs/",report)
    _ensure_dir(backups_dir(),"Backups/",report)
    _ensure_dir(update_dir(),"Cores/Update/",report)
    _ensure_dir(old_versions_dir(),"Cores/Update/OldVersions/",report)
    settings_data=_load_json_checked(
        settings_path(),
        "Data/settings.json",
        (dict,),
        report,
        False,
        default_settings(),
    )
    _load_json_checked(
        target_values_path(),
        "Data/target_values.json",
        (dict,list),
        report,
        False,
        default_target_values(),
    )
    _ensure_targets_file(report)
    current_version=_ensure_version_info(report)
    state_data=_load_json_checked(
        update_state_path(),
        "Cores/Update/state.json",
        (dict,),
        report,
        True,
        default_update_state(current_version),
    )
    if isinstance(state_data,dict):
        state_data,state_changed=_normalize_update_state(state_data,current_version)
        if state_changed:
            _write_json(update_state_path(),state_data)
            report.repairs.append("Normalized Cores/Update/state.json")
        _check_update_runtime_state(state_data,report)
    if report.fatal:
        return report
    _check_database(report,after_security,settings_data)
    return report
