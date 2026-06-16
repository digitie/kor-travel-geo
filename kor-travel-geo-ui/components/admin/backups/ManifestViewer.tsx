"use client";

import { X } from "lucide-react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { BackupArtifact } from "@/lib/api";

/** ok=true → 검증됨, false → 불일치, null/undefined → 미검증(legacy/skipped). */
export function inventoryTone(ok: boolean | null | undefined): {
  tone: "ok" | "error" | "warn";
  label: string;
} {
  if (ok === true) return { tone: "ok", label: "검증됨" };
  if (ok === false) return { tone: "error", label: "불일치" };
  return { tone: "warn", label: "미검증" };
}

/**
 * Backup manifest reproducibility viewer (T-252): surfaces the T-237/T-240 manifest context —
 * source_set reference months, source-inventory verification (vs the active match set at backup
 * time), active serving release/snapshot/match-set ids, retention/expiry — plus the raw manifest.
 */
export function ManifestViewer({
  artifact,
  onClose
}: {
  artifact: BackupArtifact;
  onClose: () => void;
}) {
  const manifest = artifact.manifest ?? {};
  const inventory = nested(manifest, "source_inventory_verification");
  const activeServing = nested(manifest, "active_serving");
  const sourceMatchSet = nested(manifest, "source_match_set");
  const inv = inventoryTone(artifact.source_inventory_ok);
  const yyyymm = artifact.source_set_yyyymm ?? null;

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        aria-label="백업 manifest 재현성 뷰어"
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
      >
        <div className="manifest-head">
          <h2>{artifact.display_name ?? artifact.artifact_id}</h2>
          <button aria-label="닫기" className="icon-button" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>

        <dl className="wizard-meta">
          <div>
            <dt>retention</dt>
            <dd>{artifact.retention_class ?? "default"}</dd>
          </div>
          <div>
            <dt>expires</dt>
            <dd>{formatDate(artifact.expires_at)}</dd>
          </div>
          <div>
            <dt>source 인벤토리</dt>
            <dd>
              <StatusBadge tone={inv.tone} value={inv.label} />
            </dd>
          </div>
          <div>
            <dt>기준월 혼합</dt>
            <dd>{artifact.source_set_mixed === true ? "혼합" : artifact.source_set_mixed === false ? "단일" : "—"}</dd>
          </div>
        </dl>

        {yyyymm ? (
          <section className="manifest-section">
            <strong>source_set 기준월</strong>
            <ul className="manifest-kv">
              {Object.entries(yyyymm).map(([kind, ym]) => (
                <li key={kind}>
                  <code>{kind}</code> · {ym ?? "—"}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {activeServing ? (
          <section className="manifest-section">
            <strong>active serving (백업 시점)</strong>
            <ul className="manifest-kv">
              <li>release · {text(activeServing.serving_release_id) ?? "—"}</li>
              <li>snapshot · {text(activeServing.dataset_snapshot_id) ?? "—"}</li>
              <li>match set · {text(activeServing.source_match_set_id) ?? "—"}</li>
            </ul>
          </section>
        ) : null}

        {inventory ? (
          <section className="manifest-section">
            <strong>source_inventory_verification</strong>
            <JsonBlock value={inventory} />
          </section>
        ) : null}

        {sourceMatchSet ? (
          <section className="manifest-section">
            <strong>source_match_set</strong>
            <JsonBlock value={sourceMatchSet} />
          </section>
        ) : null}

        <section className="manifest-section">
          <strong>전체 manifest</strong>
          <JsonBlock value={manifest} />
        </section>
      </div>
    </div>
  );
}

function nested(value: Record<string, unknown>, key: string): Record<string, unknown> | undefined {
  const v = value[key];
  return v && typeof v === "object" ? (v as Record<string, unknown>) : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return value;
  return value.slice(0, 10);
}
