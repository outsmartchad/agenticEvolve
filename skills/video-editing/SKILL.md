---
name: video-editing
description: AI-assisted video editing workflows for cutting, structuring, and augmenting real footage — not generating videos from prompts. Covers the full pipeline from raw capture through FFmpeg, Remotion, ElevenLabs, fal.ai, and final polish. Use when the user wants to edit video, cut footage, create content for YouTube/TikTok/Reels, build tutorials or demo videos, add subtitles or overlays, reframe video for different platforms, or says "edit this video", "make a clip", "cut this recording".
---

# Video Editing

AI-assisted editing for real footage. The value is not generation — it's compression: taking raw recordings and turning them into tight, publishable content fast.

## The Pipeline

```
Raw footage -> Claude (structure/plan) -> FFmpeg (cuts) -> Remotion (overlays) -> ElevenLabs/fal.ai (assets) -> Descript/CapCut (polish)
```

## Layer 1: Capture
- Screen Studio for screen recordings
- Raw camera footage for vlogs/interviews
- OBS for livestream recordings

## Layer 2: Organization (Claude)
- Transcribe and label content sections
- Identify dead sections, ums, silence
- Generate an edit decision list with timestamps
- Scaffold FFmpeg and Remotion code

## Layer 3: Deterministic Cuts (FFmpeg)

```bash
# Extract segment
ffmpeg -i raw.mp4 -ss 00:12:30 -to 00:15:45 -c copy segment_01.mp4

# Batch cut from a CSV
while IFS=, read -r start end label; do
  ffmpeg -i raw.mp4 -ss "$start" -to "$end" -c copy "segments/${label}.mp4"
done < cuts.txt

# Concatenate segments
for f in segments/*.mp4; do echo "file '$f'"; done > concat.txt
ffmpeg -f concat -safe 0 -i concat.txt -c copy assembled.mp4

# Create proxy for faster editing
ffmpeg -i raw.mp4 -vf "scale=960:-2" -c:v libx264 -preset ultrafast -crf 28 proxy.mp4

# Extract audio for transcription
ffmpeg -i raw.mp4 -vn -acodec pcm_s16le -ar 16000 audio.wav

# Normalize audio levels
ffmpeg -i segment.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:v copy normalized.mp4
```

## Layer 4: Programmable Composition (Remotion)
Use for overlays, text, data viz, motion graphics, composable scenes, reusable templates. If you'll do it more than once, codify it.

## Layer 5: Generated Assets
- ElevenLabs for voiceover
- fal.ai for music, SFX, generated visuals
- Generate selectively — only for assets that don't exist

## Layer 6: Final Polish (Descript / CapCut)
- Pacing, captions, color grading, final audio mix, export

## Social Media Reframing

| Platform | Aspect | Resolution |
|----------|--------|------------|
| YouTube | 16:9 | 1920x1080 |
| TikTok/Reels | 9:16 | 1080x1920 |
| Instagram Feed | 1:1 | 1080x1080 |

```bash
# 16:9 to 9:16 (vertical)
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" vertical.mp4
# 16:9 to 1:1 (square)
ffmpeg -i input.mp4 -vf "crop=ih:ih,scale=1080:1080" square.mp4
```

## Key Principles

1. Edit, don't generate — this is for cutting real footage
2. Structure before style — get the story right first
3. FFmpeg is the backbone — boring but critical
4. Remotion for repeatability — codify anything you'll do twice
5. Taste is the last layer — AI clears repetitive work, you make final calls

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) video-editing skill
