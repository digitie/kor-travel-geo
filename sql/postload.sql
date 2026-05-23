VACUUM (ANALYZE) tl_spbd_buld;
VACUUM (ANALYZE) tl_spbd_entrc;
VACUUM (ANALYZE) tl_sprd_manage;

REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target;
ANALYZE mv_geocode_target;
