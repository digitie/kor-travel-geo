import type { ServingRelease } from "@/lib/api";

export function validDataToken(value: unknown): string | null {
  return typeof value === "string" && /^dd1-[0-9a-f]{32}$/.test(value) ? value : null;
}

function previousActivatedRelease(release: ServingRelease, releases: ServingRelease[]): ServingRelease | undefined {
  // 행의 위치/created_at 순서로 실제 활성화 이력을 추측하지 않는다.
  return releases.find((row) => row.serving_release_id === release.previous_serving_release_id &&
    row.activated_at && ["superseded", "rolled_back"].includes(row.state));
}

export function sameDataAsPrevious(release: ServingRelease, releases: ServingRelease[]): boolean {
  const token = validDataToken(release.data_token);
  const previous = previousActivatedRelease(release, releases);
  return ["active", "superseded", "rolled_back"].includes(release.state) && Boolean(release.activated_at) && token !== null && token === validDataToken(previous?.data_token);
}

export function recentFingerprintsMissing(releases: ServingRelease[]): boolean {
  const active = releases.filter((row) => row.state === "active" && row.activated_at);
  if (active.length !== 1) return false;
  const previous = previousActivatedRelease(active[0], releases);
  return Boolean(previous) && !validDataToken(active[0].data_token) && !validDataToken(previous?.data_token);
}

export function fingerprintFailureNote(release: ServingRelease): string {
  const marker = "data_fingerprint_failed:";
  const start = release.notes?.lastIndexOf(marker) ?? -1;
  // 운영자가 남긴 전체 notes 대신 지문 계산 실패 접미의 사유 코드만 표시한다.
  const reason = start >= 0 ? release.notes!.slice(start).match(/^data_fingerprint_failed:\s*([a-z_]+)\b/) : null;
  return reason ? `data_fingerprint_failed: ${reason[1]}` : "데이터 지문이 없어 동일성을 판정할 수 없습니다.";
}
