"""
Olira SDK — Project (Workspace) Management

A project is a self-contained, isolated workspace within your organization:
its own patients, event logs, patient state, views, cohorts, and configuration.
Everything you can do with projects in the Olira Console, you can do here.

Covers the full project lifecycle:
  - List projects (every org has a "default" project)
  - Create a new (empty) project
  - Select a project for data operations via init(project=...) / OliraClient(project=...)
  - Duplicate a project's *configuration* into a new one (never its patients/data)
  - Rename / retag a project
  - Deprecate (soft-delete → recoverable) and Restore
  - Permanently delete a deprecated project (irreversible)

All project-management calls require:
  - the ``api:manage-projects`` scope, AND
  - an **org-wide** API key (a project-locked key is confined to its own
    workspace and gets 403 on these routes).

Run: python 10_project_management.py
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, OliraClient, OliraEnv  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]  # must be an org-wide key with api:manage-projects
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

RUN = uuid.uuid4().hex[:6]

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT,
    async_flush=False,
    timeout=30.0,
)

# Everything created below is tracked so the ``finally`` cleanup removes it even
# if a step fails partway through — no throwaway workspaces left behind.
created_project_ids: list[str] = []
created_patients: list[tuple[OliraClient, str]] = []  # (scoped client, patient_id)
dev_client: OliraClient | None = None

try:
    # ── 1. List projects ──────────────────────────────────────────────────────
    # Every organization has exactly one "default" project. Data written without
    # a selected project (no init(project=...) / OliraClient(project=...)) lands there.
    print("\n── 1. List projects ────────────────────────────────────────────────────")
    projects = client.list_projects()
    for p in projects.data:
        default = " (default)" if p.is_default else ""
        print(f"  • {p.slug:<24} status={p.status}{default}")

    # ── 2. Create a new, empty project ────────────────────────────────────────
    # Fresh config, no patients or data carried over — a genuinely clean console.
    print("\n── 2. Create project ───────────────────────────────────────────────────")
    dev = client.create_project(
        name=f"Dev Sandbox {RUN}",
        slug=f"dev-sandbox-{RUN}",  # the handle for init(project=...); omit to derive from name
        description="Created by 10_project_management.py",
        environment="dev",  # optional intent tag: dev | staging | prod
    )
    created_project_ids.append(dev.id)
    print(f"  id          = {dev.id}")
    print(f"  slug        = {dev.slug}   ← pass this to init(project=...)")
    print(f"  environment = {dev.environment}")

    # ── 3. Operate inside a project ───────────────────────────────────────────
    # Point a client at the project (by slug or id). Every patient/log/etc. created
    # through this client is isolated to that workspace.
    print("\n── 3. Write data scoped to the project ─────────────────────────────────")
    dev_client = OliraClient(
        api_key=API_KEY,
        base_url=BASE_URL,
        environment=OliraEnv.DEVELOPMENT,
        project=dev.slug,  # ← selects the workspace (also: olira.init(project=...))
        async_flush=False,
        timeout=30.0,
    )
    patient = dev_client.create_patient(first_name="Sandbox", last_name=f"Patient{RUN}")
    created_patients.append((dev_client, patient.id))
    print(f"  created patient {patient.id} inside project {dev.slug!r}")

    # ── 4. Duplicate a project ────────────────────────────────────────────────
    # Copies CONFIGURATION ONLY (platform config, pipeline templates, cohort
    # definitions) into a brand-new project. Patients, logs, and state are NEVER
    # copied — the duplicate starts empty. Ideal for a validated dev→prod handoff.
    print("\n── 4. Duplicate project (config only) ──────────────────────────────────")
    prod = client.duplicate_project(
        project=dev.slug,
        name=f"Prod {RUN}",
        slug=f"prod-{RUN}",  # pick a distinct handle; don't rely on the "<source> copy" default
        environment="prod",
    )
    created_project_ids.append(prod.id)
    print(f"  duplicated {dev.slug!r} → {prod.slug!r} (env={prod.environment})")
    prod_detail = client.get_project(project=prod.slug)
    print(f"  duplicate status = {prod_detail.status}  (config only — patients/logs/state are never copied)")

    # ── 5. Rename / retag ─────────────────────────────────────────────────────
    print("\n── 5. Rename / retag project ───────────────────────────────────────────")
    renamed = client.rename_project(
        project=dev.id,
        name=f"Dev Sandbox {RUN} (renamed)",
        description="Renamed by the example",
    )
    print(f"  name = {renamed.name!r}")

    # ── 6. Deprecate (soft-delete) ────────────────────────────────────────────
    # Moves the project to the deprecated list. Its data becomes unreachable
    # through normal reads but is fully retained — this is reversible.
    print("\n── 6. Deprecate project ────────────────────────────────────────────────")
    deprecated = client.deprecate_project(project=prod.id)
    print(f"  {prod.slug!r} status = {deprecated.status}")

    # ── 7. Restore ────────────────────────────────────────────────────────────
    print("\n── 7. Restore project ──────────────────────────────────────────────────")
    restored = client.restore_project(project=prod.id)
    print(f"  {prod.slug!r} status = {restored.status}")

    # ── 8. Permanent delete (irreversible) ────────────────────────────────────
    # Must be deprecated first, and blocked (409) while it still has patients.
    # The empty duplicate ("prod") can be erased directly after deprecating it.
    print("\n── 8. Permanently delete a project ─────────────────────────────────────")
    client.deprecate_project(project=prod.id)  # must be deprecated before permanent delete
    client.delete_project(project=prod.id)
    created_project_ids.remove(prod.id)  # gone for good — nothing left to clean up
    print(f"  permanently deleted {prod.slug!r}")

finally:
    # ── Cleanup ───────────────────────────────────────────────────────────────
    # Best-effort removal of everything this script created, even after a partial
    # failure. The permanent-delete guard counts only NON-deleted patients, so
    # soft-deleting the test patients is enough to unblock project deletion.
    # (Not part of a real integration — remove when adapting this code.)
    print("\n── Cleanup ─────────────────────────────────────────────────────────────")
    for scoped_client, patient_id in created_patients:
        try:
            scoped_client.delete_patient(patient_id=patient_id)  # soft-delete (status → deleted)
        except Exception as e:  # noqa: BLE001 — keep cleaning up the rest
            print(f"  ! could not delete patient {patient_id}: {e}")
    for project_id in created_project_ids:
        try:
            client.deprecate_project(project=project_id)
            client.delete_project(project=project_id)
            print(f"  cleaned up project {project_id}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! could not delete project {project_id}: {e}")
    if dev_client is not None:
        dev_client.close()
    client.close()

print("\nDone.")
