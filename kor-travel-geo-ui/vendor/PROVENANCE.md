> Common 패키지의 최신 정본·출처는 [COMMON-RELEASE.md](COMMON-RELEASE.md)를 따른다. 아래 내용은 이전 채택 시점의 출처 기록이다.

# 공통 UI vendor 출처

## 현재 정본 — integration-12-review (2026-11-17)

common #58(`97f8ed98360518e7afc96e89a5b45a6a478ac955`)이 동결한 `frontend-artifacts.json`의 tgz·원장을
그대로 소비한다. `../common-artifacts.json`은 그 정본의 byte 사본이다. 동일 버전의 bytes를 바꾸거나 독립 pack을
만들지 않으며, 후속 runtime 변경은 새 버전으로 소비한다.

| 패키지 | 정확 버전 | SHA512 | 출처 |
| --- | --- | --- | --- |
| @kor-travel/ui | 0.2.1 | sha512-Yk0TFRE3UUPhHH3ErzgYQtNft+pzy3J5oYZaLwc4MnhUVUT3KPlvCQJDZtj8MvbKdNcVmi4fduxx3Z0FcIfTnw== | common `938d1db` source, `97f8ed9` main push docs artifact `common-release-packs-97f8ed98…` |
| @kor-travel/tokens | 0.1.2 | sha512-IF5qTyPe0LrVFvHRHp2roruudcOO2U96b11zVr0D+Ir1Twsuc2UcAqkYoEL6LfMpDMiq6Xp+CfIDv7N/zkmo/w== | 같음 |
| @kor-travel/toast | 0.1.1 | sha512-R4UI0Mj2c+jQBEg4J+N23z6Ch0QxO5V15Uw+fb/DzJNPkfNKIGgSWhsmbrMFy3oFUL9/NuCNkDIyFT8REsdMNg== | common `vendor/kor-travel-toast-0.1.1.tgz`(97f8ed9), 같은 artifact와 byte 동일 |
| vworld-map-web | 1.0.4 | sha512-yuie33P42nb6pHoR+rI3OTNzXmW/HdIbh6RCEWEooaVTg2lNax8NkakTiadZR/Osw34a6IO0jRxANaE16g6mKA== | maplibre-vworld-react `79b70997` main push CI pack(#33 `vworld://` 스킴 수정) |
| vworld-map-core | 1.0.1 | sha512-Djm14Arr7U0r7Sabj6P0V57CdzWIGaJmecklmY1hwrq1QUZJjMUFgkZfGRFalUo6AFzHEwwzOEzbJPMifGhINw== | 변경 없음 |
| lightningcss | 1.33.0+nativecss.fix.4 | sha512-zDQ03VJE37OlyBrLsRcsEdIVu0T4BXJKDH5y9//To6GlGN2UrKQGERFVAFblkPQ5ZEbhuOp5wpXxGARZNdbQLA== | 변경 없음 |
| @radix-ui/react-focus-scope | 1.3.1+kortravel.fix.2 | sha512-v3XweXrUSZ/QfrMVvYmsAkVNDnvcN21QKbSrViXYf0OQf5Ue9xSgqQIukgGjsYMEBQ5qxQW8fnOC9t1Y0ENPXw== | 변경 없음 |

- ui 0.2.1·tokens 0.1.2·toast 0.1.1은 내장 dependency 정책·검사기만 새 정본(vworld-map-web 1.0.4·rn 1.0.2)으로
  바꿨다. 컴포넌트·CSS·토큰 런타임 파일은 이전 판과 같다.
- vworld-map-web 1.0.4는 `vworld://` 타일 스킴을 `URL.protocol` setter 대신 문자열로 https로 바꿔 Firefox·Safari
  바탕지도 누락을 고친다. 공개 API(`registerVWorldProtocol` 등)는 그대로다.

## 이전 기록 (최초 vendor)

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
