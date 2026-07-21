export type CandidateAddressLike = {
  address?: {
    type?: string | null;
    road_address?: string | null;
    parcel_address?: string | null;
    full?: string | null;
  } | null;
};

export function extractCandidates(result: unknown): CandidateAddressLike[] {
  if (!result || typeof result !== "object") return [];
  const candidates = (result as { candidates?: unknown }).candidates;
  return Array.isArray(candidates) ? (candidates as CandidateAddressLike[]) : [];
}

/**
 * Human-readable road/parcel address line(s) above the raw JSON response — the response
 * already carries road_address (forward geocode) / road+parcel candidate pairs (reverse
 * geocode), but a raw JSON dump made that easy to miss.
 */
export function CandidateAddressSummary({ candidates }: { candidates: CandidateAddressLike[] }) {
  const rows = candidates.map(addressRow).filter((row): row is { label: string; text: string } => row !== null);

  if (rows.length === 0) return null;

  return (
    <ul aria-label="주소 요약" className="mb-3 grid gap-1 text-sm">
      {rows.map((row, index) => (
        <li className="flex flex-wrap items-baseline gap-2" key={`${row.label}-${index}-${row.text}`}>
          <span className="inline-flex shrink-0 items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {row.label}
          </span>
          <span className="min-w-0 break-all">{row.text}</span>
        </li>
      ))}
    </ul>
  );
}

function addressRow(candidate: CandidateAddressLike): { label: string; text: string } | null {
  const address = candidate.address;
  if (!address) return null;
  const text = address.road_address || address.parcel_address || address.full;
  if (!text) return null;
  return { label: address.type === "parcel" ? "지번" : "도로명", text };
}
