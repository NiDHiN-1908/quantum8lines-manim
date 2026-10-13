# Studio UI Design Reference

## Purpose
Design reference for the future Studio UI (milestone M8). Not implemented.

Reference mockups:
- `studio_demo/studio_demo_01_overview.png`
- `studio_demo/studio_demo_02_publish.png`

---

## Mapping: Demo Elements to Project Files

| Demo Element | Project File / Target | Notes |
|---|---|---|
| Topic brief | `topics/<topic>/bible.json` | Stores topic overview, premise, target audience, and metadata |
| Voice for this topic | `bible.json` `voice_profile` + `brand/voices/*.json` | Configured voice profile selection mapped to validated voice presets |
| Teach from your materials | `bible.json` `sources` | Source documents / curriculum inputs (later phase) |
| AI generation toggle | Agent provider config | Toggles agent-assisted pipeline vs manual/scripted runs |
| Chapter map and Review | `script.json`, `storyboard.json`, `status.json` | Evaluated under gate G3 (human plan review) |
| Vertical preview | `renders/916` | Rendered low/high-res output video frames for 9:16 vertical layout |
| Bring the chapters together | Long-video compile | Concat/assembly stage combining chapters with 16:9 intro and transitions |
| Chapter cover frames | Publisher output | Keyframe thumbnails generated per chapter and for the full lesson |
| Prepare exports | `exports` | Bundled distribution packages (videos, SRT/ASS subtitles, metadata) |
| Publishing accounts | Later phase (manual upload first) | Direct API publishing integration planned for a subsequent milestone |

---

## Known differences from the real system

1. **Demo colors:** The demo mockups use cream, forest green, and peach, which differ from the canonical brand tokens (blue, orange, near-black). The preview must show real renders using design system tokens.
2. **Intro length:** The demo displays a 6 s intro; the real intro is about 10 s for 16:9 and a roughly 3 s sting for 9:16.
3. **Voice names:** Voice names in the demo (for example "Mara") must map to real voice profile IDs (e.g. from `brand/voices/` and Voice Lab acceptance).
4. **Panels to add:** Panels required for the full system include gate results G1–G7 per chapter, verified math claims, cast and characters, Voice Lab (blind test), a status board with re-run of a single stage, and a safe-zone overlay toggle on the preview.
5. **Section numbering and branding:** Section numbering in the demo is out of order (`01`, `02`, `06`, `05`), and the header logo shows a gap in "Quantum 8Lines"; the real brand name is one word, **Quantum8Lines**.
6. **Direct publishing scope:** Direct publishing to YouTube, Instagram, and Facebook is out of scope for v1; v1 prepares export files plus titles, descriptions, and captions for manual upload.
