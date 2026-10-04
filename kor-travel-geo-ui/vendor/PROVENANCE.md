# 공통 UI vendor 출처

- 저장소: https://github.com/digitie/kor-travel-common
- UI: @kor-travel/ui 0.1.0-dev.3, source 426de4fbad35282bb558712d922c06268e9aba62
- UI SHA256: 03feae21b9e44041b648ba6d0defc3b16b97973ed3c7e70a83b91d279afb2f43
- tokens: @kor-travel/tokens 0.1.0, 같은 source commit
- tokens SHA256: 554ae3f6a18cbf453130b29f8a2d737ddb880101b55e14535cf8d63174b47505
- npm pack으로 생성했고 npm ci로 설치했다. tarball 안의 LICENSE/NOTICE/Origin 고지를 보존한다.
- geo의 배치·상태 표현을 비교해 common에서 새로 구현했다. geo의 GPL-3.0-only
  소스/CSS를 common에 복사하지 않았다. 기존 weather 기원 고지는 common에 유지한다.
