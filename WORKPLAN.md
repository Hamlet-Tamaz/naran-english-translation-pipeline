# Naran Pipeline — Workplan

## Phase 1: COMPLETED ✅
- [x] Rule engine (rules.json + auto-apply)
- [x] Hardened translation (dual GPT-4o + back-check)
- [x] Text archiving (original_russian.txt, translation_variants.json)
- [x] Multi-voice TTS (Naran=onyx, Kamran=echo, Commenter=fable)
- [x] Voice gap prevention (300ms between speakers)
- [x] Version tracking (v1, v2, v3... preserved)
- [x] Speaker detection (GPT-4o + pyannote.audio)
- [x] Dashboard UI (queue, upload, preview, download)
- [x] Cloud storage (R2 for unlimited file sizes)

## Phase 2: IN PROGRESS
- [x] Password protection (translathor888)
- [x] Robustness slider (Free → Maximum with dynamic pricing)
- [x] Rule engine UI (add rules from review mode)
- [ ] Manual review mode (side-by-side Russian/English, flag, retry)
- [ ] Segment-level retry API (re-translate single segment)
- [ ] Review flags persistence (review_flags.json)
- [ ] Cost breakdown display (per-component pricing in UI)

## Phase 3: HIGH IMPACT, LOW EFFORT
- [ ] Batch processing (drop 10 videos, auto-queue)
- [ ] Email/Slack notification on completion
- [ ] Download all outputs as ZIP
- [ ] Keyboard shortcuts (Space=play, F=flag, R=retry)
- [ ] Dark/light mode toggle

## Phase 4: HIGH IMPACT, MEDIUM EFFORT
- [ ] Translation memory (auto-suggest from past corrections)
- [ ] Segment-level confidence heatmap (color-code low-confidence)
- [ ] Audio waveform + subtitle timeline
- [ ] Export to SRT/VTT standalone files
- [ ] Auto-post to Instagram (Meta Graph API)

## Phase 5: MEDIUM IMPACT, HIGH EFFORT
- [ ] Fine-tune custom translation model on approved translations
- [ ] Real-time collaboration (multiple reviewers)
- [ ] Mobile-responsive review mode
- [ ] Analytics dashboard (cost tracking, error rates, rule effectiveness)

## Cost Reference
| Robustness | Translation | Voice | Speakers | Est. Cost/Video |
|------------|-------------|-------|----------|-----------------|
| Free | Google Translate | gTTS | None | $0 |
| Basic | GPT-4o-mini | OpenAI single | Basic | ~$0.02 |
| Standard | GPT-4o | Multi-voice | GPT-4o | ~$0.05 |
| Hardened | Dual + back-check | Multi-voice + gaps | GPT-4o + pyannote | ~$0.10 |
| Maximum | All + rules | All + gap tuning | All + manual review | ~$0.12 |
