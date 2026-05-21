"""Manual upload and load jobs for local Juso datasets."""

from __future__ import annotations

import shutil
import threading
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from kraddr.geo import (
    SpatialiteAddressStore,
    iter_location_summary_records,
    iter_navigation_building_records,
    iter_navigation_road_section_entrance_records,
)

from .config import load_settings

DatasetKind = Literal[
    "auto",
    "location_summary",
    "navigation_building",
    "navigation_road_section_entrance",
    "boundary_shapes",
]
JobStatus = Literal["pending", "running", "succeeded", "failed"]

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / ".uploads"
POINT_BATCH_SIZE = 50_000
SHAPE_SIDECAR_SUFFIXES = {".shp", ".dbf", ".shx", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}


@dataclass(slots=True)
class LoadJob:
    id: str
    dataset: DatasetKind
    replace: bool
    root: Path
    files: list[Path]
    status: JobStatus = "pending"
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    loaded: int = 0
    skipped: int = 0
    message: str = "대기 중"
    errors: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def progress_percent(self) -> float:
        if self.status == "succeeded":
            return 100.0
        if self.total_files <= 0:
            return 0.0
        return round(min(99.0, (self.processed_files / self.total_files) * 100), 1)


@dataclass(frozen=True, slots=True)
class LoadUnit:
    kind: DatasetKind
    path: Path
    display_name: str
    source_name: str


_jobs: dict[str, LoadJob] = {}
_jobs_lock = threading.Lock()


def create_load_job(
    *,
    files: Sequence[tuple[str, Path]],
    dataset: DatasetKind,
    replace: bool,
) -> dict[str, object]:
    """Persist uploaded files and register a background load job."""

    job_id = uuid4().hex
    root = UPLOAD_ROOT / job_id
    root.mkdir(parents=True, exist_ok=True)
    saved_files = []
    for filename, source_path in files:
        destination = root / _safe_relative_path(filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), destination)
        saved_files.append(destination)
    job = LoadJob(id=job_id, dataset=dataset, replace=replace, root=root, files=saved_files)
    with _jobs_lock:
        _jobs[job.id] = job
    return job_snapshot(job)


def run_load_job(job_id: str) -> None:
    """Run one registered job in the current process."""

    _update_job(job_id, status="running", message="파일 분류 중")
    try:
        with _jobs_lock:
            job = _jobs[job_id]
        units = _build_load_units(job)
        _update_job(job_id, total_files=len(units), message="적재 시작")
        settings = load_settings()
        current = SpatialiteAddressStore(
            settings.spatialite_path,
            load_spatialite=True,
            vworld_api_key=settings.vworld_api_key,
            vworld_domain=settings.vworld_domain,
        )
        try:
            boundary_replace_used = False
            for index, unit in enumerate(units, 1):
                _update_job(
                    job_id,
                    current_file=unit.display_name,
                    processed_files=index - 1,
                    message=f"{unit.kind} 적재 중",
                )
                loaded, skipped = _load_unit(
                    current,
                    unit,
                    replace=job.replace,
                    boundary_replace=job.replace and not boundary_replace_used,
                )
                if unit.kind == "boundary_shapes":
                    boundary_replace_used = boundary_replace_used or job.replace
                _increment_job(
                    job_id,
                    loaded=loaded,
                    skipped=skipped,
                    processed_files=index,
                    message=f"{unit.display_name} 완료",
                )
        finally:
            current.close()
        _update_job(job_id, status="succeeded", current_file="", message="적재 완료")
    except Exception as exc:  # noqa: BLE001 - job failures must be visible in the UI
        _update_job(job_id, status="failed", message=str(exc), add_error=str(exc))


def get_load_job(job_id: str) -> dict[str, object]:
    with _jobs_lock:
        return job_snapshot(_jobs[job_id])


def list_load_jobs(limit: int = 20) -> dict[str, object]:
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda item: item.created_at, reverse=True)[:limit]
        return {"items": [job_snapshot(job) for job in jobs]}


def reset_jobs_for_tests() -> None:
    """Clear in-memory jobs for isolated API tests."""

    with _jobs_lock:
        _jobs.clear()


def job_snapshot(job: LoadJob) -> dict[str, object]:
    return {
        "id": job.id,
        "dataset": job.dataset,
        "replace": job.replace,
        "status": job.status,
        "total_files": job.total_files,
        "processed_files": job.processed_files,
        "current_file": job.current_file,
        "loaded": job.loaded,
        "skipped": job.skipped,
        "message": job.message,
        "errors": list(job.errors),
        "progress_percent": job.progress_percent,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _build_load_units(job: LoadJob) -> list[LoadUnit]:
    units = []
    shape_paths: set[Path] = set()
    if job.dataset in {"auto", "boundary_shapes"}:
        shape_units = _shape_units(job.root, job.files)
        units.extend(shape_units)
        shape_paths = {
            path
            for path in job.files
            if path.suffix.lower() in SHAPE_SIDECAR_SUFFIXES
        }
    for path in job.files:
        if path in shape_paths:
            continue
        kind = _classify_dataset(path, requested=job.dataset)
        if kind == "auto":
            continue
        units.append(_unit(kind, path, job.root))
    if not units:
        raise ValueError("적재할 수 있는 TXT, 7Z, ZIP, SHP 파일을 찾지 못했습니다.")
    return units


def _load_unit(
    store: SpatialiteAddressStore,
    unit: LoadUnit,
    *,
    replace: bool,
    boundary_replace: bool,
) -> tuple[int, int]:
    if unit.kind == "location_summary":
        return _load_location_summary(store, unit, replace=replace)
    if unit.kind == "navigation_building":
        return _load_navigation_building(store, unit, replace=replace)
    if unit.kind == "navigation_road_section_entrance":
        result = store.load_navigation_road_section_entrance_records(
            iter_navigation_road_section_entrance_records(unit.path),
            replace=replace,
            batch_size=POINT_BATCH_SIZE,
            source=unit.source_name,
        )
        return result.loaded, result.skipped
    if unit.kind == "boundary_shapes":
        result = store.load_boundary_zips([unit.path], replace=boundary_replace)
        return result.loaded, result.skipped
    raise ValueError(f"지원하지 않는 데이터 유형입니다: {unit.kind}")


def _load_location_summary(
    store: SpatialiteAddressStore,
    unit: LoadUnit,
    *,
    replace: bool,
) -> tuple[int, int]:
    loaded = 0
    skipped = 0
    for index, chunk in enumerate(_batched(iter_location_summary_records(unit.path)), 1):
        result = store.load_location_summary_records(
            chunk,
            replace=replace and index == 1,
            batch_size=POINT_BATCH_SIZE,
            source=unit.source_name,
        )
        loaded += result.loaded
        skipped += result.skipped
    return loaded, skipped


def _load_navigation_building(
    store: SpatialiteAddressStore,
    unit: LoadUnit,
    *,
    replace: bool,
) -> tuple[int, int]:
    loaded = 0
    skipped = 0
    for index, chunk in enumerate(_batched(iter_navigation_building_records(unit.path)), 1):
        result = store.load_navigation_building_records(
            chunk,
            replace=replace and index == 1,
            batch_size=POINT_BATCH_SIZE,
            source=unit.source_name,
        )
        loaded += result.loaded
        skipped += result.skipped
    return loaded, skipped


def _batched(records: Iterable[object], size: int = POINT_BATCH_SIZE) -> Iterable[list[object]]:
    batch = []
    for record in records:
        batch.append(record)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _unit(kind: DatasetKind, path: Path, root: Path) -> LoadUnit:
    relative = str(path.relative_to(root)).replace("\\", "/")
    return LoadUnit(kind=kind, path=path, display_name=relative, source_name=relative)


def _shape_units(root: Path, files: Sequence[Path]) -> list[LoadUnit]:
    by_dir_stem: dict[tuple[Path, str], list[Path]] = {}
    for path in files:
        if path.suffix.lower() not in SHAPE_SIDECAR_SUFFIXES:
            continue
        by_dir_stem.setdefault((path.parent, path.stem), []).append(path)
    units = []
    for index, ((directory, stem), grouped_files) in enumerate(sorted(by_dir_stem.items()), 1):
        if not any(path.suffix.lower() == ".shp" for path in grouped_files):
            continue
        zip_path = root / "_prepared_shapes" / f"{index:04d}_{stem}.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        region_dir = f"manual_{index:04d}"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in grouped_files:
                archive.write(path, f"{region_dir}/{path.name}")
        display = str(directory.relative_to(root) / f"{stem}.shp").replace("\\", "/")
        units.append(
            LoadUnit(
                kind="boundary_shapes",
                path=zip_path,
                display_name=display,
                source_name=display,
            )
        )
    return units


def _classify_dataset(path: Path, *, requested: DatasetKind) -> DatasetKind:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".zip":
        return _classify_zip(path)
    if suffix == ".7z":
        return "navigation_building"
    if suffix in {".txt", ".dat"}:
        if name.startswith("match_rs_entrc"):
            return "navigation_road_section_entrance"
        if name.startswith("match_build"):
            return "navigation_building"
        return "location_summary"
    if suffix in SHAPE_SIDECAR_SUFFIXES:
        return "boundary_shapes"
    return "auto"


def _classify_zip(path: Path) -> DatasetKind:
    with zipfile.ZipFile(path) as archive:
        names = [Path(name).name.lower() for name in archive.namelist() if not name.endswith("/")]
    if any(name.endswith(".shp") for name in names):
        return "boundary_shapes"
    if any(name.startswith("match_rs_entrc") for name in names):
        return "navigation_road_section_entrance"
    if any(name.startswith("match_build") for name in names):
        return "navigation_building"
    if any(name.startswith("entrc") for name in names):
        return "location_summary"
    return "location_summary"


def _safe_relative_path(filename: str) -> Path:
    raw_parts = filename.replace("\\", "/").split("/")
    parts = [
        part.strip().replace(":", "_")
        for part in raw_parts
        if part.strip() and part not in {".", ".."}
    ]
    if not parts:
        parts = [f"upload-{uuid4().hex}"]
    return Path(*parts)


def _update_job(job_id: str, **changes: object) -> None:
    add_error = changes.pop("add_error", None)
    with _jobs_lock:
        job = _jobs[job_id]
        for key, value in changes.items():
            setattr(job, key, value)
        if add_error:
            job.errors.append(str(add_error))
        job.updated_at = datetime.now(UTC)


def _increment_job(job_id: str, **changes: int | str) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
        for key, value in changes.items():
            if key in {"loaded", "skipped"}:
                setattr(job, key, int(getattr(job, key)) + int(value))
            else:
                setattr(job, key, value)
        job.updated_at = datetime.now(UTC)
