import { type CandidateAddressLike } from "@/lib/candidate-addresses";
import { Alert, AlertDescription } from "@/components/ui/alert";

/**
 * Human-readable road/parcel address line(s) above the raw JSON response — the response
 * already carries road_address (forward geocode) / road+parcel candidate pairs (reverse
 * geocode), but a raw JSON dump made that easy to miss.
 */
export function CandidateAddressSummary({ candidates }: { candidates: CandidateAddressLike[] }) {
  const rows = candidates.map(addressRow).filter((row): row is { label: string; text: string } => row !== null);
  const geometryTimedOut = candidates.some((candidate) => candidate.geometry_error?.code === "statement_timeout");

  if (rows.length === 0 && !geometryTimedOut) return null;

  return (
    <>
      {geometryTimedOut ? (
        <Alert aria-label="도형 조회 경고" className="mb-3" role="status">
          <AlertDescription>
            일부 도형 조회 시간이 초과되었습니다. 확인된 좌표와 조회된 도형은 유지합니다.
            다시 실행하여 도형을 조회할 수 있습니다.
          </AlertDescription>
        </Alert>
      ) : null}
      {rows.length > 0 ? (
        <ul aria-label="주소 요약" className="mb-3 grid gap-1 text-sm">
          {rows.map((row) => (
            <li className="flex flex-wrap items-baseline gap-2" key={`${row.label}-${row.text}`}>
              <span className="inline-flex shrink-0 items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {row.label}
              </span>
              <span className="min-w-0 break-all">{row.text}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function addressRow(candidate: CandidateAddressLike): { label: string; text: string } | null {
  const address = candidate.address;
  if (!address) return null;
  const text = address.road_address || address.parcel_address || address.full;
  if (!text) return null;
  return { label: address.type === "parcel" ? "지번" : "도로명", text };
}
