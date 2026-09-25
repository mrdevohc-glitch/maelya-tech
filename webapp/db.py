"""Base SQLite pour la file de jobs de la plateforme web. Une connexion courte par operation
(SQLite + mode WAL gere bien les acces concurrents pour ce volume -- un seul utilisateur, une
poignee de jobs par jour) -- pas besoin d'un pool de connexions.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from common.paths import AGENTS_ROOT

DB_PATH = AGENTS_ROOT / "webapp" / "webapp.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                 -- 'code' | 'marketing' | 'execute_action'
    task TEXT NOT NULL,
    project_dir TEXT,                   -- pour kind='code'
    thread TEXT,                        -- pour kind='marketing'
    client_id TEXT,                     -- pour kind='marketing' cible a un client (optionnel)
    allow_push INTEGER NOT NULL DEFAULT 0,
    max_iterations INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | running | succeeded | failed
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    business_profile TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client_credentials (
    client_id TEXT NOT NULL,
    platform TEXT NOT NULL,             -- 'meta' | 'linkedin' | 'google_ads' | 'x'
    encrypted_payload BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (client_id, platform)
);

CREATE TABLE IF NOT EXISTS intake_submissions (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    company TEXT,
    brief TEXT NOT NULL,
    job_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued',   -- queued | running | succeeded | failed
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_submissions_created_at ON intake_submissions(created_at);

CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    platform TEXT NOT NULL,             -- 'meta' | 'linkedin' | 'google_ads' | 'x'
    action_type TEXT NOT NULL,          -- 'post' | 'campaign'
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | executed | failed
    created_by_job_id TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    executed_at TEXT,
    result TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_client ON pending_actions(client_id);

CREATE TABLE IF NOT EXISTS scan_targets (
    id TEXT PRIMARY KEY,
    client_id TEXT,                     -- NULL = notre propre infra (pas un projet client)
    target_type TEXT NOT NULL,          -- 'self' | 'third_party'
    hostname TEXT NOT NULL,             -- pour nmap
    url TEXT NOT NULL,                  -- pour nikto (http(s)://...)
    authorized_note TEXT NOT NULL,      -- confirmation ecrite par l'utilisateur, obligatoire
    created_at TEXT NOT NULL,
    last_scan_at TEXT
);

CREATE TABLE IF NOT EXISTS scan_results (
    id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    scan_type TEXT NOT NULL,            -- 'port' | 'web_vuln'
    result_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scan_results_target ON scan_results(target_id);
"""


def _migrate_add_missing_columns(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS ne modifie pas une table existante -- si une table existe
    deja sans une colonne ajoutee par une fonctionnalite plus recente, on l'ajoute ici."""
    jobs_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "client_id" not in jobs_columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN client_id TEXT")

    clients_columns = {row[1] for row in conn.execute("PRAGMA table_info(clients)").fetchall()}
    if "whatsapp_number" not in clients_columns:
        conn.execute("ALTER TABLE clients ADD COLUMN whatsapp_number TEXT")

    intake_columns = {row[1] for row in conn.execute("PRAGMA table_info(intake_submissions)").fetchall()}
    if "contact_phone" not in intake_columns:
        conn.execute("ALTER TABLE intake_submissions ADD COLUMN contact_phone TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate_add_missing_columns(conn)


def mark_interrupted_jobs_as_failed() -> int:
    """A appeler au demarrage du serveur : tout job reste 'running' apres un crash/redemarrage
    est en realite arrete -- on le marque honnetement en echec plutot que de le laisser bloque
    'running' pour toujours."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='failed', error='Interrompu par un redemarrage du serveur', "
            "finished_at=? WHERE status='running'",
            (_now(),),
        )
        return cur.rowcount


def create_job(
    kind: str,
    task: str,
    project_dir: str | None = None,
    thread: str | None = None,
    client_id: str | None = None,
    allow_push: bool = False,
    max_iterations: int | None = None,
) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, kind, task, project_dir, thread, client_id, allow_push, "
            "max_iterations, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
            (job_id, kind, task, project_dir, thread, client_id, int(allow_push), max_iterations, _now()),
        )
    return job_id


def claim_next_queued_job() -> sqlite3.Row | None:
    """Recupere le plus ancien job 'queued' et le passe en 'running' en une seule transaction
    (evite qu'un deuxieme worker -- s'il y en avait un jour un -- prenne le meme job)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE jobs SET status='running', started_at=? WHERE id=?", (_now(), row["id"])
        )
        return row


def mark_succeeded(job_id: str, result: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='succeeded', result=?, finished_at=? WHERE id=?",
            (result, _now(), job_id),
        )


def mark_failed(job_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE id=?",
            (error, _now(), job_id),
        )


def get_job(job_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def list_jobs(kind: str | None = None, status: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    if kind:
        query += " AND kind=?"
        params.append(kind)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        return conn.execute(query, params).fetchall()


def list_projects() -> list[dict]:
    """Dossiers de projet 'code' deja utilises, avec la date du dernier job."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT project_dir, MAX(created_at) AS last_activity, COUNT(*) AS job_count "
            "FROM jobs WHERE kind='code' AND project_dir IS NOT NULL "
            "GROUP BY project_dir ORDER BY last_activity DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def list_marketing_threads() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT thread, MAX(created_at) AS last_activity, COUNT(*) AS job_count "
            "FROM jobs WHERE kind='marketing' AND thread IS NOT NULL "
            "GROUP BY thread ORDER BY last_activity DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# --- Clients ---

def create_client(name: str, business_profile: str = "", whatsapp_number: str | None = None) -> str:
    client_id = uuid.uuid4().hex[:10]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO clients (id, name, business_profile, whatsapp_number, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (client_id, name, business_profile, whatsapp_number, _now()),
        )
    return client_id


def get_client(client_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()


def get_client_by_whatsapp_number(whatsapp_number: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM clients WHERE whatsapp_number=?", (whatsapp_number,)
        ).fetchone()


def list_clients() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM clients ORDER BY name ASC").fetchall()


def update_client_profile(client_id: str, business_profile: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE clients SET business_profile=? WHERE id=?", (business_profile, client_id)
        )


def update_client_whatsapp_number(client_id: str, whatsapp_number: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE clients SET whatsapp_number=? WHERE id=?", (whatsapp_number, client_id)
        )


# --- Identifiants clients (payload deja chiffre par l'appelant -- voir common/crypto.py) ---

def save_client_credentials(client_id: str, platform: str, encrypted_payload: bytes) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO client_credentials (client_id, platform, encrypted_payload, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(client_id, platform) DO UPDATE SET "
            "encrypted_payload=excluded.encrypted_payload, updated_at=excluded.updated_at",
            (client_id, platform, encrypted_payload, _now()),
        )


def get_client_credentials(client_id: str, platform: str) -> bytes | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT encrypted_payload FROM client_credentials WHERE client_id=? AND platform=?",
            (client_id, platform),
        ).fetchone()
        return row["encrypted_payload"] if row else None


def list_client_platforms(client_id: str) -> list[str]:
    """Plateformes pour lesquelles ce client a des identifiants enregistres (jamais les
    valeurs elles-memes)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT platform FROM client_credentials WHERE client_id=? ORDER BY platform",
            (client_id,),
        ).fetchall()
        return [r["platform"] for r in rows]


# --- Actions en attente d'approbation ---

def create_pending_action(
    client_id: str, platform: str, action_type: str, payload_json: str, created_by_job_id: str | None = None
) -> str:
    action_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO pending_actions (id, client_id, platform, action_type, payload_json, "
            "status, created_by_job_id, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (action_id, client_id, platform, action_type, payload_json, created_by_job_id, _now()),
        )
    return action_id


def get_pending_action(action_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM pending_actions WHERE id=?", (action_id,)).fetchone()


def list_pending_actions(status: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
    query = "SELECT * FROM pending_actions WHERE 1=1"
    params: list = []
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        return conn.execute(query, params).fetchall()


def decide_pending_action(action_id: str, approved: bool) -> None:
    """Marque une action 'approved' ou 'rejected'. L'execution reelle (si approuvee) est
    declenchee separement (voir job kind='execute_action'), pas ici -- cette fonction ne fait
    que consigner la decision humaine."""
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET status=?, decided_at=? WHERE id=?",
            ("approved" if approved else "rejected", _now(), action_id),
        )


def mark_action_executed(action_id: str, result: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET status='executed', executed_at=?, result=? WHERE id=?",
            (_now(), result, action_id),
        )


def mark_action_failed(action_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE pending_actions SET status='failed', executed_at=?, result=? WHERE id=?",
            (_now(), error, action_id),
        )


# --- Demandes entrantes (portail public /demande) ---

def create_intake_submission(
    client_id: str, contact_name: str, contact_email: str, company: str, brief: str, job_id: str,
    contact_phone: str | None = None,
) -> str:
    submission_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO intake_submissions (id, client_id, contact_name, contact_email, "
            "company, brief, job_id, contact_phone, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
            (submission_id, client_id, contact_name, contact_email, company, brief, job_id,
             contact_phone, _now()),
        )
    return submission_id


def get_intake_submission(submission_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM intake_submissions WHERE id=?", (submission_id,)
        ).fetchone()


def get_intake_submission_by_job(job_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM intake_submissions WHERE job_id=?", (job_id,)
        ).fetchone()


def list_intake_submissions(limit: int = 100) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM intake_submissions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


def update_intake_status(submission_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE intake_submissions SET status=? WHERE id=?", (status, submission_id))


def count_intake_submissions_today() -> int:
    """Nombre de demandes recues depuis minuit UTC -- utilise comme plafond de securite anti-abus
    sur le formulaire public (chaque demande declenche un vrai appel OpenAI payant)."""
    start_of_day = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM intake_submissions WHERE created_at >= ?", (start_of_day,)
        ).fetchone()
        return row["n"]


# --- Cibles de scan securite (tests d'intrusion hebdomadaires) ---

def create_scan_target(
    target_type: str, hostname: str, url: str, authorized_note: str, client_id: str | None = None
) -> str:
    target_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO scan_targets (id, client_id, target_type, hostname, url, "
            "authorized_note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (target_id, client_id, target_type, hostname, url, authorized_note, _now()),
        )
    return target_id


def get_scan_target(target_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM scan_targets WHERE id=?", (target_id,)).fetchone()


def list_scan_targets() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM scan_targets ORDER BY created_at ASC").fetchall()


def list_due_scan_targets(max_age_days: int = 7) -> list[sqlite3.Row]:
    """Cibles jamais scannees, ou dont le dernier scan date de plus de `max_age_days` --
    utilise par le scheduler hebdomadaire (webapp/job_runner.py). Ne lit QUE cette table --
    jamais une cible fournie ailleurs (agent, portail public, etc.)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM scan_targets WHERE last_scan_at IS NULL OR last_scan_at < ?", (cutoff,)
        ).fetchall()


def has_pending_security_scan(target_id: str) -> bool:
    """Evite que le planificateur (verifie toutes les heures) ne cree un deuxieme job pour la
    meme cible si le premier n'a pas encore ete traite par le worker."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE kind='security_scan' AND task=? AND status IN "
            "('queued', 'running') LIMIT 1",
            (target_id,),
        ).fetchone()
        return row is not None


def mark_scan_target_scanned(target_id: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE scan_targets SET last_scan_at=? WHERE id=?", (_now(), target_id))


def create_scan_result(target_id: str, scan_type: str, result_text: str) -> str:
    result_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO scan_results (id, target_id, scan_type, result_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (result_id, target_id, scan_type, result_text, _now()),
        )
    return result_id


def list_scan_results(target_id: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
    query = "SELECT * FROM scan_results WHERE 1=1"
    params: list = []
    if target_id:
        query += " AND target_id=?"
        params.append(target_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        return conn.execute(query, params).fetchall()


def get_scan_result(result_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM scan_results WHERE id=?", (result_id,)).fetchone()
