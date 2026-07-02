---
name: dashboard
description: Hi-Flow 실시간 운영 대시보드 서버를 실행하고 브라우저로 연다. 사용자가 "대시보드 켜줘", "대시보드 실행", "운영 화면 보여줘"라고 하면 사용한다.
---

# Hi-Flow 대시보드 실행

1. 이미 실행 중인지 확인한다:
   ```powershell
   try { Invoke-RestMethod http://localhost:8000/api/telemetry -TimeoutSec 2 | Out-Null; "RUNNING" } catch { "STOPPED" }
   ```
2. `STOPPED`이면 프로젝트 루트에서 `python dashboard_server.py`를 백그라운드로 실행하고,
   위 확인 명령이 `RUNNING`이 될 때까지 기다린다 (최대 10초).
3. 기본 브라우저로 연다:
   ```powershell
   Start-Process http://localhost:8000
   ```
4. `/api/telemetry` 응답에서 플랫폼 상태·배터리·진행률을 읽어 한 줄로 보고한다.

참고
- 서버는 표준 라이브러리만 사용하므로 pip 설치가 필요 없다.
- 3D 히트맵은 Plotly CDN을 사용하므로 인터넷 연결이 필요하다.
- 서버 종료가 필요하면 실행 중인 백그라운드 작업을 중지하면 된다 (포트 8000).
