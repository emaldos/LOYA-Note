import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
APP_NAME="LOYA Note"
DEFAULT_APP_VERSION="5.1.1"
OFFICIAL_SOURCE_REPO="https://github.com/emaldos/LOYA-Note"
OFFICIAL_SOURCE_OWNER="emaldos"
OFFICIAL_SOURCE_NAME="LOYA-Note"
REMOTE_MANIFEST_VERSION=1
GITHUB_RELEASES_API_URL=f"https://api.github.com/repos/{OFFICIAL_SOURCE_OWNER}/{OFFICIAL_SOURCE_NAME}/releases/latest"
_SEMVER_RX=re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHORT_VER_RX=re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_GITHUB_REPO_RX=re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?(?:$|#|\?)",re.I)
_SHA256_RX=re.compile(r"^[a-f0-9]{64}$",re.I)
_COMMIT_SHA_RX=re.compile(r"^[a-f0-9]{7,40}$",re.I)
_ALLOWED_DOWNLOAD_REDIRECT_HOSTS={"github.com","api.github.com","codeload.github.com","objects.githubusercontent.com","github-releases.githubusercontent.com"}
def root_dir():
    return Path(__file__).resolve().parents[2]
def update_dir():
    return root_dir().joinpath("Cores","Update")
def version_info_path():
    return update_dir().joinpath("CurrentVersion.info")
def legacy_version_info_path():
    return update_dir().joinpath("CurentVersion.info")
def update_state_path():
    return update_dir().joinpath("state.json")
def update_log_path():
    return root_dir().joinpath("Logs","Update_log.log")
def normalize_text(value):
    return str(value or "").strip()
def parse_semver(text):
    m=_SEMVER_RX.match(normalize_text(text))
    if not m:
        return None
    return int(m.group(1)),int(m.group(2)),int(m.group(3))
def is_semver(text):
    return bool(parse_semver(text))
def normalize_semver(text,fallback=""):
    parts=parse_semver(text)
    if not parts:
        return normalize_text(fallback)
    return ".".join(str(int(x)) for x in parts)
def coerce_local_version(text,fallback=""):
    raw=normalize_text(text)
    if not raw:
        return normalize_text(fallback)
    if raw[:1] in ("v","V"):
        raw=raw[1:].strip()
    ver=normalize_semver(raw,"")
    if ver:
        return ver
    m=_SHORT_VER_RX.match(raw)
    if m:
        return f"{int(m.group(1))}.{int(m.group(2))}.0"
    return normalize_text(fallback)
def compare_semver(a,b):
    av=parse_semver(a)
    bv=parse_semver(b)
    if not av or not bv:
        raise ValueError("compare_semver requires X.X.X values")
    if av<bv:
        return -1
    if av>bv:
        return 1
    return 0
def version_to_tag(version):
    ver=normalize_semver(version,"")
    return f"v{ver}" if ver else ""
def tag_to_version(tag):
    raw=normalize_text(tag)
    if raw[:1] in ("v","V"):
        raw=raw[1:].strip()
    return normalize_semver(raw,"")
def normalize_sha256(value):
    raw=normalize_text(value).lower()
    return raw if _SHA256_RX.fullmatch(raw) else ""
def normalize_commit_sha(value):
    raw=normalize_text(value).lower()
    return raw if _COMMIT_SHA_RX.fullmatch(raw) else ""
def canonical_repo_parts(repo_url=""):
    raw=normalize_text(repo_url)
    m=_GITHUB_REPO_RX.match(raw)
    if not m:
        return "","",""
    owner=normalize_text(m.group(1))
    name=normalize_text(m.group(2))
    canonical=f"https://github.com/{owner}/{name}"
    return owner,name,canonical
def canonical_repo_url(repo_url=""):
    return canonical_repo_parts(repo_url)[2]
def is_official_repo(repo_url="",owner="",name=""):
    if owner and name:
        return owner.lower()==OFFICIAL_SOURCE_OWNER.lower() and name.lower()==OFFICIAL_SOURCE_NAME.lower()
    got_owner,got_name,_=canonical_repo_parts(repo_url)
    if not got_owner or not got_name:
        return False
    return is_official_repo(owner=got_owner,name=got_name)
def _url_parts(url):
    try:
        p=urlparse(normalize_text(url))
        return p.scheme.lower(),p.netloc.lower(),p.path or ""
    except Exception:
        return "","",""
def is_allowed_download_redirect_url(url):
    scheme,host,_=_url_parts(url)
    return scheme in ("http","https") and host in _ALLOWED_DOWNLOAD_REDIRECT_HOSTS
def is_official_package_url(url,owner="",name=""):
    scheme,host,path=_url_parts(url)
    if scheme not in ("http","https"):
        return False
    owner=(normalize_text(owner) or OFFICIAL_SOURCE_OWNER).lower()
    name=(normalize_text(name) or OFFICIAL_SOURCE_NAME).lower()
    path=(path or "").lower()
    if host=="github.com":
        return path.startswith(f"/{owner}/{name}/releases/download/") or path.startswith(f"/{owner}/{name}/archive/refs/tags/") or path.startswith(f"/{owner}/{name}/archive/") or path.startswith(f"/{owner}/{name}/zipball/")
    if host=="api.github.com":
        return path.startswith(f"/repos/{owner}/{name}/zipball") or path.startswith(f"/repos/{owner}/{name}/tarball") or path.startswith(f"/repos/{owner}/{name}/releases/assets/") or path.startswith(f"/repos/{owner}/{name}/releases/")
    if host=="codeload.github.com":
        return path.startswith(f"/{owner}/{name}/zip/") or path.startswith(f"/{owner}/{name}/legacy.zip/") or path.startswith(f"/{owner}/{name}/tar.gz/")
    return False
def build_windows_app_id(version):
    ver=coerce_local_version(version,DEFAULT_APP_VERSION)
    owner=re.sub(r"[^A-Za-z0-9]+",".",OFFICIAL_SOURCE_OWNER).strip(".") or "loya"
    name=re.sub(r"[^A-Za-z0-9]+",".",OFFICIAL_SOURCE_NAME).strip(".") or "note"
    return f"{owner}.{name}.{ver}"
def read_json(path,default=None):
    try:
        with open(path,"r",encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default
def write_json(path,obj):
    path=str(path)
    tmp=path+".tmp"
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(tmp,"w",encoding="utf-8") as fh:
        json.dump(obj,fh,ensure_ascii=False,indent=2)
    os.replace(tmp,path)
def read_text(path,default=""):
    try:
        with open(path,"r",encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return default
def write_text(path,text):
    path=str(path)
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"w",encoding="utf-8") as fh:
        fh.write(str(text))
def remote_manifest_template(version="",release_id="",commit_sha="",package_sha256="",html_url="",asset_url="",published_at=""):
    ver=normalize_semver(version,"") or DEFAULT_APP_VERSION
    return {
        "manifest_version":REMOTE_MANIFEST_VERSION,
        "source_repo":OFFICIAL_SOURCE_REPO,
        "source_owner":OFFICIAL_SOURCE_OWNER,
        "source_name":OFFICIAL_SOURCE_NAME,
        "version":ver,
        "source_tag":version_to_tag(ver),
        "package_sha256":normalize_sha256(package_sha256),
        "release_id":normalize_text(release_id),
        "commit_sha":normalize_commit_sha(commit_sha),
        "html_url":normalize_text(html_url),
        "asset_url":normalize_text(asset_url),
        "published_at":normalize_text(published_at),
    }
def validate_remote_manifest(data):
    if not isinstance(data,dict):
        raise ValueError("Remote manifest must be an object.")
    repo_url=normalize_text(data.get("source_repo") or data.get("repo_url") or data.get("repository") or "")
    owner=normalize_text(data.get("source_owner") or data.get("owner") or "")
    name=normalize_text(data.get("source_name") or data.get("name") or "")
    if repo_url:
        owner2,name2,repo_url2=canonical_repo_parts(repo_url)
        if owner2 and name2:
            owner=owner or owner2
            name=name or name2
            repo_url=repo_url2
    if not is_official_repo(repo_url=repo_url,owner=owner,name=name):
        raise ValueError("Remote manifest source is not the official emaldos/LOYA-Note repository.")
    version=normalize_semver(data.get("version") or tag_to_version(data.get("source_tag") or data.get("tag_name") or ""), "")
    if not version:
        raise ValueError("Remote manifest version must use X.X.X format.")
    tag=normalize_text(data.get("source_tag") or data.get("tag_name") or version_to_tag(version))
    if tag!=version_to_tag(version):
        raise ValueError("Remote manifest tag does not match the semantic version.")
    package_sha256=normalize_sha256(data.get("package_sha256",""))
    release_id=normalize_text(data.get("release_id") or data.get("id") or "")
    commit_sha=normalize_commit_sha(data.get("commit_sha") or data.get("target_commitish") or "")
    asset_url=normalize_text(data.get("asset_url",""))
    if asset_url and not is_official_package_url(asset_url,owner or OFFICIAL_SOURCE_OWNER,name or OFFICIAL_SOURCE_NAME):
        raise ValueError("Remote manifest package URL is not from the official emaldos/LOYA-Note repository.")
    if not release_id and not commit_sha:
        raise ValueError("Remote manifest must include release_id or commit_sha.")
    manifest=remote_manifest_template(
        version=version,
        release_id=release_id,
        commit_sha=commit_sha,
        package_sha256=package_sha256,
        html_url=data.get("html_url",""),
        asset_url=data.get("asset_url",""),
        published_at=data.get("published_at",""),
    )
    manifest["manifest_version"]=int(data.get("manifest_version") or REMOTE_MANIFEST_VERSION)
    return manifest
