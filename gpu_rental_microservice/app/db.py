import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from .config import settings

_lock = threading.Lock()

def _connect():
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_conn():
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

def init_db():
    with get_conn() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT UNIQUE NOT NULL,
                api_key_hash TEXT UNIQUE NOT NULL,
                scopes TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                requests_per_minute INTEGER NOT NULL,
                max_concurrent_jobs INTEGER NOT NULL,
                max_job_seconds INTEGER NOT NULL,
                max_input_bytes INTEGER NOT NULL,
                monthly_credit_limit REAL NOT NULL,
                price_per_gpu_second REAL NOT NULL,
                gpu_share REAL NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                workload_name TEXT NOT NULL,
                status TEXT NOT NULL,
                estimated_seconds INTEGER NOT NULL,
                billed_seconds INTEGER NOT NULL DEFAULT 0,
                gpu_seconds REAL NOT NULL DEFAULT 0,
                peak_vram_mb INTEGER NOT NULL DEFAULT 0,
                input_bytes INTEGER NOT NULL DEFAULT 0,
                output_bytes INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(client_name, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS request_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                request_bytes INTEGER NOT NULL DEFAULT 0,
                response_bytes INTEGER NOT NULL DEFAULT 0,
                latency_ms REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            '''
        )

def upsert_client(**kwargs):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO clients (
                client_name, api_key_hash, scopes, plan_name,
                requests_per_minute, max_concurrent_jobs, max_job_seconds,
                max_input_bytes, monthly_credit_limit, price_per_gpu_second,
                gpu_share, is_admin, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(client_name) DO UPDATE SET
                api_key_hash=excluded.api_key_hash,
                scopes=excluded.scopes,
                plan_name=excluded.plan_name,
                requests_per_minute=excluded.requests_per_minute,
                max_concurrent_jobs=excluded.max_concurrent_jobs,
                max_job_seconds=excluded.max_job_seconds,
                max_input_bytes=excluded.max_input_bytes,
                monthly_credit_limit=excluded.monthly_credit_limit,
                price_per_gpu_second=excluded.price_per_gpu_second,
                gpu_share=excluded.gpu_share,
                is_admin=excluded.is_admin
            ''',
            (
                kwargs["client_name"],
                kwargs["api_key_hash"],
                kwargs["scopes"],
                kwargs["plan_name"],
                kwargs["requests_per_minute"],
                kwargs["max_concurrent_jobs"],
                kwargs["max_job_seconds"],
                kwargs["max_input_bytes"],
                kwargs["monthly_credit_limit"],
                kwargs["price_per_gpu_second"],
                kwargs["gpu_share"],
                kwargs["is_admin"],
            ),
        )

def get_client_by_api_hash(api_key_hash: str):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM clients WHERE api_key_hash = ? AND is_active = 1",
            (api_key_hash,),
        )
        return cur.fetchone()

def insert_job(job: dict):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO jobs (
                id, client_name, workload_name, status, estimated_seconds,
                billed_seconds, gpu_seconds, peak_vram_mb, input_bytes,
                output_bytes, idempotency_key, created_at, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                job["id"], job["client_name"], job["workload_name"], job["status"],
                job["estimated_seconds"], job["billed_seconds"], job["gpu_seconds"],
                job["peak_vram_mb"], job["input_bytes"], job["output_bytes"],
                job["idempotency_key"], job["created_at"], job["started_at"], job["finished_at"]
            ),
        )

def get_job(job_id: str):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return cur.fetchone()

def get_job_by_idempotency(client_name: str, idempotency_key: str):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM jobs WHERE client_name = ? AND idempotency_key = ?",
            (client_name, idempotency_key),
        )
        return cur.fetchone()

def count_running_jobs(client_name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE client_name = ? AND status IN ('queued','running')",
            (client_name,),
        )
        return int(cur.fetchone()["c"])

def update_job(job_id: str, **kwargs):
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [job_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {fields} WHERE id = ?", values)

def insert_audit(**kwargs):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO request_audit (
                client_name, path, method, status_code,
                request_bytes, response_bytes, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                kwargs["client_name"], kwargs["path"], kwargs["method"], kwargs["status_code"],
                kwargs["request_bytes"], kwargs["response_bytes"], kwargs["latency_ms"], kwargs["created_at"]
            )
        )

def monthly_usage(client_name: str, month_prefix: str):
    with get_conn() as conn:
        jobs = conn.execute(
            '''
            SELECT
                COUNT(*) AS total_requests,
                COALESCE(SUM(input_bytes), 0) AS total_input_bytes,
                COALESCE(SUM(output_bytes), 0) AS total_output_bytes,
                COALESCE(SUM(billed_seconds), 0) AS total_billed_seconds,
                COALESCE(SUM(gpu_seconds), 0) AS total_gpu_seconds,
                COALESCE(MAX(peak_vram_mb), 0) AS total_peak_vram_mb
            FROM jobs
            WHERE client_name = ? AND substr(created_at, 1, 7) = ?
            ''',
            (client_name, month_prefix),
        ).fetchone()

        client = conn.execute(
            "SELECT * FROM clients WHERE client_name = ?",
            (client_name,),
        ).fetchone()
        return jobs, client

def list_clients():
    with get_conn() as conn:
        cur = conn.execute(
            '''
            SELECT client_name, plan_name, requests_per_minute, max_concurrent_jobs,
                   max_job_seconds, max_input_bytes, monthly_credit_limit,
                   price_per_gpu_second, gpu_share, is_active
            FROM clients ORDER BY client_name
            '''
        )
        return cur.fetchall()

def utcnow_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()
