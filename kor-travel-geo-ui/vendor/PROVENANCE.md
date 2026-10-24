# 공통 UI vendor 출처

- 저장소: https://github.com/digitie/kor-travel-common
- UI: @kor-travel/ui 0.1.0-dev.6, source 091d4fe1dda8eacf43b453ad39b4f2e42e9e80fc
- UI SHA256: e4945d01d9eb89ed505a95b551899fd0ecf41be66c9ee6b76246701350447e6d
- tokens: @kor-travel/tokens 0.1.0, source 50d2db4c7c7e0154dd863defb62d4b9fa3b5bec3
- tokens SHA256: 22b7613085e55885987ce05720a178b65ac649b097763db650b8c7b8b4acaa84
- PinVi·Map·Weather·Transport 관리자 앱과 같은 검증된 tarball을 사용한다.
- npm pack으로 생성했고 npm ci로 설치했다. tarball 안의 LICENSE/NOTICE/Origin 고지를 보존한다.
- geo의 배치·상태 표현을 비교해 common에서 새로 구현했다. geo의 GPL-3.0-only
  소스/CSS를 common에 복사하지 않았다. 기존 weather 기원 고지는 common에 유지한다.

## MapLibre VWorld 동일 소스의 로컬 소비

- 상류: `https://github.com/digitie/maplibre-vworld-react`
- 고정 커밋: `ffa5523b5f4f101590c2c449845eba37adc11f30`
- Git tree: `3f1c6be9714778d264be3bcff3fe10c5f33c6dec`
- 파일: `maplibre-vworld-react-ffa5523b5f4f.tgz`
- SHA256: `9ef1552b64e3afc2941173eb7fe91a68f6c1bf4dc23e069993f5ef3104a175e9`
- 생성: 로컬 상류 체크아웃에서 `git archive --format=tar.gz --prefix=package/ <고정 커밋>`으로 생성했다. 라이선스는 아티팩트 안에 보존한다.
- 이전 GitHub archive URL과 같은 커밋의 파일을 소비한다. npm 12의 원격 패키지 차단을 해제하지 않으며 앱 API나 제공자 소스를 바꾸지 않는다.
