"""Source-management audit event_type / action constants (T-202, T-203+).

These are plain string constants (the audit ``action`` == ``event_type`` value
set for source-management actions) and the frozenset of all of them. They live
in ``core`` so that lower layers (e.g. ``infra``) can reference them without
importing ``api`` (which would violate the layered-architecture contract). The
``api.security`` module re-exports them so existing
``from kortravelgeo.api.security import SOURCE_*`` imports keep working.
"""

from __future__ import annotations

# --- Audit event_type / action constants -----------------------------------
# Audit `action` (== event_type) value set for the upcoming T-203+ source
# management actions. Naming follows the existing dot-separated convention
# (e.g. "serving_release.activate", "consistency.sample.decision", "geoip.denied").
SOURCE_UPLOAD_REGISTER = "source_upload.register"
SOURCE_MATCH_SET_ACTIVATE = "source_match_set.activate"
SOURCE_REBUILD_DB = "source.rebuild_db"
SOURCE_FORCED_PROMOTION = "source.forced_promotion"
SOURCE_HARD_DELETE = "source.hard_delete"
SOURCE_UPDATE_HASH_AFTER_VERIFY = "source.update_hash_after_verify"
SOURCE_JANITOR = "source.janitor"
# T-204 RustFS reconciliation.
SOURCE_RECONCILE_RUN = "source.reconcile_run"
SOURCE_RECONCILE_RESOLVE = "source.reconcile_resolve"

#: All source-management audit event types introduced for T-109 / T-203+.
SOURCE_AUDIT_EVENT_TYPES: frozenset[str] = frozenset(
    {
        SOURCE_UPLOAD_REGISTER,
        SOURCE_MATCH_SET_ACTIVATE,
        SOURCE_REBUILD_DB,
        SOURCE_FORCED_PROMOTION,
        SOURCE_HARD_DELETE,
        SOURCE_UPDATE_HASH_AFTER_VERIFY,
        SOURCE_JANITOR,
        SOURCE_RECONCILE_RUN,
        SOURCE_RECONCILE_RESOLVE,
    }
)
