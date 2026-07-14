"""
FastAPI backend for HemaGuide.
Provides REST API and WebSocket endpoints for document processing.
"""
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
QUERY_INPUT_DIR = PROJECT_ROOT / 'query_input'
EXTRACTED_DIR = PROJECT_ROOT / 'extracted_data' / 'query_input'
RESULTS_DIR = PROJECT_ROOT / 'results' / 'agent_decisions'
KB_DIR = PROJECT_ROOT / 'kb_storage' / 'chroma_db'
VENV_PYTHON = Path(os.environ.get('HEMAGUIDE_PYTHON') or sys.executable)
FLOWCHART_SOURCES = PROJECT_ROOT / 'data' / 'onkopedia.json'
ONKOPEDIA_URL = "https://www.onkopedia.com/de/onkopedia/guidelines/{slug}/@@guideline/html/index.html"
GERMAN_MONTHS = {
    'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
    'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
    'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
}

app = FastAPI(title="HemaGuide API", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """WebSocket connection manager for real-time updates."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        await websocket.accept()
        # Swap first so subsequent send_status calls reach the new socket; then
        # close the old one out-of-band. disconnect() is identity-keyed so
        # the old socket's WebSocketDisconnect handler can't evict the new one.
        old = self.active_connections.get(job_id)
        self.active_connections[job_id] = websocket
        if old is not None:
            try:
                await old.close()
            except Exception:
                pass
        logger.info(f"WebSocket connected for job {job_id}")

    def disconnect(self, job_id: str, websocket: Optional[WebSocket] = None):
        current = self.active_connections.get(job_id)
        if current is not None and (websocket is None or current is websocket):
            del self.active_connections[job_id]
            logger.info(f"WebSocket disconnected for job {job_id}")

    async def send_status(self, job_id: str, status: dict):
        if job_id in self.active_connections:
            try:
                await self.active_connections[job_id].send_json(status)
            except Exception as e:
                logger.warning(f"Failed to send status to {job_id}: {e}")


manager = ConnectionManager()

# Job tracking
jobs: Dict[str, dict] = {}
jobs_lock = asyncio.Lock()


# --- Pydantic Models ---

class ProcessRequest(BaseModel):
    llm_mode: str = "ollama-local"
    decision_model: str = "qwen3:8b"
    files: List[str]
    use_flowchart: bool = True
    use_historical_cases: bool = True
    use_pubmed: bool = True
    use_conferences: bool = True


class UploadResponse(BaseModel):
    filename: str
    path: str


class JobResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    progress: Optional[int] = None
    current_case: Optional[int] = None
    total_cases: Optional[int] = None
    logs: Optional[List[str]] = None
    case_results: Optional[List[dict]] = None
    result: Optional[dict] = None
    files: Optional[List[str]] = None
    extraction_previews: Optional[List[dict]] = None


def _parse_json_list(value) -> list:
    if isinstance(value, list):
        return value
    if not value or value == "nicht vorhanden":
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _load_extraction_previews(files: List[str]) -> List[dict]:
    previews = []
    for filename in files:
        path = EXTRACTED_DIR / f"{Path(filename).stem}.json"
        if not path.exists():
            continue
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        sections = data.get("sections", {})
        variants = _parse_json_list(sections.get("mol_info"))
        fish = _parse_json_list(sections.get("mol_fish"))
        previews.append({
            "filename": filename,
            "diagnosis": sections.get("main_diagnosis") or sections.get("entity") or "Not identified",
            "entity": sections.get("entity", "Not identified"),
            "age": sections.get("age", "Not provided"),
            "ecog": sections.get("ECOG", "Not provided"),
            "tumorboard_type": sections.get("tumorboard_type", "Not identified"),
            "is_molecular": bool(sections.get("is_mol_tb")),
            "predicted_mode": "MOLECULAR" if sections.get("is_mol_tb") else "Automatic routing",
            "variants": [
                {
                    "gene": item.get("gene", "Unknown"),
                    "aa_change": item.get("aa_change") or item.get("variant") or "Not provided",
                    "vaf": item.get("vaf"),
                }
                for item in variants if isinstance(item, dict)
            ],
            "fish_count": len(fish),
        })
    return previews


def _friendly_error(error: Exception, phase: str) -> str:
    text = str(error)
    if isinstance(error, FileNotFoundError) or "No such file or directory" in text:
        return f"{phase} could not start because a required executable or file was not found. Check the Python environment and project paths."
    if "Connection" in text or "connect" in text.lower():
        return f"{phase} could not connect to the configured model service. Confirm that Ollama is running on localhost:11434."
    if "exit code" in text:
        return f"{phase} failed. Open Technical logs below for the model or extraction error."
    return f"{phase} failed: {text}"


class FlowchartStatus(BaseModel):
    slug: str
    name: str
    local_stand: Optional[str]
    online_stand: Optional[str]
    onkopedia_url: str
    status: str  # "current" | "outdated" | "unknown" | "error"
    message: Optional[str] = None


class FlowchartStatusResponse(BaseModel):
    checked_at: str
    flowcharts: List[FlowchartStatus]


# --- Background Processing ---

async def update_job_status(job_id: str, status: str, message: str, progress: int):
    """Update job status and notify WebSocket."""
    async with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = status
            jobs[job_id]["message"] = message
            jobs[job_id]["progress"] = progress
            current_case = jobs[job_id].get("current_case", 0)
            total_cases = jobs[job_id].get("total_cases", 0)
        else:
            current_case = 0
            total_cases = 0

    await manager.send_status(job_id, {
        "status": status,
        "message": message,
        "progress": progress,
        "current_case": current_case,
        "total_cases": total_cases,
    })


async def send_case_result(job_id: str, case_stem: str):
    """Load and send a completed case result via WebSocket."""
    job = jobs[job_id]
    result_file = RESULTS_DIR / f"{case_stem}_agent.json"

    if result_file.exists():
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)

            case_result = {
                "case_id": case_stem,
                "case_name": case_stem,
                "mode": result_data.get("mode", "GUIDELINE"),
                "effective_mode": result_data.get("effective_mode", result_data.get("mode", "GUIDELINE")),
                "synthesis_failed": result_data.get("synthesis_failed", False),
                "synthesis_failure_reason": result_data.get("synthesis_failure_reason"),
                "konferenzbeschluss": result_data.get("konferenzbeschluss", ""),
                "begründung": result_data.get("begründung", ""),
                "supplemental_reason": result_data.get("supplemental_reason", ""),
                "evidence_hits": result_data.get("evidence_hits", {}),
                "completed_at": datetime.now().isoformat(),
            }

            job["case_results"].append(case_result)

            await manager.send_status(job_id, {
                "status": job["status"],
                "message": f"Fall abgeschlossen: {case_stem}",
                "progress": job["progress"],
                "current_case": job["current_case"],
                "total_cases": job["total_cases"],
                "case_result": case_result,
            })

            logger.info(f"Sent interim result for {case_stem}")
        except Exception as e:
            logger.error(f"Failed to load result for {case_stem}: {e}")


async def stream_process_output(proc, job_id: str, phase: str):
    """Stream stdout/stderr from subprocess and parse for progress updates."""
    job = jobs[job_id]
    case_pattern = re.compile(r'\[(\d+)/(\d+)\]')
    saved_pattern = re.compile(r'Saved: (.+)_agent\.json')

    async def read_stream(stream):
        while True:
            line = await stream.readline()
            if not line:
                break

            decoded = line.decode('utf-8', errors='replace').strip()
            if not decoded:
                continue

            # Add to logs (keep last 100 lines)
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {decoded}"
            job["logs"].append(log_entry)
            job["logs"] = job["logs"][-100:]

            # Parse case progress [1/5] pattern. Skip total==0 — the regex is
            # non-anchored and unrelated tool lines like "[1/0] candidates" can
            # match; dividing by zero here would kill the reader and hang the job.
            match = case_pattern.search(decoded)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                if total > 0:
                    job["current_case"] = current
                    job["total_cases"] = total
                    # Progress: extraction 0-40%, agent 40-95%
                    if phase == "extraction":
                        progress = int(10 + (current / total) * 30)
                    else:
                        progress = int(40 + (current / total) * 55)
                    job["progress"] = progress

            # Check if a case was saved (agent phase only)
            if phase == "agent":
                saved_match = saved_pattern.search(decoded)
                if saved_match:
                    case_stem = saved_match.group(1)
                    await send_case_result(job_id, case_stem)

            # Send WebSocket update
            await manager.send_status(job_id, {
                "status": job["status"],
                "message": decoded[:100],
                "progress": job["progress"],
                "current_case": job["current_case"],
                "total_cases": job["total_cases"],
                "log": log_entry,
            })

    # Read both streams concurrently
    await asyncio.gather(
        read_stream(proc.stdout),
        read_stream(proc.stderr)
    )


async def process_documents(job_id: str):
    """Background task to run extraction and agent with streaming output."""
    job = jobs[job_id]
    config = job["config"]

    phase = "Document extraction"
    try:
        # Step 1: Extraction
        await update_job_status(job_id, "extracting", "Dokumentenextraktion...", 10)

        extraction_cmd = [
            str(VENV_PYTHON), "-u", "process_query_input.py",
            "--llm-mode", config["llm_mode"],
            "--extraction-model", config["decision_model"],
        ]

        logger.info(f"Running extraction: {' '.join(extraction_cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *extraction_cmd,
            cwd=PROJECT_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await stream_process_output(proc, job_id, "extraction")
        await proc.wait()

        if proc.returncode is None or proc.returncode != 0:
            raise Exception(f"Extraction failed with exit code {proc.returncode} - check logs")

        previews = _load_extraction_previews(job["files"])
        if not previews:
            raise Exception("Extraction completed but no structured case preview was produced")
        job["extraction_previews"] = previews
        await update_job_status(job_id, "routing", "Extraction complete; starting agent automatically", 40)
        await manager.send_status(job_id, {
            "status": "routing",
            "message": "Extraction complete; starting agent automatically",
            "progress": 40,
            "current_case": 0,
            "total_cases": job["total_cases"],
            "extraction_previews": previews,
        })

        # Step 2: Agent processing
        phase = "Agent decision generation"
        if not KB_DIR.exists():
            logger.warning("Knowledge base not found - similar case retrieval will be skipped")

        await update_job_status(job_id, "routing", "Agent-Routing...", 45)

        agent_cmd = [
            str(VENV_PYTHON), "-u", "agent.py",
            "--llm-mode", config["llm_mode"],
            "--decision-model", config["decision_model"],
        ]
        if not config["use_flowchart"]:
            agent_cmd.append("--ignore-flowchart")
        if not config["use_historical_cases"]:
            agent_cmd.append("--disable-case-retrieval")
        if not config["use_pubmed"]:
            agent_cmd.append("--disable-pubmed-retrieval")
        if not config["use_conferences"]:
            agent_cmd.append("--disable-conference-retrieval")

        logger.info(f"Running agent: {' '.join(agent_cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *agent_cmd,
            cwd=PROJECT_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await update_job_status(job_id, "generating", "Entscheidungen werden generiert...", 50)

        await stream_process_output(proc, job_id, "agent")
        await proc.wait()

        if proc.returncode is None or proc.returncode != 0:
            raise Exception(f"Agent failed with exit code {proc.returncode} - check logs")

        # Step 3: Collect results
        await update_job_status(job_id, "complete", "Verarbeitung abgeschlossen", 100)

        results = []
        for filename in job["files"]:
            stem = Path(filename).stem
            result_file = RESULTS_DIR / f"{stem}_agent.json"
            if result_file.exists():
                with open(result_file, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                    result_data["source_file"] = filename
                    results.append(result_data)
                logger.info(f"Loaded result for {filename}")
            else:
                logger.warning(f"Result file not found: {result_file}")

        if not results:
            raise Exception("No results produced - check logs for errors")

        job["result"] = results[0] if len(results) == 1 else results
        job["status"] = "complete"

        await manager.send_status(job_id, {
            "status": "complete",
            "message": "Verarbeitung abgeschlossen",
            "progress": 100,
            "current_case": job["total_cases"],
            "total_cases": job["total_cases"],
            "result": job["result"],
        })

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        friendly_message = _friendly_error(e, phase)
        job["status"] = "error"
        job["message"] = friendly_message
        await manager.send_status(job_id, {
            "status": "error",
            "message": friendly_message,
            "technical_message": str(e),
            "logs": job["logs"][-10:],
        })


# --- Flowchart Currency Check ---

def _fetch_onkopedia_stand(slug: str) -> Optional[str]:
    """Fetch the 'Stand Month Year' date from an Onkopedia guideline page."""
    url = ONKOPEDIA_URL.format(slug=slug)
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; HemaGuide/1.0)"})
            resp.raise_for_status()
            # Primary: parse structured HTML header (Stand label + value in separate spans)
            header_match = re.search(
                r'Stand</span>\s*<span[^>]*>(\w+)\s+(\d{4})</span>',
                resp.text,
            )
            if header_match:
                month_num = GERMAN_MONTHS.get(header_match.group(1).lower())
                if month_num:
                    return f"{header_match.group(2)}-{month_num:02d}"
            # Fallback: inline "Stand Month Year" in body text
            dates = []
            for match in re.finditer(r'Stand\s+(\w+)\s+(\d{4})', resp.text):
                month_num = GERMAN_MONTHS.get(match.group(1).lower())
                if month_num:
                    dates.append(f"{match.group(2)}-{month_num:02d}")
            if dates:
                return max(dates)
            return None
        except Exception as e:
            if attempt == 0:
                import time; time.sleep(1)
                continue
            logger.warning(f"Failed to fetch Onkopedia stand for {slug}: {e}")
    return None


@app.get("/api/flowchart-status", response_model=FlowchartStatusResponse)
async def check_flowchart_status():
    """Check whether local flowcharts are current against Onkopedia online versions."""
    if not FLOWCHART_SOURCES.exists():
        raise HTTPException(404, "onkopedia.json not found")

    with open(FLOWCHART_SOURCES, 'r', encoding='utf-8') as f:
        sources = json.load(f)

    # Fetch all Onkopedia dates concurrently
    slugs = list(sources.keys())
    online_stands = await asyncio.gather(*(
        asyncio.to_thread(_fetch_onkopedia_stand, sources[s]["onkopedia_slug"])
        for s in slugs
    ))

    flowcharts = []
    for slug, online_stand in zip(slugs, online_stands):
        entry = sources[slug]
        local_stand = entry.get("local_stand")
        onkopedia_url = ONKOPEDIA_URL.format(slug=entry["onkopedia_slug"])

        if online_stand is None:
            status = "error"
            message = "Onkopedia unreachable"
        elif local_stand is None:
            status = "unknown"
            message = "Local date not set"
        elif local_stand >= online_stand:
            status = "current"
            message = None
        else:
            status = "outdated"
            message = f"Local: {local_stand} → Onkopedia: {online_stand}"

        flowcharts.append(FlowchartStatus(
            slug=slug,
            name=entry["name"],
            local_stand=local_stand,
            online_stand=online_stand,
            onkopedia_url=onkopedia_url,
            status=status,
            message=message,
        ))

    flowcharts.sort(key=lambda f: f.name)

    return FlowchartStatusResponse(
        checked_at=datetime.now().isoformat(),
        flowcharts=flowcharts,
    )


# --- API Endpoints ---

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/system-status")
async def system_status():
    """Return local runtime readiness and installed Ollama models."""
    ollama_error = None
    models = []
    try:
        response = await asyncio.to_thread(requests.get, "http://localhost:11434/api/tags", timeout=3)
        response.raise_for_status()
        models = sorted({item.get("name", "") for item in response.json().get("models", []) if item.get("name")})
    except Exception as exc:
        ollama_error = str(exc)

    decision_models = [name for name in models if "embed" not in name.lower()]
    embedding_models = [name for name in models if "embed" in name.lower()]
    flowchart_dir = PROJECT_ROOT / "data" / "flowchart"
    return {
        "ollama_connected": ollama_error is None,
        "ollama_error": ollama_error,
        "models": models,
        "decision_models": decision_models,
        "embedding_models": embedding_models,
        "recommended_decision_model": "qwen3:8b" if "qwen3:8b" in decision_models else (decision_models[0] if decision_models else None),
        "recommended_embedding_model": "embeddinggemma:300m" if "embeddinggemma:300m" in embedding_models else (embedding_models[0] if embedding_models else None),
        "knowledge_base_ready": KB_DIR.exists(),
        "flowchart_count": len(list(flowchart_dir.glob("*.txt"))) if flowchart_dir.exists() else 0,
        "python_path": str(VENV_PYTHON),
        "python_ready": VENV_PYTHON.exists(),
    }


@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a .docx file to query_input/"""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    if not file.filename.endswith('.docx'):
        raise HTTPException(400, "Only .docx files are allowed")

    if file.filename.startswith('~'):
        raise HTTPException(400, "Temporary files are not allowed")

    QUERY_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    file_path = QUERY_INPUT_DIR / file.filename
    if not file_path.resolve().is_relative_to(QUERY_INPUT_DIR.resolve()):
        raise HTTPException(400, "Invalid filename")

    with open(file_path, 'wb') as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"Uploaded file: {file.filename}")
    return UploadResponse(filename=file.filename, path=str(file_path))


@app.delete("/api/upload/{filename}")
async def delete_file(filename: str):
    """Delete an uploaded file and its extracted/enriched versions."""
    file_path = QUERY_INPUT_DIR / filename
    if not file_path.resolve().is_relative_to(QUERY_INPUT_DIR.resolve()):
        raise HTTPException(400, "Invalid filename")
    if file_path.exists():
        file_path.unlink()
        for subdir in ['extracted_data/query_input', 'enriched_data/query_input']:
            json_path = PROJECT_ROOT / subdir / f"{Path(filename).stem}.json"
            if json_path.exists():
                json_path.unlink()
        logger.info(f"Deleted file: {filename}")
        return {"deleted": filename}
    raise HTTPException(404, "File not found")


@app.get("/api/files")
async def list_files():
    """List uploaded .docx files."""
    if not QUERY_INPUT_DIR.exists():
        return {"files": []}
    files = [f.name for f in QUERY_INPUT_DIR.glob("*.docx") if not f.name.startswith('~')]
    return {"files": sorted(files)}


@app.post("/api/process", response_model=JobResponse)
async def start_processing(request: ProcessRequest):
    """Start processing uploaded files."""
    if not request.files:
        raise HTTPException(400, "No files specified")

    for filename in request.files:
        file_path = QUERY_INPUT_DIR / filename
        if not file_path.resolve().is_relative_to(QUERY_INPUT_DIR.resolve()):
            raise HTTPException(400, "Invalid filename")
        if not file_path.is_file():
            raise HTTPException(404, f"File not found: {filename}")

    job_id = str(uuid.uuid4())[:8]

    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "message": "Warteschlange",
        "progress": 0,
        "current_case": 0,
        "total_cases": len(request.files),
        "logs": [],
        "case_results": [],
        "files": request.files,
        "config": {
            "llm_mode": request.llm_mode,
            "decision_model": request.decision_model,
            "use_flowchart": request.use_flowchart,
            "use_historical_cases": request.use_historical_cases,
            "use_pubmed": request.use_pubmed,
            "use_conferences": request.use_conferences,
        },
        "created_at": datetime.now().isoformat(),
        "result": None,
        "extraction_previews": [],
    }
    asyncio.create_task(process_documents(job_id))

    logger.info(f"Started job {job_id} for files: {request.files}")
    return JobResponse(job_id=job_id)


@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Get current job status."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return StatusResponse(**jobs[job_id])


@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    """Get job results."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(400, f"Job not complete: {job['status']}")

    return job["result"]


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket for real-time status updates."""
    await manager.connect(job_id, websocket)
    try:
        if job_id in jobs:
            await websocket.send_json({
                **jobs[job_id],
                "logs": jobs[job_id].get("logs", [])[-20:]
            })

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)


# Serve pre-built frontend (production mode)
FRONTEND_DIST = PROJECT_ROOT / 'frontend' / 'dist'
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static-root")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
