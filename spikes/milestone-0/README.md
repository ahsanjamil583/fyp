# Milestone 0 — Voice Companion spikes

Three throwaway experiments that answer the questions capable of invalidating the
WhatsApp Voice Companion design. They exist to be run *before* any companion or
backend code is written, because each one can change what gets built.

| Spike | Question | Status |
|---|---|---|
| 1. TTS and language | Can the agent's actual replies be spoken intelligibly? | **Answered** |
| 2. Audio routing | Can we capture the caller and speak back through WhatsApp? | **Half answered** |
| 3. Session coexistence | Can Baileys and WhatsApp Desktop share one account? | **Blocked — needs re-pairing** |

Nothing here is production code. It does not import from `backend/app`, and the
Windows-only dependency (`pyaudiowpatch`) is kept out of the API's requirements on
purpose.

## Setup

```bash
cd spikes/milestone-0
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The backend should be running for spike 1 and 3 (`uvicorn app.main:app --reload` from
`backend/`). Spike 2 needs no backend at all.

---

## Spike 1 — TTS and Roman Urdu (decision D1)

The agent replies in Roman Urdu — Urdu written in Latin script. No mainstream TTS
engine handles that directly, so this measures which route works:

- **(a)** force English replies on the voice channel
- **(b)** transliterate to Urdu script and use an Urdu voice
- **(c)** feed Roman Urdu straight to a multilingual voice

```bash
.venv\Scripts\python.exe spike1_tts_language.py            # pull live replies
.venv\Scripts\python.exe spike1_tts_language.py --offline  # use stored replies
```

It pulls real replies from the running backend, speaks each with four engines, then
sends the audio back through Groq Whisper. **Content recall** — the fraction of product
names and prices that survive the round trip — is the score that matters; grammar words
are excluded and a transcription returned in Urdu script is not penalised as long as
the products and numbers come back.

Results land in `results/spike1/` (40 audio files + `REPORT.md`). **Listen to them** —
the score is a proxy, not a verdict.

### Result

| Engine | Mean content recall | Script shifts | Verdict |
|---|---|---|---|
| edge_en_us (`en-US-AriaNeural`) | **0.91** | 0 | usable |
| windows_sapi (offline) | 0.88 | 0 | usable |
| edge_ur_pk (`ur-PK-UzmaNeural`) | 0.67 | 3 | poor |
| edge_en_in (`en-IN-NeerjaNeural`) | 0.66 | 4 | poor |

**English replies: 0.98 · Roman Urdu replies: 0.58.**

**Decision: route (a).** Force English on the voice channel and use
`en-US-AriaNeural`. The Urdu voice performed worse than the English one even on Urdu
text, and it caused script shifts that would break any keyword matching downstream.
Roman Urdu stays exactly as it is on the text channels, where it works well.

---

## Spike 2 — Audio routing

Proves the assumption everything else rests on.

```bash
.venv\Scripts\python.exe spike2_audio_routing.py devices    # list every device
.venv\Scripts\python.exe spike2_audio_routing.py check      # what is installed/missing
.venv\Scripts\python.exe spike2_audio_routing.py selftest   # prove loopback works, no WhatsApp needed
.venv\Scripts\python.exe spike2_audio_routing.py capture --seconds 6
.venv\Scripts\python.exe spike2_audio_routing.py play --file results/spike1/sample02_sapi.wav
.venv\Scripts\python.exe spike2_audio_routing.py duplex     # does our own audio bleed back in?
```

### Result so far

- **WASAPI loopback works.** The self-test played a file to the speakers and captured
  764 frames at peak RMS 11913 through `Speakers (Realtek(R) Audio) [Loopback]`. The
  capture half of the routing is proven on this machine.
- **VB-CABLE is not installed**, so the playback half is unproven. This is the one
  remaining blocker for a full pass.

### Finding worth carrying into Milestone 3

A blocking `stream.read()` on an idle WASAPI loopback **never returns** — Windows
delivers no frames while the render device is silent, and the process hangs. The spike
now uses a callback stream with a wall-clock deadline. **The companion app must do the
same**, or it will freeze whenever a call goes quiet.

### To finish this spike

1. Install [VB-CABLE](https://vb-audio.com/Cable/) and reboot.
2. `spike2_audio_routing.py check` — all five checks should pass.
3. In WhatsApp Desktop: **Speaker** = your headset, **Microphone** = `CABLE Output`.
4. Place a real WhatsApp call to the machine, answer it, and run `capture` while the
   caller speaks. Confirm the level meter moves.
5. Run `play` during the call and confirm the caller hears it.
6. Run `duplex` and record whether bleed is detected.
7. Fill in the verdict block in `results/spike2/REPORT.md`.

---

## Spike 3 — Baileys and WhatsApp Desktop coexistence

Watches whether the messaging bridge and WhatsApp Desktop can stay linked to one
account simultaneously. Baileys is unofficial, so this is observed rather than assumed.

```bash
.venv\Scripts\python.exe spike3_session_coexistence.py --once
.venv\Scripts\python.exe spike3_session_coexistence.py --minutes 120
```

Every sample is appended to `results/spike3/timeline.jsonl`, and state transitions are
summarised in `REPORT.md`.

### Result so far

```
2026-08-02T12:33:15Z  [session_broken]  desktop=down | 6a4f571923bff861a6f43e36=logged_out
```

The monitor works, but the measurement cannot start yet: the Bonanza Baileys session is
logged out and WhatsApp Desktop is not installed/running. **This is itself a data point**
— the session dropped once already during development, which is exactly the risk this
spike exists to quantify.

### To finish this spike

1. Delete `whatsapp-bridge/.baileys_auth/default/`, restart the bridge, scan the QR.
2. Install WhatsApp Desktop and link it to the **same** account.
3. Run with `--minutes 120` or longer, ideally overnight.
4. Any `-> session_broken` transition while Desktop was up means the two are competing
   for device slots. Mitigation: separate WhatsApp accounts for messaging and voice.

---

## What Milestone 0 has settled

**Proceed** — with one route decided and one blocker outstanding.

- **D1 answered with evidence.** English-only on the voice channel, `en-US-AriaNeural`.
  This also simplifies Milestone 2: no transliteration dependency.
- **Capture path proven.** WASAPI loopback works on this hardware.
- **Playback path unproven.** Needs VB-CABLE installed — a 5-minute install and reboot.
- **Coexistence unproven.** Needs the bridge re-paired first.

### Consequences for the plan

1. Add a **voice reply style** to the agent that also forces `languageMode = "english"`
   for `channel="whatsapp_voice"`. Spike 1 justifies this in the report.
2. Budget for the **idle-loopback hang** in the capture loop from the start.
3. Keep the **separate-accounts** fallback for messaging and voice until spike 3 passes.

### Evidence for the FYP report

`results/spike1/REPORT.md` gives a measured, defensible justification for the language
decision rather than an assertion — the kind of thing that answers a viva question well.
Keep the audio files; being able to play the comparison is more persuasive than the table.
