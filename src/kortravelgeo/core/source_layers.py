"""Canonical SHP layer / member-name constants (single source of truth).

These pure-data constants (layer-name tuples and strings) describe the layers
that uploaded source archives are expected to contain. They were historically
defined in the ``loaders`` package, but ``core.source_validation`` needs them to
build its structure-validation profiles, and ``core`` must not import
``loaders`` (layered-architecture contract: a layer may only import LOWER
layers). They therefore live here in ``core`` as the single source of truth; the
loader modules re-export them (``loaders -> core`` is allowed) so existing
references such as ``loaders.juso_map.MASTER_LAYER_NAMES`` keep resolving to the
identical object.
"""

from __future__ import annotations

# --- electronic-map master layers (loaders.juso_map.MASTER_LAYER_NAMES) -----
MASTER_LAYER_NAMES: tuple[str, ...] = (
    "TL_SCCO_CTPRVN",
    "TL_SCCO_SIG",
    "TL_SCCO_EMD",
    "TL_SCCO_LI",
    "TL_KODIS_BAS",
    "TL_SPRD_MANAGE",
    "TL_SPRD_INTRVL",
    "TL_SPRD_RW",
    "TL_SPBD_EQB",
    "TL_SPBD_BULD",
    "TL_SPBD_ENTRC",
)

# --- serving polygon layers (loaders.shp.polygons_loader) -------------------
POLYGON_LAYER_NAMES: tuple[str, ...] = (
    "TL_SCCO_CTPRVN",
    "TL_SCCO_SIG",
    "TL_SCCO_EMD",
    "TL_SCCO_LI",
    "TL_KODIS_BAS",
    "TL_SPRD_MANAGE",
    "TL_SPRD_INTRVL",
    "TL_SPRD_RW",
    "TL_SPBD_BULD",
)

#: DBF-only road interval layer (loaders.shp.polygons_loader).
ROAD_INTERVAL_LAYER_NAME = "TL_SPRD_INTRVL"

# --- zone makarea layer (loaders.sppn_makarea_loader.LAYER_NAME) ------------
ZONE_MAKAREA_LAYER_NAME = "TL_SPPN_MAKAREA"

# --- road-address building shape bundle (loaders.building_shape_bundle) -----
ADDRESS_BUNDLE_LAYER = "TL_SGCO_RNADR_MST"
BUNDLE_ENTRANCE_LAYER = "TL_SPBD_ENTRC"
BUNDLE_CONNECTION_LAYER = "TL_SPOT_CNTC"

# --- detail-dong shape bundle (loaders.extra_shape_layers) ------------------
DETAIL_DONG_POLYGON_LAYER = "TL_SGCO_RNADR_DONG"
DETAIL_DONG_ENTRANCE_LAYER = "TL_SPBD_ENTRC_DONG"
