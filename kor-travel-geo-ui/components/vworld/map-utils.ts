import type { Map as MapLibreMap } from "maplibre-gl";

/**
 * True when `map` can still service getLayer/getSource. maplibre sets the public `_removed`
 * flag and deletes the map's `style` on Map.remove(); getLayer/getSource read `style` and
 * throw once it is gone. Both are public Map members, but `style` is typed as always-present,
 * so probe through a narrow cast. `_removed` is the canonical teardown signal; the `style`
 * check additionally covers a transient styleless window (setStyle(null) in flight). Revisit
 * on maplibre-gl major upgrades.
 */
export function isMapUsable(map: MapLibreMap): boolean {
  const internals = map as unknown as { _removed?: boolean; style?: unknown };
  return !internals._removed && Boolean(internals.style);
}
