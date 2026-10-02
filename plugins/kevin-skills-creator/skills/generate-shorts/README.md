# generate-shorts

> 내가 가진 롱폼 영상에서 세로 쇼츠(1080x1920 mp4)와 카드뉴스를 만든다. 구간 선택·제목·후크·자막은 Claude가 정하고, 대본 준비·인코딩·검사는 스크립트가 한다.
> 플러그인: `kevin-skills-creator` · 책 9장

## 하는 일

- **원본·대본 준비**(`prepare_source.py`): 다음 세 가지 입력을 같은 대본 파일로 만든다.
  - 로컬 영상 + 자막(.srt·.vtt)
  - 로컬 영상 + 음성 인식(faster-whisper, 선택 설치)
  - 권리를 확인한 내 YouTube 영상
- **후보 추리기**(`select_highlights.py`): 규칙 점수로 후보 구간을 추린다. 고르는 일은 Claude가 내용을 읽고 한다.
- **하이라이트 검사**(`validate_highlights.py`): 인코딩 전에 다음을 잡는다.
  - 15~60초 범위, 원본 길이 초과, 구간 겹침
  - 제목 28자·후크 20자 초과
  - 자막 시간 역전·범위 초과, 문장 경계 어긋남
- **쇼츠 생성**(`generate_shorts.py`): 세로 변환(fit_blur·crop·fit), 후크 오버레이, 한글 자막을 합성한다. Windows 맑은 고딕과 경로를 처리한다.
- **완성 검사**(`verify_short.py`): 해상도, 길이, 오디오, 검은 화면을 검사한다. 마지막으로 Claude가 프레임을 눈으로 확인한다.
- **카드뉴스**(`card_news.py`): 요약 카드 이미지 세트와 카드 쇼츠를 만든다. 나레이션은 edge-tts를 쓴다.

## 데모

| 이렇게 요청하면 | 이런 결과가 나온다 |
|-----------------|--------------------|
| "이 강의 영상(mp4)이랑 자막으로 쇼츠 2개 만들어줘" | 독립적으로 이해되는 구간 2개를 골라 1080x1920 쇼츠 2개, 제목·후크·설명 문구, 검사 통과 |
| "자막 없는 발표 영상인데 쇼츠로" | 음성 인식으로 대본을 만든 뒤 같은 흐름(faster-whisper 필요) |
| "이 영상 내용 카드뉴스로 정리해줘" | 카드 PNG 3~5장 + 나레이션 카드 쇼츠 |
| 다른 사람 채널 링크만 주고 "쇼츠 만들어줘" | 권리를 먼저 확인하고, 확인이 안 되면 내려받지 않는다 |

실습 샘플은 `practice-samples` 스킬의 `shorts-lecture` 세트(자체 제작 강의 영상·자막)와 `shorts-answer-key` 세트(정답표)다.

## 요구사항

| 항목 | 필수 | 비고 |
|------|:---:|------|
| Python 3.10+ | ✅ | |
| ffmpeg | ✅ | Windows `winget install Gyan.FFmpeg` 또는 `pip install imageio-ffmpeg`(관리자 권한 불필요). ffprobe는 없어도 된다 |
| Pillow | ✅ | 카드뉴스 |
| 한글 폰트 | ✅ | Windows 맑은 고딕, macOS Apple SD Gothic Neo, Linux Noto CJK·나눔 |
| faster-whisper | | 자막 없는 영상(`--stt`) |
| yt-dlp | | 권리를 확인한 YouTube URL 입력 |
| edge-tts | | 카드뉴스 나레이션(인터넷 필요) |

```bash
python scripts/_vendor/doctor.py --skills generate-shorts
```

## 지원 환경

| Claude Code Win | Claude Code Mac | Cowork | claude.ai |
|:-:|:-:|:-:|:-:|
| 지원 | 지원 | 지원(명령 시간 제한 — 나눠 실행) | 지원(업로드 시 `_vendor` 포함 필요, ffmpeg 있는 환경) |

## 커스터마이즈 포인트

플러그인 설치 폴더를 고치지 말고 오버라이드 폴더에 파일을 둔다. 규약은 `references/_shared/overrides.md`에 있다.

- 팀 공용: `<작업 폴더>/.claude/claude-skills/generate-shorts/`
- 개인 기본값: `~/.claude/claude-skills/generate-shorts/`

| 수준 | 대상 | 파일(스킬 폴더 기준 상대 경로) | 형식 | 예시 |
|:---:|------|-------------------------------|------|------|
| L0 | 기본 레이아웃·쇼츠 개수 | `settings.yaml` → `layout`·`count` | fit_blur·crop·fit / 숫자 | `layout: crop` |
| L1 | 영상·자막·후크 설정 | `templates/config_template.yaml`을 복사한 `config.yaml`(`--config`) | YAML | 자막 크기 60, 후크 3초 |
| L1 | 채널 문구·해시태그 | `references/channel.md` | 마크다운 | 채널명, 고정 해시태그 3개, 금지 표현 |

다음 보호 규칙은 오버라이드로 바뀌지 않는다.

- 원본 덮어쓰기 금지
- 비밀 정보 파일 기록 금지(쿠키·계정 정보)
- 외부 전송·게시 전 확인(이 스킬은 업로드하지 않는다)
- 권리를 확인하지 않은 영상은 내려받지 않는다
- 로그인 확인·봇 차단을 우회하지 않는다

## 데이터 흐름

| 데이터 | 외부 전송 경로 |
|--------|----------------|
| 로컬 영상·자막 | 없음(로컬 처리). 대본 텍스트는 Claude가 읽는다 |
| 음성 인식(--stt) | 없음(로컬 faster-whisper). 처음 실행 때 모델을 내려받는다 |
| YouTube URL | YouTube에서 자막·하이라이트 구간만 내려받는다 |
| 카드뉴스 나레이션 | Microsoft Edge TTS 서비스로 문장 전송 |

## 변경 이력

| 버전 | 변경 |
|------|------|
| 2.0.0-alpha.1 | 다음을 바꿨다. <ul><li>로컬 영상 입력(자막·음성 인식)을 추가하고 YouTube는 권리를 확인한 영상만 받게 했다</li><li>YouTube 로그인 확인을 피하려던 장치(브라우저 쿠키 자동 사용·User-Agent 위장·무작위 지연)를 삭제했다</li><li>Windows에서 ffmpeg(imageio-ffmpeg 포함)·맑은 고딕·필터 경로·python 실행이 동작하게 했다</li><li>CRLF 자막 파싱을 고쳤다</li><li>validate_highlights·verify_short를 추가했다</li><li>제3자 방송 영상 자막이던 실습 자료를 자체 제작 강의 영상으로 바꿨다</li><li>비교 평가에서 찾은 결함을 고쳤다: 자막·후크 합성 실패를 성공으로 숨기던 동작, Windows에서 두 줄 후크 사이에 빈 줄이 생기던 문제, 카드 제목의 획 많은 한글이 뭉개지던 문제, 제목 전체를 붙인 긴 해시태그, 메모리 부족 시 음성 인식 중단</li></ul> |
| 1.6.0 | 명령당 시간 제한 환경 대응(다운로드·인코딩 분리) |
| 1.5.0 | 카드뉴스 나레이션 |
