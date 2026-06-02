import { create } from "zustand";

export type RegionWithinRadiusLevel = "sido" | "sigungu" | "emd";

export type RegionsWithinRadiusDraft = {
  lon: number;
  lat: number;
  radius_km: number;
  levels: RegionWithinRadiusLevel[];
};

type RegionsWithinRadiusState = {
  draft: RegionsWithinRadiusDraft;
  result: unknown;
  setDraft: (draft: RegionsWithinRadiusDraft) => void;
  setResult: (result: unknown) => void;
};

const DEFAULT_REGIONS_WITHIN_RADIUS_DRAFT: RegionsWithinRadiusDraft = {
  lon: 126.978,
  lat: 37.5665,
  radius_km: 3,
  levels: ["sigungu", "emd"]
};

export const useRegionsWithinRadiusStore = create<RegionsWithinRadiusState>()((set) => ({
  draft: DEFAULT_REGIONS_WITHIN_RADIUS_DRAFT,
  result: null,
  setDraft: (draft) => set({ draft }),
  setResult: (result) => set({ result })
}));
