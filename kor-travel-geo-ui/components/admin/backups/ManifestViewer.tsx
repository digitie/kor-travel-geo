"use client";

import { JsonBlock } from "@/components/ui/JsonBlock";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import {
  inventoryTone,
  nestedRecord,
  textValue
} from "@/components/admin/backups/manifest-utils";
import type { BackupArtifact } from "@/lib/api";

/**
 * Backup manifest reproducibility viewer (T-252): surfaces the T-237/T-240 manifest context —
 * source_set reference months, source-inventory verification (vs the active match set at backup
 * time), active serving release/snapshot/match-set ids, retention/expiry — plus the raw manifest.
 * 접근명 "백업 manifest 재현성 뷰어"는 spec 계약이라 DialogTitle 텍스트로 유지한다.
 */
export function ManifestViewer({
  artifact,
  onClose
}: {
  artifact: BackupArtifact;
  onClose: () => void;
}) {
  const manifest = artifact.manifest ?? {};
  const inventory = nestedRecord(manifest, "source_inventory_verification");
  const activeServing = nestedRecord(manifest, "active_serving");
  const sourceMatchSet = nestedRecord(manifest, "source_match_set");
  const inv = inventoryTone(artifact.source_inventory_ok);
  const yyyymm = artifact.source_set_yyyymm ?? null;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto" size="lg">
        <DialogHeader>
          <DialogTitle>백업 manifest 재현성 뷰어</DialogTitle>
          <DialogDescription>{artifact.display_name ?? artifact.artifact_id}</DialogDescription>
        </DialogHeader>

        <KeyValueGrid
          items={[
            {
              label: "retention",
              value: artifact.retention_class ?? "default",
              help: (
                <>
                  API 필드 <code>retention_class</code> — 백업본 보존 정책 분류.
                </>
              ),
              helpLabel: "retention 도움말"
            },
            { label: "expires", value: formatDate(artifact.expires_at) },
            {
              label: "source 인벤토리",
              value: <StatusBadge tone={inv.tone} value={inv.label} />,
              help: "백업 시점의 활성 match set 대비 원천 파일 인벤토리 검증 결과.",
              helpLabel: "source 인벤토리 도움말"
            },
            {
              label: "기준월 혼합",
              value:
                artifact.source_set_mixed === true
                  ? "혼합"
                  : artifact.source_set_mixed === false
                    ? "단일"
                    : "—"
            }
          ]}
        />

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
              <li>release · {textValue(activeServing.serving_release_id) ?? "—"}</li>
              <li>snapshot · {textValue(activeServing.dataset_snapshot_id) ?? "—"}</li>
              <li>match set · {textValue(activeServing.source_match_set_id) ?? "—"}</li>
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
      </DialogContent>
    </Dialog>
  );
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return value;
  return value.slice(0, 10);
}
