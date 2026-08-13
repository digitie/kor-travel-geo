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
