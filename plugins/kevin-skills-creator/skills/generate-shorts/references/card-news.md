# 카드뉴스 모드 (이미지 세트 + 카드 쇼츠 영상)

"카드뉴스", "개념 카드", "카드로 정리" 요청이면 클립 대신 내용 요약 카드를 만든다.
디자인(다크 네이비 + 옐로 액센트, 1080x1920)은 `scripts/card_news.py`에 고정돼 있고 Claude는 내용(`cards.json`)만 쓴다. 외부 API가 필요 없다(Pillow + ffmpeg, 나레이션은 edge-tts·인터넷 필요).

## 절차

```bash
# 1) 대본 준비(이미 있으면 생략) — 워크플로 1단계와 같다
python ${CLAUDE_SKILL_DIR}/scripts/prepare_source.py --video <영상> --subs <자막> --output <W>

# 2) [Claude] transcript를 읽고 <W>/cards.json 작성(아래 스키마)

# 3) 카드 렌더링 + 카드 쇼츠 영상(나레이션 포함 권장: 카드 길이가 낭독 길이에 맞춰진다)
python ${CLAUDE_SKILL_DIR}/scripts/card_news.py --cards <W>/cards.json --output <W>/cards/ --video <W>/cards/cards_short.mp4 --tts

# 4) [Claude] 만든 PNG를 Read로 열어 검수(텍스트 넘침·겹침·오탈자)
```

나레이션 없이 만들려면 `--tts` 대신 `--seconds 4`. 렌더러가 "경고"(폰트 축소·잘림)를 내면 그 카드 문구를 줄여 다시 렌더링한다.

## cards.json

```json
{
  "series_label": "음성 합성 파인튜닝 · 핵심 개념",
  "footer": "전체 강의는 채널에서 ▶",
  "cards": [
    {
      "index": 1,
      "title_lines": ["로스는", "낮을수록 좋다?"],
      "punch": "오해입니다",
      "points": [
        {"label": "실전 기준", "body": "여러 번 학습해 보니 12~11 구간이\n가장 안정적"},
        {"label": "진짜 변수", "body": "로스보다 에폭 수가 중요"}
      ],
      "narration": "로스는 낮을수록 좋다고 생각하기 쉬운데요, 사실은 오해입니다. 여러 번 학습해 보면 12에서 11 구간이 가장 안정적이었고, 로스보다 에폭 수가 훨씬 중요합니다."
    }
  ]
}
```

- 카드 1장 = 개념 1개, 보통 3~5장
- `title_lines`: 질문·도발형, 최대 2줄·줄당 8자 안팎
- `punch`: 반전·답 한마디, 8자 이내
- `points`: 2~3개. `label` 6자 이내, `body` 2줄 이내(줄당 ~22자)
- `narration`: `--tts` 때 읽는 구어체 2~3문장(10~20초). 생략하면 제목+펀치를 읽어 어색하다
- 숫자·주장은 영상에 있는 것만 쓴다. 음성인식 오류는 문맥으로 고친다
