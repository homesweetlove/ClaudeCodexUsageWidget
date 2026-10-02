[![English](https://img.shields.io/badge/README-English-24292f?style=for-the-badge)](./README.md) [![한국어](https://img.shields.io/badge/README-%ED%95%9C%EA%B5%AD%EC%96%B4-24292f?style=for-the-badge)](./README.ko.md)

# ClaudeCodexUsageWidget

프롬프트를 보내거나 모델 토큰을 소비하지 않고, **Claude Code**와 **OpenAI Codex**가 로컬에 저장한 사용량/요금 제한 정보를 보여주는 가벼운 Windows 데스크톱 위젯입니다.

## 주요 기능

- 어두운 테마의 작고 항상 위에 표시되는 데스크톱 위젯
- 로컬에서 확인 가능한 Claude Code / Codex 사용량 표시
- 로컬 캐시와 세션 메타데이터만 읽음
- **`claude`, `codex`, 모델 API를 실행하지 않음**
- 수동 새로고침 + 자동 새로고침 주기 설정
- 테두리 없는 드래그 가능한 창
- 선택적 Windows 시작 프로그램 등록
- 서드파티 Python 패키지 없음

## 데이터 소스

### Codex
위젯은 `%USERPROFILE%\.codex` 아래의 최근 JSON/JSONL 상태 파일을 확인하고 `rate_limits`, `primary`, `secondary`, `used_percent`, 재설정 시각 같은 제한 정보를 찾습니다. 최신 Codex CLI 세션은 이런 정보를 세션/이벤트 메타데이터에 저장하는 경우가 있습니다.

### Claude Code
위젯은 `%USERPROFILE%\.claude` 아래 최근 JSON/JSONL 상태에서 로컬에 캐시된 제한/사용량 메타데이터를 찾습니다. Claude Code 버전에 따라 로컬 저장 형식이 다르므로 토큰을 소비하지 않고 확인 가능한 기록이 없으면 **Unavailable**로 표시될 수 있습니다.

이 프로젝트는 제한을 확인하기 위해 브라우저 쿠키를 긁거나 세션 토큰을 탈취하거나 숨겨진 프롬프트를 보내지 않습니다.

## Windows 실행

요구사항: Python 3.10+ 및 Tkinter(일반 Windows Python 설치에 포함).

```bat
run.bat
```

또는:

```powershell
pythonw usage_widget.py
```

## Windows 시작 시 자동 실행

등록:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_startup.ps1
```

해제:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_startup.ps1
```

## 설정

첫 실행 시 다음 파일을 생성합니다.

`%LOCALAPPDATA%\ClaudeCodexUsageWidget\config.json`

기본값:

```json
{
  "refresh_seconds": 30,
  "always_on_top": true,
  "window_x": null,
  "window_y": null
}
```

## 참고

- 표시되는 퍼센트는 위젯이 찾은 가장 최신의 일치하는 로컬 상태 기록을 기준으로 합니다.
- CLI가 로컬 파일 형식을 변경해도 대응할 수 있도록 파서는 중첩 JSON을 재귀적으로 탐색합니다.
- `Unavailable`은 신뢰할 수 있는 로컬 사용량 메타데이터를 찾지 못했다는 뜻이며, 계정 할당량이 없다는 뜻은 아닙니다.

## 라이선스

MIT
