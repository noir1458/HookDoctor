# HookDoctor 0.3.0

Linux x86-64/glibc에서 LD_PRELOAD의 ELF 심볼과 loader binding을 조사하는 CLI.
구현·검증 계약은 [AGENTS.md](AGENTS.md)에 있습니다. 함수 호출 여부는 일반 CLI에서 항상
`UNKNOWN`이며, binding 확인만으로 함수가 실행되었다고 말하지 않습니다.

중간발표용 v0.3의 기능 범위는 동결했습니다. 지원 진단은 `open`/`open64` 불일치 한
종류이며, 변경 범위를 넓히기보다 현재 기능의 재현성과 검증 근거를 유지합니다.

## Apple Silicon 개발 환경

Git과 Docker Desktop이 필요합니다. 처음 받는 경우:

```bash
git clone https://github.com/CAU-2026-2-capstone-5-team-8/HookDoctor.git
cd HookDoctor
```

Docker Desktop을 실행한 뒤 프로젝트 루트에서:

```bash
bash scripts/dev.sh build
bash scripts/dev.sh bash scripts/verify.sh
```

이 명령은 fixture를 새로 빌드하고, 전체 테스트·help/version·데모를 실행합니다.
한 단계라도 실패하면 비정상 종료합니다. 단계별 실행은 아래 명령을 사용합니다.
생성된 ELF 파일은 Git에 포함하지 않으며, 검증 로그는 `docs/evidence/`에 저장됩니다.
검증을 다시 실행하면 PID·실행 시간 등이 바뀌어 기존 로그 파일에 변경이 생길 수 있습니다.

`Dockerfile`은 Ubuntu 24.04와 시스템 GCC/Make/binutils/Python만 설치합니다.
이미지 빌드와 실행 모두 `linux/amd64`를 지정합니다. Apple Silicon에서는 Docker의
에뮬레이션을 사용하므로 native x86-64 하드웨어 검증과 구분해야 합니다.
소스와 ELF 산출물은 현재 프로젝트 폴더에 저장되고 컨테이너에서는 `/workspace`로 보입니다.
다른 Capstone 저장소를 마운트하지 않습니다. 컨테이너는 호스트 UID/GID로 실행됩니다.
최초 이미지 빌드에는 인터넷이 필요하며 이후 실행은 `--network none`입니다.

```bash
bash scripts/dev.sh make -C fixtures all
bash scripts/dev.sh python3 -m unittest discover -s tests -v
bash scripts/dev.sh python3 -m hookdoctor --help
bash scripts/dev.sh bash scripts/demo.sh
bash scripts/dev.sh bash scripts/verify.sh  # fixture, 전체 테스트, 도움말, 데모와 증거 저장
bash scripts/dev.sh  # 대화형 개발 셸
```

일반 Linux x86-64/glibc에서도 시스템 도구가 설치되어 있으면 루트에서:

```bash
make -C fixtures all
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m hookdoctor --help
bash scripts/demo.sh
```

직접 실행 환경의 필수 도구는 Python 3.11 이상, GCC/cc, GNU Make, GNU readelf/nm,
glibc 개발 헤더입니다. macOS에서 직접 컴파일한 Mach-O 파일은 대상이 아니므로 Docker
경로를 사용합니다. 정적 링크 지원이 없으면 사유를 기록하고 no-export 보조 사례를 사용합니다.

Docker 데몬/이미지 문제가 생기면 `scripts/dev.sh`가 `ENVIRONMENT` 오류를 출력합니다.
`exec format error`는 플랫폼/에뮬레이터를 먼저 확인하고, fixture의 심볼 또는 binding 검증
실패는 `docs/evidence/fixture-gate`의 실제 도구 출력과 구분해서 조사합니다.
Docker Desktop 설정을 자동으로 변경하거나 privileged 컨테이너를 사용하지 않습니다.

검증 결과와 지원 한계는 [docs/EVIDENCE.md](docs/EVIDENCE.md), 자료는
[docs/SOURCES.md](docs/SOURCES.md)에 기록합니다.

기능 동결 커밋 `576de8f`를 빌드 산출물 없는 별도 체크아웃에서 재검증했습니다.
전체 40개 테스트 통과, 데모 3.340초이며
[재현 기록](docs/evidence/reproduction/576de8f/metadata.json)에 실제 환경과 명령을 남겼습니다.
Docker 이미지 빌드는 기존 레이어 캐시를 사용했습니다. 네이티브 Intel/AMD Linux
교차 검증은 아직 수행하지 않았습니다.

## CLI 사용

```bash
bash scripts/dev.sh python3 -m hookdoctor check \
  --lib ./fixtures/libhook_open.so --symbol open -- ./fixtures/app_large

bash scripts/dev.sh python3 -m hookdoctor check \
  --lib ./fixtures/libhook_fixed.so --symbol open64 --json -- ./fixtures/app_large
```

`--` 뒤는 그대로 전달되는 target argv입니다. `./app` 또는 절대 경로의 ELF 실행 파일이
필요합니다. PATH 검색과 shell script는 지원하지 않습니다. `--symbol`은 버전 접미사가
없는 정확한 동적 심볼 이름 하나이며, target은 check마다 최대 한 번 실행됩니다.
기본 제한은 target 10초, 각 수집 도구 5초, 각 subprocess의 stdout+stderr 합계 5 MiB입니다.
`--timeout`과 `--max-output-bytes`로 target 시간 및 모든 수집 출력 상한을 지정합니다.
공백·콜론이 들어가는 hook 경로는 지원하지 않습니다.

- `EXPECTED_BINDING_OBSERVED`: 요청한 심볼의 target→hook binding이 확인됨. 함수 진입 증거는 아님.
- `SYMBOL_VARIANT_MISMATCH`: ELF와 target→libc binding이 모두 확인된 경우의 **조건부** 설명.
- 정상적으로 수집한 동적 target은 `INCONCLUSIVE`, 호출 여부는 항상 `UNKNOWN`.
- 검증된 일반 정적 ET_EXEC는 실행하지 않고 `NOT_APPLICABLE`을 반환.

| 종료 코드 | 의미 |
| --- | --- |
| 0 | 분석 완료; target 자체의 실패/시그널도 보고서에 따로 보존 |
| 2 | CLI 구문 또는 옵션 오류 |
| 3 | 입력·지원 환경·수집·실행 시작 오류 |
| 4 | target 또는 수집 도구 시간 초과 |
| 5 | 캡처 출력 상한 초과 |

`--json`은 유효하게 파싱된 요청에 대해 오류도 단일 schema v0.3 문서로 출력합니다.
전체 환경은 기록하지 않습니다. target에는 단일 절대 `LD_PRELOAD`와 `LD_DEBUG=libs,bindings`를
설정하고 `LD_LIBRARY_PATH`, `LD_BIND_NOW`는 보존합니다. loader 로그는 인증된 관측 채널이
아니므로 target의 stderr를 신뢰할 수 없는 상황에 대한 보안 도구로 사용하지 않습니다.

MVP에는 GUI, 서버, 자동 코드 수정, 실행 전후 자동 재시도, child-process 진단이 없습니다.
`fixtures/expected_cases.json`과 marker 해석은 테스트·데모만 사용합니다. raw evidence의
개별 발췌는 최대 4096 UTF-8 bytes, 합계는 최대 65536 bytes이며 전체 target 캡처는 별도
실행 상한 내에서 `run.stdout`/`run.stderr`에 보존됩니다. 원문 로그가 크면 발췌에는 일부만 보입니다.

Python 패키지 설치 없이 `PYTHONPATH=src python3 -m hookdoctor`로 사용할 수 있습니다.
선택적으로 설치하면 pyproject.toml의 console entry point가 같은 CLI를 `hookdoc`로 노출합니다.
