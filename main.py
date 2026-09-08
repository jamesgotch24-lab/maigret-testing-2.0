import os
import sys
import re
import json
import shlex
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
            for k, v in data.items():
                job = InvestigationJob.deserialize(v)
                jobs_db[int(k)] = job
                if int(k) >= job_id_counter:
                    job_id_counter = int(k) + 1
        except Exception as e:
            print(f"Error loading DB: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_db()

    # Fast startup update indicator check
    try:
        has_update = await asyncio.to_thread(check_for_engine_update, 3.5)
        if has_update:
            print("\nUpdate Detected\n")
        else:
            print("\nUpdated\n")
    except Exception:
        print("\nUpdated\n")

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
                await broadcast_message({"type": "terminal_log", "job_id": None, "line": clean_line})
        await asyncio.to_thread(proc.wait)
        if on_complete:
            try:
                res = on_complete()
                if asyncio.iscoroutine(res):
                    await res
            except Exception as cb_err:
                print(f"Error in on_complete callback: {cb_err}")
    except Exception as e:
        await broadcast_message({"type": "terminal_log", "job_id": None, "line": f"[!] CLI Error: {repr(e)}"})
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
    
    if "--folder" not in cmd_args and "--folderoutput" not in cmd_args:
        cmd_args.extend(["--folderoutput", job_folder])
        
    log_header = f"[*] Engine Executing: {' '.join(cmd_args)}"
    job.logs.append(log_header)
    await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": log_header})

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
                await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": cancel_msg})
                break

            line_bytes = await asyncio.to_thread(job.process.stdout.readline)
            if not line_bytes:
                break
            
            clean_line = ANSI_ESCAPE.sub('', line_bytes.decode('utf-8', errors='replace')).rstrip('\r\n')
            if clean_line:
                job.logs.append(clean_line)
                if "FOUND" in clean_line and "NOT FOUND" not in clean_line and "Starting" not in clean_line:
                    job.found_sites += 1
                await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": clean_line})

        await asyncio.to_thread(job.process.wait)
        if job.status != "cancelled":
            job.status = "completed"
            
        job.completed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if os.path.exists(job_folder):
            for fname in os.listdir(job_folder):
                ext = fname.split(".")[-1].lower()
                if ext in ["html", "pdf", "json", "csv", "txt", "xmind", "md"]:
                    if ext not in job.reports_generated:
                        job.reports_generated.append(ext)

        if job.options.get("pdf_style") == "internal" or job.options.get("internal_format"):
            generate_internal_dossier(job.username, job_folder)
            if "internal_html" not in job.reports_generated:
                job.reports_generated.append("internal_html")

        completion_msg = f"\n[✓] Job #{job.id} concluded. {job.found_sites} returned accounts verified."
        job.logs.append(completion_msg)
        await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": completion_msg})
        save_db()
        await broadcast_message({"type": "job_status", "job": job.to_dict()})

    except Exception as e:
        job.status = "failed"
        err_msg = f"[!] Core Execution Error: {repr(e)}"
        job.logs.append(err_msg)
        save_db()
        await broadcast_message({"type": "terminal_log", "job_id": job.id, "line": err_msg})
        await broadcast_message({"type": "job_status", "job": job.to_dict()})

class GUIStartRequest(BaseModel):
    username: str
    tags: Optional[List[str]] = []
    timeout: Optional[int] = 15
    top_sites: Optional[int] = 500
    all_sites: Optional[bool] = False
    permute: Optional[bool] = False
    cloudflare_bypass: Optional[bool] = False
    id_type: Optional[str] = "username"
    print_mode: Optional[str] = "long"
    report_html: Optional[bool] = True
    report_pdf: Optional[bool] = True
    pdf_style: Optional[str] = "default"
    report_json: Optional[bool] = False
    report_csv: Optional[bool] = False
    report_txt: Optional[bool] = False

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

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    if job_id in jobs_db:
        del jobs_db[job_id]
        save_db()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Investigation not found.")

@app.post("/api/search")
async def start_gui_search(req: GUIStartRequest):
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    
    max_sites = get_engine_meta().get("sites_count", 4990)
    cmd_args = ["maigret", username]
    if req.all_sites:
        cmd_args.append("--all-sites")
    else:
        top_val = min(max(1, req.top_sites or 500), max_sites)
        cmd_args.extend(["--top-sites", str(top_val)])
    
    if req.tags:
        cleaned_tags = [t.strip() for t in req.tags if t.strip()]
        if cleaned_tags:
            cmd_args.extend(["--tags", ",".join(cleaned_tags)])
    
    cmd_args.extend(["--timeout", str(req.timeout)])
    if req.id_type and req.id_type != "username":
        cmd_args.extend(["--id-type", req.id_type])
    
    if req.permute: cmd_args.append("--permute")
    if req.cloudflare_bypass: cmd_args.append("--cloudflare-bypass")
    if req.report_html: cmd_args.append("--html")
    if req.report_pdf: cmd_args.append("--pdf")
    if req.report_json: cmd_args.extend(["--json", "simple"])
    if req.report_csv: cmd_args.append("--csv")
    if req.report_txt: cmd_args.append("--txt")

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

        # If user did not specify any report flag, default to generating HTML report
        cmd_with_reports = list(tokens)
        has_report_flag = any(f in cmd_with_reports for f in ["--html", "--pdf", "--json", "--csv", "--txt", "-a"])
        if not has_report_flag:
            cmd_with_reports.append("--html")

        asyncio.create_task(run_maigret_subprocess(new_job, cmd_with_reports))
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