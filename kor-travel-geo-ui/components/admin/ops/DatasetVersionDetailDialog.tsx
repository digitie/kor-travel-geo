"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { getErrorMessage, postJson, type ServingRelease } from "@/lib/api";

type DatasetVersionPreview = {
  status: string;
  query_id: string;
  available: boolean;
  // known_version을 보냈을 때만 채워진다 — "현재 활성 릴리스"가 이 다이얼로그가 보여주는
  // release와 같은지 구분하는 신호(아래 changed/known_version_found로 노출).
  changed?: boolean;
  known_version_found?: boolean;
  current?: {
    version_token: string;
    activated_at: string;
    change_type: "full" | "delta";
    reference_months?: Record<string, string>;
    reference_months_mixed?: boolean;
  };
};

/**
 * T-291d: 서빙 릴리스 1건의 데이터셋 버전 상세 — 내부 id 상관, 원본 source_set(정규화 전),
 * 정규화된 기준월, 실제 `POST /v2/dataset/version` 응답 미리보기(trusted-proxy 경유), curl
 * 스니펫. 미리보기 한계: trusted-proxy 경로는 `require_public_api_key`를 신뢰 클라이언트로
 * 우회하므로, 이 미리보기가 검증하는 것은 응답 본문의 공개 범위이지 인증 동작이 아니다
 * (ADR-067 D6). 인증 포함 검증은 live e2e가 담당한다.
 */
export function DatasetVersionDetailDialog({
  release,
  onClose
}: {
  release: ServingRelease;
  onClose: () => void;
}) {
  const [preview, setPreview] = useState<DatasetVersionPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  async function loadPreview() {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      // known_version을 이 release의 값으로 보낸다 — 그래야 응답의 changed/known_version_found로
      // "현재 활성 릴리스가 바로 이 release인지"를 판단할 수 있다. version_token이 없는(구버전)
      // 행은 known_version 없이 호출하고, 그 사실을 아래 안내문에서 밝힌다.
      const body = release.version_token ? { known_version: release.version_token } : {};
      const result = await postJson<DatasetVersionPreview>("/v2/dataset/version", body);
      setPreview(result);
    } catch (error) {
      setPreviewError(getErrorMessage(error));
    } finally {
      setPreviewLoading(false);
    }
  }

  const curl = [
    'curl -X POST "https://<host>/v2/dataset/version"',
    '-H "Content-Type: application/json"',
    '-H "X-KTG-API-Key: <키>"',
    `-d '{"known_version":"${release.version_token ?? ""}"}'`
  ].join(" ");

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto" size="lg">
        <DialogHeader>
          <DialogTitle>데이터셋 버전 상세</DialogTitle>
          <DialogDescription>{release.serving_release_id}</DialogDescription>
        </DialogHeader>

        <KeyValueGrid
          items={[
            { label: "release", value: release.serving_release_id },
            { label: "snapshot", value: release.dataset_snapshot_id },
            { label: "state", value: <StatusBadge value={release.state} /> },
            { label: "release_kind", value: release.release_kind },
            {
              label: "version_token",
              value: release.version_token ?? "-",
              help: (
                <>
                  외부 <code>POST /v2/dataset/version</code>이 반환하는 것과 동일한 값
                  (ADR-067 D1 — <code>dv1-</code> + release id sha256 prefix).
                </>
              ),
              helpLabel: "version_token 도움말"
            },
            {
              label: "change_type",
              value: release.change_type ?? "-",
              help: "full=전체 재동기화, delta=증분 갱신 (ADR-067 D2).",
              helpLabel: "change_type 도움말"
            },
            {
              label: "기준월 혼합",
              value:
                release.reference_months_mixed === true ? (
                  <Badge tone="warn">혼합</Badge>
                ) : release.reference_months_mixed === false ? (
                  "단일"
                ) : (
                  "—"
                )
            }
          ]}
        />

        {release.reference_months ? (
          <section className="manifest-section">
            <strong>reference_months (정규화 결과)</strong>
            <ul className="manifest-kv">
              {Object.entries(release.reference_months).map(([kind, ym]) => (
                <li key={kind}>
                  <code>{kind}</code> · {ym}
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <p className="form-note">
            기준월을 정규화하지 못했습니다 — version_token만이 신뢰 신호입니다.
          </p>
        )}

        <section className="manifest-section">
          <strong>원본 source_set (snapshot, 정규화 전)</strong>
          <JsonBlock value={release.source_set ?? {}} />
        </section>

        <section className="manifest-section">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong>외부 응답 미리보기</strong>
            <Button
              aria-busy={previewLoading || undefined}
              disabled={previewLoading}
              onClick={() => void loadPreview()}
              size="sm"
              type="button"
              variant="outline"
            >
              {previewLoading ? "호출 중…" : "POST /v2/dataset/version 호출"}
            </Button>
          </div>
          <p className="form-note">
            trusted-proxy 경유 실제 호출입니다 — 응답 본문의 공개 범위만 검증하며, 인증(공개
            API 키) 동작은 검증하지 않습니다.{" "}
            {release.version_token ? (
              <>
                <code>known_version</code>에 이 release의 <code>version_token</code>을 실어
                보내므로, 아래 <code>current</code>는 이 release가 여전히 현재 서빙 중인지를
                가리킵니다.
              </>
            ) : (
              "이 release는 version_token이 없어 known_version 없이 호출합니다 — 아래 current는 항상 현재 활성 릴리스이며, 이 release와 무관할 수 있습니다."
            )}
          </p>
          {previewError ? <p className="form-note warn">{previewError}</p> : null}
          {preview && preview.changed === true ? (
            <p className="form-note warn">
              이 release는 더 이상 현재 활성 릴리스가 아닙니다 — 아래 <code>current</code>는
              지금 서빙 중인 다른 릴리스({preview.current?.version_token ?? "?"})입니다.
            </p>
          ) : null}
          {preview && preview.changed === false ? (
            <p className="form-note">
              이 release가 지금도 현재 활성 릴리스입니다 — 아래 <code>current</code>가 이
              release와 동일합니다.
            </p>
          ) : null}
          {preview ? <JsonBlock value={preview} /> : null}
        </section>

        <section className="manifest-section">
          <strong>curl 스니펫</strong>
          <CopyableTextBlock text={curl} />
        </section>
      </DialogContent>
    </Dialog>
  );
}

/** 평문 복사(JsonBlock은 JSON.stringify를 거쳐 curl 스니펫엔 부적합) — 복사 UX는 동일. */
function CopyableTextBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    };
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (resetTimer.current) clearTimeout(resetTimer.current);
      resetTimer.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      const node = preRef.current;
      if (node) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
      }
    }
  }

  return (
    <div className="group relative min-w-0">
      <pre className="json-box" ref={preRef}>
        {text}
      </pre>
      <button
        type="button"
        aria-label="curl 복사"
        onClick={() => void copy()}
        className="absolute top-2 right-2 inline-flex size-8 items-center justify-center rounded-control bg-white/10 text-white/70 opacity-0 transition-opacity duration-fast group-hover:opacity-100 hover:bg-white/20 hover:text-white focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}
