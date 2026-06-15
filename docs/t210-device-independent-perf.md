# T-210 장비 비종속 성능 harness

T-210의 "장비 비종속 성능(fixture 기반 deep rehash·multipart 대용량 회귀·메모리 상한)" 부분을 다룬다. GDAL·전국 데이터·RustFS 서버 없이 합성 fixture로 측정하므로 머신 간 비교가 가능하고, **메모리 상한이 실제 회귀 가드**가 된다. 실측 throughput은 T-063(N150/Odroid), 전국 적재 perf는 T-213/T-214로 분리한다.

## 대상 primitive (실제 코드)

| 항목 | 코드 | 측정 |
|------|------|------|
| deep rehash | `infra.rustfs.sha256_file` (reconcile `deep` 모드가 쓰는 해시) | wall/throughput, peak RSS delta |
| multipart 대용량 | `infra.rustfs._read_file_chunks` (`put_file`/multipart part 스트리밍 iterator) | wall/throughput, 최대 chunk 크기, peak RSS delta |

두 primitive 모두 1 MiB chunk 스트리밍이라 파일 크기와 무관하게 peak RSS가 낮게 유지된다. 전체 파일을 메모리에 적재하는 회귀가 들어오면 즉시 드러난다.

## 실행 (WSL ext4 미러)

```bash
~/ktgvenv/bin/python scripts/benchmark_source_registry_perf.py \
    --rehash-count 8 --rehash-size-mib 64 --multipart-size-mib 512 \
    --output artifacts/perf/t210-device-independent
```

산출물: `artifacts/perf/t210-device-independent/t210-source-registry-perf.json` (objects/throughput/peak_rss_mib 등). throughput 절대값은 머신 종속(참고용), **peak RSS가 파일 크기 대비 낮게 유지되는지가 장비 비종속 판정**이다.

## 상시 회귀 가드 (CI 포함)

`tests/unit/test_t210_source_registry_perf.py` — 16 MiB 합성 파일에 대해 `sha256_file`·`_read_file_chunks`의 tracemalloc peak가 ceiling(6 MiB) 미만임을 단언한다. 빠르고 결정적이며 머신 비종속이라 일반 pytest에 포함된다. 전체 파일 버퍼링 회귀가 들어오면 ceiling을 넘겨 실패한다.
