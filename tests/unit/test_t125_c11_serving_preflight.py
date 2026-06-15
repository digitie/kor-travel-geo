from scripts import run_t125_c11_serving_preflight as t125


def test_sido_code_to_name_uses_current_admin_codes() -> None:
    assert t125.SIDO_CODE_TO_NAME["43"] == "충청북도"
    assert t125.SIDO_CODE_TO_NAME["51"] == "강원특별자치도"
    assert t125.SIDO_CODE_TO_NAME["52"] == "전북특별자치도"
    assert set(t125.SIDO_CODE_TO_NAME) == set(t125.DEFAULT_SIDO_CODES)


def test_address_staging_spec_uses_adr_mng_no_as_candidate_bd_key() -> None:
    spec = t125.address_staging_spec()

    columns = {column.name: column for column in spec.columns}

    assert columns["adr_mng_no"].source_field == "ADR_MNG_NO"
    assert "bd_mgt_sn" not in columns
    assert columns["bul_man_no"].sql_type == "bigint"
    assert spec.geometry_type == "Geometry"


def test_entrance_staging_spec_preserves_representative_priority_field() -> None:
    spec = t125.entrance_staging_spec()

    columns = {column.name: column for column in spec.columns}

    assert columns["entrc_se"].source_field == "ENTRC_SE"
    assert columns["ent_man_no"].sql_type == "bigint"
    assert spec.geometry_type == "Point"


def test_candidate_sql_builds_bd_key_from_adr_mng_no_and_ranks_representative() -> None:
    raw_sql, best_sql = t125.candidate_table_sql()

    assert "a.adr_mng_no AS bd_mgt_sn" in raw_sql
    assert "AND a.bul_man_no = e.bul_man_no" in raw_sql
    assert "AND a.eqb_man_sn = e.eqb_man_sn" in raw_sql
    assert "CASE WHEN raw.entrc_se = '0' THEN 0 ELSE 1 END" in best_sql
    assert "PARTITION BY raw.bd_mgt_sn" in best_sql
