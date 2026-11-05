# Pinvi650 운영 불일치 읽기 전용 대조

이 문서는 최종 prod 검증 담당 Claude Code의 진단 자료다. 이번 PR에서는 운영에
접속·배포·적재·MV 갱신·테스트를 수행하지 않았다. 이 문서를 실행했다는 증거도 아니다.
운영650은 열린 상태로 유지하며, 아래 비교가 끝나기 전 완료나 배포 회귀로 단정하지 않는다.

## 확인된 기준

202605 보존 공식 Juso의 하회종가길67행을 원문 그대로 실제 적재기·generated column·
정본 MV·검색 SQL·공개키 인증 v2 HTTP에 연결했다. 약칭/정식40은 각각1행이고,
40-1/68은 별도 주소, 없는40-2/999와 지하40은0행이다. 좌표는 원문에 없어 추가하지 않았다.
원문 관리번호는 이 자료에서26자리이며 잘라내거나25자리로 보정하지 않는다.

- 40: 47170340472227900004000000
- 40-1: 47170340472227900004000001
- 68: 47170340472227900006800000

실제 Pinvi API/브라우저도 Chromium·Firefox 각각 다섯 검색을 통과했다.
이 결과는 보존 원천의 최신 코드 성공이며 현재 운영 원천·서빙 release·worker 상태를
입증하지 않는다. 원래40을 다른 번호로 치환하거나 가까운 번호로 fallback하지 않는다.

## 실행 코드·요청 식별

실제 요청을 받는 Geo endpoint/worker/image의 revision·image digest·프로세스 시작 시각을
기존 운영 도구에서 확인한다. Pinvi/Map revision은 Geo revision을 대신하지 않는다.
파일이 바뀐 뒤 worker가 재시작되지 않은 상태도 구분한다.

아래 Python은 같은 환경에서 새로 import한 파일의 hash만 출력한다.
이미 실행 중인 API worker의 메모리 상태까지 증명하지 않으며 secret·DSN을 출력하지 않는다.

    import hashlib, inspect, json
    from pathlib import Path
    from kortravelgeo import __version__
    from kortravelgeo.core import normalize
    from kortravelgeo.infra import search_repo, sql
    modules = (normalize, search_repo, sql)
    print(json.dumps({
        "package_version": __version__,
        "source_sha256": {
            module.__name__: hashlib.sha256(
                Path(inspect.getfile(module)).read_bytes()
            ).hexdigest()
            for module in modules
        },
    }, ensure_ascii=False, indent=2))

v2의 실제 요청 JSON과 응답 input/status/total/candidates를 함께 보존한다.
공개키는 기존 승인된 비공개 자격 흐름으로 전달하며 본문·로그에 출력하지 않는다.

    {"query":"경북 안동시 풍천면 하회종가길 40","type":"address","page":1,"size":8}

같은 endpoint에 정식명도 대조한다. type 생략의 기본은 address지만,
road/place/category나 남은 region hint는 다른 조건이다. 코드에는 검색 결과 음성
캐시가 없으며 dataset metadata cache는 검색 결과 cache가 아니다.

## 원천과 서빙 MV

검증된 같은 Geo DB·같은 search_path에서 실행할 읽기 전용 SQL이다.
존재하지 않는 relation/컬럼 오류를0건으로 바꾸지 말고 실제 오류 종류로 기록한다.
운영의 도로 총수가67과 다르다고 곧바로 오류라고 판단하지 않는다.

    BEGIN TRANSACTION READ ONLY;
    SET LOCAL statement_timeout = '5s';
    SELECT current_setting('transaction_read_only'), current_schema();
    SHOW search_path;

    SELECT 'raw' AS stage, count(*) AS road_rows,
           count(*) FILTER (WHERE buld_mnnm=40 AND buld_slno=0 AND buld_se_cd='0'
             AND ctp_kor_nm='경상북도' AND sig_kor_nm='안동시'
             AND emd_kor_nm='풍천면') AS exact_40_rows
      FROM tl_juso_text WHERE rn_nrm='하회종가길'
    UNION ALL
    SELECT 'serving', count(*),
           count(*) FILTER (WHERE buld_mnnm=40 AND buld_slno=0 AND buld_se_cd='0'
             AND si_nm='경상북도' AND sgg_nm='안동시' AND emd_nm='풍천면')
      FROM mv_geocode_target WHERE rn_nrm='하회종가길';

    SELECT bd_mgt_sn, rncode_full, rn_nrm, buld_mnnm, buld_slno, buld_se_cd,
           ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm, bjd_cd,
           source_yyyymm, source_file, loaded_at
      FROM tl_juso_text
     WHERE rn_nrm='하회종가길' AND buld_mnnm IN (40,68)
     ORDER BY bd_mgt_sn;

    SELECT bd_mgt_sn, rncode_full, rn_nrm, buld_mnnm, buld_slno, buld_se_cd,
           si_nm, sgg_nm, emd_nm, li_nm, bjd_cd, pt_source
      FROM mv_geocode_target
     WHERE rn_nrm='하회종가길' AND buld_mnnm IN (40,68)
     ORDER BY bd_mgt_sn;
    COMMIT;

## 결과별 다음 확인

- raw에40이 있지만 serving에는 없으면 적재 완료와 MV 게시 상태를 구별한다.
  등록 원천·source month·활성 release를 먼저 확인하고 대용량 재적재를 중복 제출하지 않는다.
- serving의 번호·지하 여부·지역이 기대와 다르면 실제 필드/동일 원천을 대조한다.
  NULL을0으로 바꾸거나 번호 조건을 제거하지 않는다.
- 같은 입력의 SDK/DB 검색은 성공하고 HTTP만 실패하면 endpoint/worker의 실행 코드,
  입력 type/hints·연결 DB/search_path·활성 serving release를 대조한다.
- 보존202605와 실제 원천이 다르면 현재 원천·월/일 변동을 검증한다.
  도로67건이라는 수만으로 데이터가 같다고 보지 않는다.
- 좌표 NULL은 최신 코드의 주소 후보 삭제 조건이 아니다. 가짜 좌표를 넣지 않는다.

실제 운영의 원래 SRCH-004가 통과하고 원인이 확인된 뒤 Pinvi650과643 체크를 갱신한다.
운영 효과를 확인하기 전에는 보존 원천의 WSL 통과를 근거로 테스트 기대값을 뒤집지 않는다.

## 이 PR의 런타임 기준 hash

다음은 Geo d46dfa1과 같은 src tree에서 계산했다. 파일 hash는 worker·image 식별을
대체하지 않는다.

    src/kortravelgeo/core/normalize.py: e92924ce4aa63262ec59290fc2d40307d66e7e21771f728e975143b7ccd61a2f
    src/kortravelgeo/infra/search_repo.py: 9126eee7f5c4412e71316ece680794d143613f28ead2a6c426f878b11d731fd4
    src/kortravelgeo/infra/sql.py: 8a86955fed0de4d7bfdc0c775c3936aa9366ad8443905756fd557cdd017345dd
