---
name: generate-shorts
description: 내가 가진 롱폼 영상(로컬 mp4·mov, 또는 권리를 확인한 내 채널 YouTube 영상)에서 세로 쇼츠·릴스·틱톡 영상 파일(1080x1920 mp4)을 만든다. 자막 파일이나 음성 인식으로 대본을 준비하고, 규칙 점수로 추린 후보에서 Claude가 독립적으로 이해되는 구간을 골라 제목·후크·자막을 다시 쓴 뒤, ffmpeg로 세로 변환·후크·한글 자막을 합성하고, 하이라이트와 완성 영상을 스크립트로 검사한다. 강의·화면 녹화·슬라이드처럼 가로가 넓은 영상도 잘리지 않게 바꾸며, 영상 내용을 요약한 카드뉴스 이미지와 카드 쇼츠도 만든다. "이 강의 영상으로 쇼츠 만들어줘", "내 유튜브 영상 하이라이트 쇼츠로", "릴스용 세로 영상", "영상 내용 카드뉴스로 정리" 같은 요청에 쓴다. 쇼츠 대본만 필요하면 content-repurpose, 원고로 나레이션 영상을 처음부터 만들면 narration-video가 맡는다. 권리를 확인하지 않은 다른 사람의 영상을 내려받아 가공하는 데는 쓰지 않는다.
argument-hint: "[영상 파일 경로 또는 내 YouTube URL] [쇼츠 개수]"
metadata:
  author: humanist96
  version: 2.0.0-alpha.1
  book-chapter: "9"
---

# 롱폼 영상 → 쇼츠

쇼츠가 실패하는 지점은 대개 네 곳이다. 앞뒤 맥락이 없으면 이해가 안 되는 구간을 고르고, 자동자막의 오인식·중복이 화면에 그대로 나오고, 가로 영상을 잘라 글자를 못 읽게 만들고, 권리가 없는 영상을 가공한다.
그래서 이 스킬은 스크립트로 대본을 준비하고 후보를 추린 뒤, **구간 선택·제목·후크·자막은 Claude가 내용을 읽고 정하고**, 인코딩 전후에 `validate_highlights.py`·`verify_short.py`로 검사하고, 마지막으로 프레임을 눈으로 확인한다.

## 언제 쓰는가 / 쓰지 않는가

| 상황 | 이 스킬 | 다른 스킬 |
|------|:------:|-----------|
| 내 강의·발표·화면 녹화 파일 → 쇼츠 mp4 | ✅ | |
| 내 채널 YouTube 영상(권리 확인) → 쇼츠 | ✅ | |
| 영상 내용을 카드뉴스 이미지·카드 쇼츠로 | ✅ | |
| 쇼츠·릴스 **대본**만 | | content-repurpose |
| 원고 → 나레이션 영상 | | narration-video |
| 권리를 모르는 남의 영상 다운로드·가공 | ❌ | 하지 않는다 |

## 시작 전에

> 명령의 `${CLAUDE_SKILL_DIR}`는 Claude Code가 이 스킬 폴더 경로로 바꿔 준다. 바뀌지 않은 채 보이면 이 SKILL.md가 있는 폴더 경로를 넣는다.

1. 맞춤을 확인한다(레이아웃·후크·자막 크기 설정, 채널 문구). 있으면 한 줄로 알린다.

   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/_vendor/overrides.py --skill generate-shorts --skill-dir ${CLAUDE_SKILL_DIR} --list
   ```

2. 작업 폴더: `python ${CLAUDE_SKILL_DIR}/scripts/_vendor/paths.py generate-shorts --create` → 이하 `<W>`
3. ffmpeg 확인: `python ${CLAUDE_SKILL_DIR}/scripts/_vendor/media.py --check`. 없으면 `references/troubleshooting.md`의 설치 명령을 안내하고 멈춘다.
4. **권리 확인.** 로컬 파일이면 사용자가 준 것으로 본다. YouTube URL이면 "본인 채널이거나 사용 허락을 받은 영상인가요?"를 확인한다. 확인할 수 없거나 아니라고 하면 내려받지 않고, 원본 파일을 달라고 하거나 대본만 필요한지(content-repurpose) 묻는다.

## 워크플로

```
- [ ] 1. 원본·대본 준비 — prepare_source.py (영상+자막 / 영상+STT / 권리 확인한 URL)
- [ ] 2. 후보 추리기 — select_highlights.py --mode candidates
- [ ] 3. 큐레이션 — references/curation.md, highlights.json 작성
- [ ] 4. 하이라이트 검사 — validate_highlights 통과
- [ ] 5. 쇼츠 생성 — generate_shorts.py (레이아웃은 references/layouts.md)
- [ ] 6. 완성 검사 — verify_short 통과 + 프레임 눈 검수
- [ ] 7. 전달 — 파일·제목·후크·설명 문구, 정리
```

### 1. 원본·대본 준비

```bash
python ${CLAUDE_SKILL_DIR}/scripts/prepare_source.py --video <영상> --subs <자막.srt|.vtt> --output <W>
python ${CLAUDE_SKILL_DIR}/scripts/prepare_source.py --video <영상> --stt --output <W>          # 자막 없음
python ${CLAUDE_SKILL_DIR}/scripts/prepare_source.py --url <내 영상 URL> --i-have-rights --output <W>
```

`<W>/transcript.json`·`transcript.srt`·`transcript_timestamped.txt`·`source.json`이 생긴다. `--stt`는 faster-whisper가 필요하다(없으면 설치 명령을 안내). 자막 파일이 있으면 그쪽이 빠르고 정확하다.

### 2. 후보 추리기

```bash
python ${CLAUDE_SKILL_DIR}/scripts/select_highlights.py --transcript <W>/transcript.json --output <W>/candidates.json --mode candidates
```

### 3. 큐레이션

`references/curation.md`대로 `<W>/candidates.json`과 `<W>/transcript_timestamped.txt`를 읽고 `<W>/highlights.json`을 쓴다. 점수 순이 아니라 내용으로 고른다.
- 독립적으로 이해되고 결론이 있는 구간만. 인사·구독 요청·잡담·예고 구간은 쓰지 않는다
- 개수는 요청을 따른다. 요청이 없으면 기준을 만족하는 구간만(억지로 채우지 않는다)
- 후크·제목에 영상에 없는 숫자나 과장된 주장을 쓰지 않는다
- 자막(`subtitles`)은 문장 단위로 다시 쓴다(구간 시작 기준 상대 초)

### 4. 하이라이트 검사

```bash
python ${CLAUDE_SKILL_DIR}/scripts/validate_highlights.py <W>/highlights.json --source <W>/source.json --transcript <W>/transcript.json
```

`HIGHLIGHTS OK`가 나올 때까지 고친다. 경고(문장 경계 어긋남, 긴 자막 줄)는 가능하면 고친다.

### 5. 쇼츠 생성

```bash
python ${CLAUDE_SKILL_DIR}/scripts/generate_shorts.py --highlights <W>/highlights.json --video <영상> --output <W>/shorts --srt <W>/transcript.srt --layout fit_blur
```

URL 원본이면 `--video` 대신 `--url`(하이라이트 구간만 받는다). 레이아웃은 원본을 보고 고른다: 강의·코드·슬라이드는 `fit_blur`, 가운데 인물 토킹헤드만 `crop`. 명령에 시간 제한이 있는 환경은 `references/troubleshooting.md`의 나눠 실행하기.

### 6. 완성 검사

```bash
python ${CLAUDE_SKILL_DIR}/scripts/verify_short.py <W>/shorts --highlights <W>/highlights.json
```

`SHORTS VERIFY OK`(해상도·길이·오디오·검은 화면)를 확인한 뒤, 쇼츠마다 후크 구간(1초)과 중간 프레임을 뽑아 Read로 눈으로 본다.

```bash
ffmpeg -y -ss 1 -i <W>/shorts/short_01.mp4 -frames:v 1 <W>/check_01_hook.png
```

(ffmpeg가 PATH에 없으면 `media.py --check`가 보여 준 경로로 실행한다.) 확인할 것: 글자가 잘리지 않음, 자막이 화면 안에 적당한 크기, 후크가 내용을 가리지 않음, 한글이 네모로 나오지 않음.
문제가 있으면 원인을 고치고 그 쇼츠만 `--only N --force`로 다시 만든다.

### 7. 전달

1. 쇼츠 파일 목록: 번호·제목·후크·길이·원본 구간
2. 업로드용 설명·해시태그(`<W>/shorts/metadata.json`)
3. 고르지 않은 구간과 이유(예: "인사·잡담 구간은 제외")
4. 가정한 것(레이아웃, 개수)과 검사 결과 한 줄
5. 검수가 끝나면 `<W>/cache/`를 지워도 된다고 알린다

결과물과 응답에 스킬 소개·홍보 문구를 넣지 않는다.

## 카드뉴스 모드

"카드뉴스", "개념 카드", "카드로 정리" 요청이면 `references/card-news.md`대로 `cards.json`을 쓰고 `scripts/card_news.py`로 이미지 세트와 카드 쇼츠를 만든다(1단계 대본은 같다).

## 건너뛰기 쉬운 단계 (합리화 표)

| 이런 생각이 들면 | 실제로는 | 그래서 |
|------------------|----------|--------|
| "점수 높은 후보를 그대로 쓰면 된다" | 점수는 감정 단어 수일 뿐이다 | 내용을 읽고 고른다 |
| "자동자막을 그대로 쓰자" | 오인식·중복이 화면에 그대로 나온다 | subtitles를 다시 쓴다 |
| "crop이 꽉 차 보인다" | 강의·코드는 좌우가 잘려 못 읽는다 | 확신 없으면 fit_blur |
| "인코딩이 끝났으니 됐다" | 검은 화면·무음·네모 글자가 생길 수 있다 | verify_short + 프레임 눈 검수 |
| "링크만 주면 받으면 된다" | 남의 영상은 약관·저작권 문제다 | 권리 확인, 아니면 파일을 요청 |
| "로그인 확인에 막혔으니 쿠키로 돌파" | 우회는 하지 않는다 | YouTube Studio에서 원본을 받아 로컬로 |

## 맞춤(오버라이드)

영상·자막·후크 설정(`templates/config_template.yaml`을 복사한 `config.yaml`을 `--config`로), 채널 문구·해시태그(`references/channel.md`)를 바꿀 수 있다.
목록은 README의 "커스터마이즈 포인트", 규약은 `references/_shared/overrides.md`.

## 참고

- `references/curation.md` — 구간 고르기·제목·후크·자막 재구성·스키마(3단계)
- `references/layouts.md` — 세로 레이아웃 선택, 원본 자막이 구워진 영상, 후크 오버레이(5단계)
- `references/card-news.md` — 카드뉴스 모드
- `references/troubleshooting.md` — ffmpeg·폰트 설치, 시간 제한 환경, YouTube 오류
- `scripts/_vendor/media.py` — ffmpeg 찾기·영상 정보(공용)
- 환경 규약: `references/_shared/environment.md`
