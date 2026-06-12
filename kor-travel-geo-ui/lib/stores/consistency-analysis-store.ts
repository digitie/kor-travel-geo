import { create } from "zustand";

type MapCenter = [number, number];

type ConsistencyAnalysisState = {
  selectedCaseCode: string;
  selectedSampleId: string | null;
  selectedSampleIds: string[];
  mapCenter: MapCenter;
  mapZoom: number;
  drawerOpen: boolean;
  visibleColumns: string[];
  setSelectedCase: (caseCode: string) => void;
  setSelectedSample: (sampleId: string | null) => void;
  toggleSample: (sampleId: string) => void;
  clearSelection: () => void;
  setMapView: (zoom: number, center: MapCenter) => void;
  toggleColumn: (column: string) => void;
};

const DEFAULT_COLUMNS = [
  "severity",
  "decision_state",
  "bd_mgt_sn",
  "sig_cd",
  "distance_m",
  "source_kind"
];

export const useConsistencyAnalysisStore = create<ConsistencyAnalysisState>()((set) => ({
  selectedCaseCode: "C4",
  selectedSampleId: null,
  selectedSampleIds: [],
  mapCenter: [127.5, 36.5],
  mapZoom: 7,
  drawerOpen: false,
  visibleColumns: DEFAULT_COLUMNS,
  setSelectedCase: (caseCode) =>
    set({
      selectedCaseCode: caseCode,
      selectedSampleId: null,
      selectedSampleIds: [],
      drawerOpen: false
    }),
  setSelectedSample: (sampleId) =>
    set({
      selectedSampleId: sampleId,
      drawerOpen: sampleId !== null
    }),
  toggleSample: (sampleId) =>
    set((state) => {
      const selected = new Set(state.selectedSampleIds);
      if (selected.has(sampleId)) {
        selected.delete(sampleId);
      } else {
        selected.add(sampleId);
      }
      return { selectedSampleIds: Array.from(selected) };
    }),
  clearSelection: () => set({ selectedSampleIds: [] }),
  setMapView: (zoom, center) => set({ mapZoom: zoom, mapCenter: center }),
  toggleColumn: (column) =>
    set((state) => {
      const visible = new Set(state.visibleColumns);
      if (visible.has(column)) {
        visible.delete(column);
      } else {
        visible.add(column);
      }
      return { visibleColumns: Array.from(visible) };
    })
}));
