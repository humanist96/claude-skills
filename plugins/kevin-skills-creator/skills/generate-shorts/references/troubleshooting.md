# 문제 해결

## ffmpeg·폰트

| 증상 | 해결 |
|------|------|
| "ffmpeg를 찾지 못했다" | Windows `winget install Gyan.FFmpeg`(관리자 권한이 없으면 `python -m pip install imageio-ffmpeg`), macOS `brew install ffmpeg`, Linux `sudo apt-get install -y ffmpeg`. 확인: `python scripts/_vendor/media.py --check` |
| 자막·후크 한글이 네모로 나옴 | `python scripts/_vendor/fonts.py`로 한글 폰트 확인. Windows는 맑은 고딕, macOS는 Apple SD Gothic Neo를 자동으로 쓴다 |
| ffprobe가 없음 | 필요 없다. ffmpeg 출력에서 길이·해상도·오디오를 읽는다 |

## 명령 하나에 시간 제한이 있는 환경(Cowork 등)

명령당 약 45초 제한이 있으면 쇼츠를 한 번에 여러 개 인코딩하다 끊긴다. 구간 확보와 인코딩을 나눈다.

```bash
python ${CLAUDE_SKILL_DIR}/scripts/generate_shorts.py --highlights <W>/highlights.json --video <영상> --output <W>/shorts --download-only
python ${CLAUDE_SKILL_DIR}/scripts/generate_shorts.py --highlights <W>/highlights.json --video <영상> --output <W>/shorts --srt <W>/transcript.srt --only 1
# --only 2, --only 3 … 하나씩
```

- 완성된 쇼츠는 자동으로 건너뛰고(다시 만들려면 `--force`), 확보한 구간은 `<W>/cache/`에 남아 재사용된다
- `--only`로 만든 결과는 기존 metadata.json에 합쳐진다
- 다 끝나고 검사를 통과하면 `<W>/cache/`를 지워 디스크를 정리한다(구간당 수 MB)

## YouTube URL

- 이 스킬은 권리를 가진 영상(내 채널·허락받은 영상)만 다룬다. 다른 사람의 영상은 사용자가 권리를 확인해도 출처·허락 범위를 결과에 적는다
- YouTube가 로그인 확인을 요구하면 우회하지 않는다. 내 영상이면 YouTube Studio에서 원본 영상과 자막을 내려받아 `--video`·`--subs`로 진행한다
- 쿠키는 기본으로 쓰지 않는다. 사용자가 자기 계정 쿠키를 직접 쓰기로 했을 때만 `YT_COOKIE_FILE`(쿠키 파일 경로)을 설정한다. 회사 네트워크 프록시는 `YT_PROXY`
- 자막이 없는 영상은 `prepare_source.py --video … --stt`(faster-whisper, 처음 실행 때 모델을 내려받는다)

## 로그

ffmpeg·yt-dlp가 실패하면 실행 폴더의 `output/logs/error_*.log`에 명령과 오류가 남는다.
