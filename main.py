import os
import sys
import re
import json
import shlex
import shutil
import asyncio
import subprocess
import datetime
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

DB_FILE = "search_history.json"
ENGINE_META_FILE = "engine_meta.json"

def get_engine_meta() -> Dict[str, Any]:
    if os.path.exists(ENGINE_META_FILE):
        try:
            with open(ENGINE_META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and "sites_count" in data:
                    return data
        except Exception:
            pass

    tools_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tools", "maigret"))
    home_db = os.path.expanduser("~/.maigret/data.json")
    repo_db = os.path.join(tools_dir, "maigret", "resources", "data.json")
    db_file = home_db if os.path.exists(home_db) else repo_db

    sites_count = 4990
    if os.path.exists(db_file):
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                db_data = json.load(f)
            sites_dict = db_data.get("sites", {})
            if sites_dict:
                sites_count = len(sites_dict)
        except Exception:
            pass

    commit = "12ec10b"
    commit_date = ""
    try:
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=tools_dir, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            commit = res.stdout.strip()
        res_d = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=short"], cwd=tools_dir, capture_output=True, text=True, check=False)
        if res_d.returncode == 0:
            commit_date = res_d.stdout.strip()
    except Exception:
        pass

    meta = {
        "sites_count": sites_count,
        "sites_count_formatted": f"{sites_count:,}",
        "version": "0.6.5",
        "commit": commit,
        "commit_date": commit_date,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        with open(ENGINE_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
    except Exception:
        pass

    return meta

def check_for_engine_update(timeout: float = 3.0) -> Optional[bool]:
    """
    Quickly checks upstream Git repository for tools/maigret without modifying any files.
    Returns:
        True: Update Detected (new commits on origin/main)
        False: Updated (local repository is up to date)
        None: Offline or check timed out
    """
    tools_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "tools", "maigret"))
    if not os.path.exists(tools_dir):
        return None
    try:
        local_res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tools_dir,
            capture_output=True,
            text=True,
            check=False
        )
        if local_res.returncode != 0 or not local_res.stdout.strip():
            return None
        local_head = local_res.stdout.strip()

        remote_res = subprocess.run(
            ["git", "ls-remote", "origin", "refs/heads/main"],
            cwd=tools_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        if remote_res.returncode != 0 or not remote_res.stdout.strip():
            return None

        remote_head = remote_res.stdout.split()[0].strip()
        return local_head != remote_head
    except Exception:
        return None

class InvestigationJob:
    def __init__(self, job_id: int, username: str, options: Dict[str, Any], initiated_from: str = "terminal"):
        self.id = job_id
        self.username = username
        self.options = options
        self.initiated_from = initiated_from
        self.status = "queued" 
        self.created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.completed_at: Optional[str] = None
        self.found_sites = 0
        self.logs: List[str] = []
        self.reports_generated: List[str] = []
        self.cancel_event = asyncio.Event()
        self.process: Optional[subprocess.Popen] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "initiated_from": self.initiated_from,
            "options": self.options,
            "found_sites": self.found_sites,
            "reports_generated": self.reports_generated
        }

    def serialize_full(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "options": self.options,
            "initiated_from": self.initiated_from,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "found_sites": self.found_sites,
            "logs": self.logs,
            "reports_generated": self.reports_generated
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]):
        job = cls(data["id"], data["username"], data["options"], data["initiated_from"])
        job.status = data.get("status", "queued")
        if job.status == "running":
            job.status = "cancelled"
            job.logs.append("[!] Job was interrupted by server shutdown.")
        job.created_at = data.get("created_at")
        job.completed_at = data.get("completed_at")
        job.found_sites = data.get("found_sites", 0)
        job.logs = data.get("logs", [])
        job.reports_generated = data.get("reports_generated", [])
        return job

jobs_db: Dict[int, InvestigationJob] = {}
job_id_counter = 100
active_websockets: List[WebSocket] = []

def save_db():
    try:
        data = {str(k): v.serialize_full() for k, v in jobs_db.items()}
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving DB: {e}")

def load_db():
    global job_id_counter
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            needs_save = False
            for k, v in data.items():
                job = InvestigationJob.deserialize(v)
                # Auto-heal found_sites if 0 but logs indicate positive returned accounts
                if job.found_sites == 0 and job.logs:
                    c = 0
                    for line in job.logs:
                        m = re.search(r'returned\s+(\d+)\s+accounts', line, re.IGNORECASE)
                        if m:
                            c = int(m.group(1))
                            break
                        if ("[+] " in line or "[++] " in line or "[?] " in line) and "http" in line and "MAIGRET" not in line and "Using sites" not in line and "Donate" not in line:
                            c += 1
                    if c > 0:
                        job.found_sites = c
                        needs_save = True
                jobs_db[int(k)] = job
                if int(k) >= job_id_counter:
                    job_id_counter = int(k) + 1
            if needs_save:
                save_db()
        except Exception as e:
            print(f"Error loading DB: {e}")
    cleanup_orphaned_reports()

def force_remove_path(target_path: str):
    """Force remove file or directory even if locked with read-only or OneDrive attributes on Windows."""
    if not os.path.exists(target_path):
        return

    if os.path.isfile(target_path):
        try:
            if sys.platform == "win32":
                subprocess.run(["attrib", "-r", "-s", "-h", target_path], capture_output=True, timeout=3)
            os.remove(target_path)
            return
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            abs_p = os.path.abspath(target_path)
            subprocess.run(["attrib", "-r", "-s", "-h", f"{abs_p}\\*.*", "/s", "/d"], capture_output=True, timeout=5)
            subprocess.run(["attrib", "-r", "-s", "-h", abs_p], capture_output=True, timeout=5)
            subprocess.run(["cmd", "/c", "rd", "/s", "/q", abs_p], capture_output=True, timeout=10)
            if not os.path.exists(target_path):
                return
        except Exception:
            pass

    def _on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, 0o777)
            func(path)
        except Exception:
            pass

    try:
        shutil.rmtree(target_path, onerror=_on_rm_error)
    except Exception:
        try:
            shutil.rmtree(target_path, ignore_errors=True)
        except Exception:
            pass

def cleanup_orphaned_reports():
    """Remove any reports/job_<id> folders that no longer exist in search_history.json."""
    if not os.path.exists("reports"):
        return
    for item in os.listdir("reports"):
        if item.startswith("job_"):
            jid_str = item[4:]
            if jid_str.isdigit() and int(jid_str) not in jobs_db:
                folder = os.path.join("reports", item)
                if os.path.isdir(folder):
                    force_remove_path(folder)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()

    # Fast startup update indicator check
    try:
        has_update = await asyncio.to_thread(check_for_engine_update, 3.5)
        if has_update:
            print("\nUpdate detected\n")
        else:
            print("\nUp to date\n")
    except Exception:
        print("\nUp to date\n")

    yield
    save_db()

app = FastAPI(title="Maigret OSINT Interactive Dashboard", version="3.7.0", lifespan=lifespan)

# Mount all necessary directories
os.makedirs("static", exist_ok=True)
os.makedirs("reports", exist_ok=True)
os.makedirs("logos", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/reports", StaticFiles(directory="reports"), name="reports")
app.mount("/logos", StaticFiles(directory="logos"), name="logos")

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

async def broadcast_message(message: Dict[str, Any]):
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

def generate_internal_dossier(username: str, job_folder: str):
    html_path = os.path.join(job_folder, f"report_{username}_internal.html")
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Intelligence Dossier: {username}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono&display=swap');
            body {{ font-family: 'Inter', sans-serif; background: #0a0a0c; color: #e2e8f0; margin: 0; padding: 40px; }}
            .container {{ max-width: 900px; margin: auto; background: #121216; padding: 40px; border: 1px solid #B8860B; border-radius: 8px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
            h1 {{ color: #FFD700; border-bottom: 2px solid #272732; padding-bottom: 15px; text-transform: uppercase; letter-spacing: 2px; font-weight: 800; margin-top: 0; }}
            .meta-box {{ background: #18181f; border: 1px solid #272732; padding: 20px; border-radius: 6px; margin-bottom: 30px; display: flex; justify-content: space-between; }}
            .meta-box div {{ display: flex; flex-direction: column; gap: 5px; }}
            .meta-label {{ color: #718096; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }}
            .meta-value {{ color: #FFD700; font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Competitive Intelligence Dossier</h1>
            <div class="meta-box">
                <div>
                    <span class="meta-label">Target Identity</span>
                    <span class="meta-value">{username}</span>
                </div>
                <div style="text-align: right;">
                    <span class="meta-label">Dossier Generated</span>
                    <span class="meta-value">{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
                </div>
            </div>
            <p style="color: #a0aec0;">Generated via Maigret Engine & Custom Internal Format.</p>
        </div>
    </body>
    </html>
    """
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

def resolve_maigret_cmd(cmd_args: List[str]) -> List[str]:
    args = list(cmd_args)
    if args and args[0] == "maigret":
        return [sys.executable, "-m", "maigret"] + args[1:]
    return args

def get_subprocess_env() -> Dict[str, str]:
    env = os.environ.copy()
    tools_maigret = os.path.abspath(os.path.join(os.path.dirname(__file__), "tools", "maigret"))
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{tools_maigret}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = tools_maigret
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env

def extract_target_username(tokens: List[str]) -> Optional[str]:
    flags_with_arg = {
        "-n", "--top", "-t", "--timeout", "--retries", "--folderoutput", "--folder",
        "--idtype", "--tags", "--site", "--use-disabled-sites", "--parse",
        "--cookie-jar-file", "--proxy", "--tor-proxy", "--i2p-proxy", "--db"
    }
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in flags_with_arg:
            skip_next = True
            continue
        if not token.startswith("-"):
            return token
    return None

def is_informational_maigret_cmd(tokens: List[str]) -> bool:
    info_flags = {"--help", "-h", "--version", "-V", "--list-sites", "--stats", "--self-check"}
    if len(tokens) <= 1:
        return True
    if any(t in info_flags for t in tokens):
        return True
    if extract_target_username(tokens) is None:
        return True
    return False

async def run_direct_cli_command(cmd_args: List[str], on_complete=None):
    proc = None
    try:
        resolved_cmd = resolve_maigret_cmd(cmd_args)
        proc = subprocess.Popen(
            resolved_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=get_subprocess_env()
        )
        while True:
            line_bytes = await asyncio.to_thread(proc.stdout.readline)
            if not line_bytes:
                break
            clean_line = ANSI_ESCAPE.sub('', line_bytes.decode('utf-8', errors='replace')).rstrip('\r\n')
            if clean_line:
                await broadcast_message({"type": "terminal_log", "job_id": None, "source": "terminal", "line": clean_line})
        await asyncio.to_thread(proc.wait)
        if on_complete:
            try:
                res = on_complete()
                if asyncio.iscoroutine(res):
                    await res
            except Exception as cb_err:
                print(f"Error in on_complete callback: {cb_err}")
    except Exception as e:
        await broadcast_message({"type": "terminal_log", "job_id": None, "source": "terminal", "line": f"[!] CLI Error: {repr(e)}"})
    finally:
        if proc and proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass

async def run_maigret_subprocess(job: InvestigationJob, cmd_args: List[str]):
    job.status = "running"
    save_db()
    await broadcast_message({"type": "job_status", "job": job.to_dict()})
    
    # Isolated unique directory per investigation job
    job_folder = os.path.join("reports", f"job_{job.id}")
    os.makedirs(job_folder, exist_ok=True)
    start_timestamp = datetime.datetime.now().timestamp()
    
    log_header = f"$ {' '.join(cmd_args)}"
    job.logs.append(log_header)
    await broadcast_message({"type": "terminal_log", "job_id": job.id, "source": job.initiated_from, "line": log_header})

    try:
        resolved_cmd = resolve_maigret_cmd(cmd_args)
        job.process = subprocess.Popen(
            resolved_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=get_subprocess_env()
        )

        while True:
            if job.cancel_event.is_set():
                if job.process and job.process.poll() is None:
                    try:
                        job.process.terminate()
                    except Exception:
                        pass
                job.status = "cancelled"
                cancel_msg = f"\n[!] Investigation #{job.id} halted by operator."
                job.logs.append(cancel_msg)
                await broadcast_message({"type": "terminal_log", "job_id": job.id, "source": job.initiated_from, "line": cancel_msg})
                break

            line_bytes = await asyncio.to_thread(job.process.stdout.readline)
            if not line_bytes:
                break
            
            raw_decoded = line_bytes.decode('utf-8', errors='replace').rstrip('\r\n')
            clean_line = ANSI_ESCAPE.sub('', raw_decoded)
            if clean_line:
                # Handle progress bar carriage returns mixed with match notifications
                # e.g. "\rSearching | ... \r\r[+] Twitter: https://..."
                segments = [s.strip() for s in clean_line.split('\r') if s.strip()]
                
                # Check for "Search by username <user> returned <N> accounts."
                m_sum = re.search(r'returned\s+(\d+)\s+accounts', clean_line, re.IGNORECASE)
                if m_sum:
                    job.found_sites = int(m_sum.group(1))

                has_match = False
                for seg in segments:
                    is_match = (
                        (seg.startswith("[+] ") or seg.startswith("[++] ") or seg.startswith("[?] "))
                        and "http" in seg
                        and "MAIGRET" not in seg
                        and "Using sites" not in seg
                        and "Donate" not in seg
                    ) or ("FOUND" in seg and "NOT FOUND" not in seg and "Starting" not in seg)

                    if is_match:
                        has_match = True
                        if not m_sum:
                            job.found_sites += 1
                        job.logs.append(seg)
                        await broadcast_message({"type": "terminal_log", "job_id": job.id, "source": job.initiated_from, "line": seg})
                
                # If no match in this line, keep the latest output / status update
                if not has_match:
                    latest = segments[-1] if segments else clean_line
                    job.logs.append(latest)
                    await broadcast_message({"type": "terminal_log", "job_id": job.id, "source": job.initiated_from, "line": latest})

        await asyncio.to_thread(job.process.wait)
        if job.status != "cancelled":
            job.status = "completed"
            
        job.completed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Re-verify and reconcile found_sites against logs and report summary
        count_from_summary = None
        count_from_matches = 0
        for l in job.logs:
            m = re.search(r'returned\s+(\d+)\s+accounts', l, re.IGNORECASE)
            if m:
                count_from_summary = int(m.group(1))
            elif (l.startswith("[+] ") or l.startswith("[++] ") or l.startswith("[?] ")) and "http" in l and "MAIGRET" not in l and "Using sites" not in l:
                count_from_matches += 1

        if count_from_summary is not None:
            job.found_sites = count_from_summary
        elif count_from_matches > job.found_sites:
            job.found_sites = count_from_matches
        
        # Discover and move generated reports from root reports/ into job_folder
        safe_uname = job.username.lower().replace('/', '_')
        if os.path.exists("reports"):
            for fname in os.listdir("reports"):
                fpath = os.path.join("reports", fname)
                if os.path.isfile(fpath) and fname.lower().startswith(f"report_{safe_uname}"):
                    try:
                        mtime = os.path.getmtime(fpath)
                        if mtime >= start_timestamp - 5:
                            dst = os.path.join(job_folder, fname)
                            shutil.copy2(fpath, dst)
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
                    except Exception:
                        pass

        # Create aliasing in job_folder so all standard format requests resolve without 404
        if os.path.exists(job_folder):
            for fname in os.listdir(job_folder):
                fl = fname.lower()
                # HTML aliasing: report_user_plain.html -> report_user.html
                if "_plain.html" in fl:
                    alias = fname.replace("_plain.html", ".html")
                    alias_p = os.path.join(job_folder, alias)
                    if not os.path.exists(alias_p):
                        try:
                            shutil.copy2(os.path.join(job_folder, fname), alias_p)
                        except Exception:
                            pass
                # JSON aliasing: report_user_simple.json / _ndjson.json -> report_user.json
                if "_simple.json" in fl:
                    alias = fname.replace("_simple.json", ".json")
                    alias_p = os.path.join(job_folder, alias)
                    if not os.path.exists(alias_p):
                        try:
                            shutil.copy2(os.path.join(job_folder, fname), alias_p)
                        except Exception:
                            pass
                elif "_ndjson.json" in fl:
                    alias = fname.replace("_ndjson.json", ".json")
                    alias_p = os.path.join(job_folder, alias)
                    if not os.path.exists(alias_p):
                        try:
                            shutil.copy2(os.path.join(job_folder, fname), alias_p)
                        except Exception:
                            pass

        if job.options.get("pdf_style") == "internal" or job.options.get("internal_format"):
            generate_internal_dossier(job.username, job_folder)

        # Index all reports present in job_folder into job.reports_generated
        detected_types = set()
        if os.path.exists(job_folder):
            for fname in os.listdir(job_folder):
                fl = fname.lower()
                if not fl.startswith(f"report_{safe_uname}"):
                    continue
                if fl.endswith(".html"):
                    if "_internal" in fl:
                        detected_types.add("internal_html")
                    elif "_graph" in fl:
                        detected_types.add("graph")
                    else:
                        detected_types.add("html")
                elif fl.endswith(".pdf"):
                    detected_types.add("pdf")
                elif fl.endswith(".json"):
                    detected_types.add("json")
                elif fl.endswith(".csv"):
                    detected_types.add("csv")
                elif fl.endswith(".txt"):
                    detected_types.add("txt")
                elif fl.endswith(".md"):
                    detected_types.add("md")
                elif fl.endswith(".xmind"):
                    detected_types.add("xmind")

        job.reports_generated = sorted(list(detected_types))

        completion_msg = f"\n[✓] Job #{job.id} concluded. {job.found_sites} returned accounts verified."
        job.logs.append(completion_msg)
        await broadcast_message({"type": "terminal_log", "job_id": job.id, "source": job.initiated_from, "line": completion_msg})
        save_db()
        await broadcast_message({"type": "job_status", "job": job.to_dict()})

    except Exception as e:
        job.status = "failed"
        err_msg = f"[!] Core Execution Error: {repr(e)}"
        job.logs.append(err_msg)
        save_db()
        await broadcast_message({"type": "terminal_log", "job_id": job.id, "source": job.initiated_from, "line": err_msg})
        await broadcast_message({"type": "job_status", "job": job.to_dict()})

class GUIStartRequest(BaseModel):
    username: str
    tokens: Optional[List[str]] = None
    all_sites: Optional[bool] = False
    use_top: Optional[bool] = False
    top_sites: Optional[int] = None
    use_idtype: Optional[bool] = False
    id_type: Optional[str] = "username"
    permute: Optional[bool] = False
    cloudflare_bypass: Optional[bool] = False
    no_recursion: Optional[bool] = False
    no_progressbar: Optional[bool] = False
    use_timeout: Optional[bool] = False
    timeout: Optional[int] = None
    use_tags: Optional[bool] = False
    tags: Optional[List[str]] = []
    report_html: Optional[bool] = False
    report_pdf: Optional[bool] = False
    pdf_style: Optional[str] = "default"
    report_json: Optional[bool] = False
    report_csv: Optional[bool] = False
    report_txt: Optional[bool] = False
    report_md: Optional[bool] = False
    report_graph: Optional[bool] = False
    report_xmind: Optional[bool] = False
    print_mode: Optional[str] = "long"

class CommandRequest(BaseModel):
    command: str

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("logos", "maigret logo shield.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=204)

@app.get("/")
async def serve_index():
    # Return index.html from the 'static' folder
    return FileResponse(os.path.join("static", "index.html"))

@app.get("/api/engine/info")
async def get_engine_info():
    return get_engine_meta()

@app.get("/api/overview")
async def get_overview():
    meta = get_engine_meta()
    return {
        "total_searches": len(jobs_db),
        "active_tasks": sum(1 for j in jobs_db.values() if j.status == "running"),
        "total_found": sum(j.found_sites for j in jobs_db.values()),
        "supported_sites": meta.get("sites_count", 4990),
        "engine_meta": meta
    }

@app.get("/api/history")
async def get_history():
    return [job.to_dict() for job in sorted(jobs_db.values(), key=lambda j: j.id, reverse=True)]

@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: int):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    job = jobs_db[job_id]
    data = job.to_dict()
    data["logs"] = job.logs
    return data

@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: int):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    job = jobs_db[job_id]
    if job.status == "running":
        job.cancel_event.set()
        if job.process and job.process.poll() is None:
            try:
                job.process.terminate()
            except Exception:
                pass
        save_db()
        return {"status": "cancelling"}
    return {"status": "inactive"}

def remove_investigation_and_reports(job_id: int) -> bool:
    found = False

    # 1. Terminate running process if any and remove from jobs_db
    if job_id in jobs_db:
        found = True
        job = jobs_db[job_id]
        if job.status == "running":
            job.cancel_event.set()
            if job.process and job.process.poll() is None:
                try:
                    job.process.terminate()
                except Exception:
                    pass

        safe_uname = job.username.lower().replace('/', '_')
        other_jobs = [
            j for jid, j in jobs_db.items()
            if jid != job_id and j.username.lower().replace('/', '_') == safe_uname
        ]

        # Clean up loose reports directly under reports/ if no other search targets this username
        if not other_jobs and os.path.exists("reports"):
            for fname in os.listdir("reports"):
                if fname.lower().startswith(f"report_{safe_uname}"):
                    fpath = os.path.join("reports", fname)
                    if os.path.isfile(fpath):
                        force_remove_path(fpath)

        del jobs_db[job_id]
        save_db()

    # 2. Recursively delete the associated reports folder (reports/job_<job_id>)
    job_folder = os.path.join("reports", f"job_{job_id}")
    if os.path.exists(job_folder):
        found = True
        force_remove_path(job_folder)

    return found

@app.delete("/api/jobs/{job_id}")
@app.delete("/api/reports/{job_id}")
async def delete_job(job_id: int):
    if remove_investigation_and_reports(job_id):
        await broadcast_message({"type": "job_status", "job_id": job_id, "action": "deleted"})
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=404, detail="Investigation not found.")

@app.get("/html")
async def cloudflare_bypass_html_proxy(url: str, retries: int = 1):
    """
    Built-in proxy resolver for Maigret's Cloudflare bypass fallback.
    Uses curl_cffi with Chrome TLS/HTTP2 fingerprint impersonation to retrieve
    protected pages directly without requiring an external Docker solver.
    """
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome124") as s:
            resp = await s.get(url, timeout=20)
            return Response(content=resp.text, status_code=resp.status_code, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bypass fetch error: {str(e)}")

@app.post("/api/search")
async def start_gui_search(req: GUIStartRequest):
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    
    # If exact tokens were supplied from frontend command builder, use them
    if req.tokens and len(req.tokens) >= 2 and req.tokens[0] == "maigret" and req.tokens[1] == username:
        cmd_args = list(req.tokens)
    else:
        # Construct strictly from user-specified options only
        cmd_args = ["maigret", username]
        if req.all_sites:
            cmd_args.append("-a")
        elif req.use_top and req.top_sites:
            max_sites = get_engine_meta().get("sites_count", 4990)
            cmd_args.extend(["--top-sites", str(min(req.top_sites, max_sites))])
        
        if req.use_idtype and req.id_type and req.id_type != "username":
            cmd_args.extend(["--id-type", req.id_type])
        
        if req.permute:
            cmd_args.append("--permute")
        if req.cloudflare_bypass:
            cmd_args.append("--cloudflare-bypass")
        if req.no_recursion:
            cmd_args.append("--no-recursion")
        if req.no_progressbar:
            cmd_args.append("--no-progressbar")
        
        if req.use_timeout and req.timeout:
            cmd_args.extend(["--timeout", str(req.timeout)])
        
        if req.use_tags and req.tags:
            cleaned_tags = [t.strip() for t in req.tags if t.strip()]
            if cleaned_tags:
                cmd_args.extend(["--tags", ",".join(cleaned_tags)])
        
        if req.report_html:
            cmd_args.append("--html")
        if req.report_pdf:
            cmd_args.append("--pdf")
        if req.report_json:
            cmd_args.extend(["--json", "simple"])
        if req.report_csv:
            cmd_args.append("--csv")
        if req.report_txt:
            cmd_args.append("--txt")
        if req.report_md:
            cmd_args.append("--md")
        if req.report_graph:
            cmd_args.append("--graph")
        if req.report_xmind:
            cmd_args.append("--xmind")

    global job_id_counter
    job_id_counter += 1
    new_job = InvestigationJob(job_id_counter, username, req.model_dump(), "gui")
    jobs_db[new_job.id] = new_job
    save_db()
    
    asyncio.create_task(run_maigret_subprocess(new_job, cmd_args))
    return {"status": "started", "job_id": new_job.id, "job": new_job.to_dict()}

@app.post("/api/terminal/execute")
async def execute_terminal_command(req: CommandRequest):
    raw_cmd = req.command.strip()
    if not raw_cmd:
        return {"output": ""}

    tokens = shlex.split(raw_cmd)
    primary = tokens[0].lower()

    if primary in {"rm", "del", "powershell", "cmd", "cmd.exe", "python", "python3", "bash", "sh", "zsh", "sudo", "exec", "curl", "wget", "kill"}:
        return {"output": f"[!] Access Denied: Command '{primary}' is blocked.\n"}

    if primary == "help":
        return {
            "output": (
                "MAIGRET DASHBOARD INTERACTIVE CONSOLE\n"
                "====================================================\n"
                "  maigret <user> [options]       Execute dossier investigation\n"
                "  maigret --help / -h            Display all native Maigret CLI flags and options\n"
                "  maigret --version              Display Maigret engine version\n"
                "  maigret --list-sites           List all supported OSINT platforms\n"
                "  update                         Check and apply updates to Maigret engine\n"
                "  cancel                         Halt active search\n"
                "  investigations / jobs          Display recent dossier investigations\n"
                "  open <id>                      Navigate GUI to investigation #<id>\n"
                "  delete <id>                    Permanently remove search from history and its reports\n"
                "  status                         Show running job status\n"
                "  clear                          Clear terminal display\n"
            )
        }

    if primary in ("investigations", "jobs"):
        if not jobs_db:
            return {"output": "No investigations found.\n"}
        lines = [f"{'ID':<6} {'USERNAME':<18} {'STATUS':<12} {'FOUND':<6} {'CREATED':<20}"]
        lines.append("-" * 65)
        for j in sorted(jobs_db.values(), key=lambda x: x.id, reverse=True)[:15]:
            lines.append(f"{j.id:<6} {j.username:<18} {j.status.upper():<12} {j.found_sites:<6} {j.created_at:<20}")
        return {"output": "\n".join(lines) + "\n"}

    if primary == "status":
        running_jobs = [j for j in jobs_db.values() if j.status == "running"]
        status_txt = f"Engine Status: ONLINE\nActive Jobs: {len(running_jobs)}\n"
        return {"output": status_txt}

    if primary == "open":
        if len(tokens) < 2 or not tokens[1].isdigit():
            return {"output": "Usage: open <id>\n"}
        target_id = int(tokens[1])
        if target_id not in jobs_db:
            return {"output": f"Error: Investigation #{target_id} does not exist.\n"}
        return {"output": f"[✓] Navigating to #{target_id}...\n", "action": "open_investigation", "job_id": target_id}

    if primary in ("delete", "remove"):
        if len(tokens) < 2 or not tokens[1].isdigit():
            return {"output": "Usage: delete <id>\n"}
        target_id = int(tokens[1])
        if target_id not in jobs_db and not os.path.exists(os.path.join("reports", f"job_{target_id}")):
            return {"output": f"Error: Investigation #{target_id} does not exist.\n"}
        remove_investigation_and_reports(target_id)
        await broadcast_message({"type": "job_status", "job_id": target_id, "action": "deleted"})
        return {"output": f"[✓] Investigation #{target_id} and all associated reports deleted.\n"}

    if primary == "cancel":
        for j in jobs_db.values():
            if j.status == "running":
                j.cancel_event.set()
                if j.process and j.process.poll() is None:
                    try:
                        j.process.terminate()
                    except Exception:
                        pass
        save_db()
        return {"output": f"[*] Cancellation signal sent.\n"}

    if primary == "update":
        update_script = os.path.join(os.path.dirname(__file__), "updates", "update.py")

        async def on_update_done():
            meta = get_engine_meta()
            await broadcast_message({"type": "engine_info_updated", "data": meta})
            await broadcast_message({
                "type": "terminal_log",
                "job_id": None,
                "line": f"[+] UI Synchronized: Application live updated with {meta.get('sites_count_formatted', '')} supported sites (v{meta.get('version', '')} - {meta.get('commit', '')}).\n"
            })

        asyncio.create_task(run_direct_cli_command([sys.executable, update_script] + tokens[1:], on_complete=on_update_done))
        return {"output": ""}

    if primary == "maigret":
        if is_informational_maigret_cmd(tokens):
            asyncio.create_task(run_direct_cli_command(tokens))
            return {"output": ""}

        target_user = extract_target_username(tokens)
        if not target_user:
            asyncio.create_task(run_direct_cli_command(tokens))
            return {"output": ""}

        global job_id_counter
        job_id_counter += 1
        new_job = InvestigationJob(job_id_counter, target_user, {"raw_cmd": raw_cmd}, "terminal")
        jobs_db[new_job.id] = new_job
        save_db()

        # Execute exactly what user typed
        asyncio.create_task(run_maigret_subprocess(new_job, list(tokens)))
        return {"output": f"[+] Investigation #{new_job.id} queued for target '{target_user}'. Engine starting...\n", "job_id": new_job.id}

    return {"output": f"Unknown command: '{primary}'. Type 'help' or 'maigret --help'.\n"}

@app.websocket("/ws/terminal")
async def websocket_terminal_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)