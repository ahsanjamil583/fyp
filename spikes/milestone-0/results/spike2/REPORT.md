# Spike 2 - Audio routing

Proves the assumption the whole voice project rests on: that the caller's audio
can be captured from WhatsApp Desktop, and that our audio can be pushed back into
the call. If this spike fails, the approach does not work on this machine.

## Environment

| Check | Result |
|---|---|
| WASAPI host API present | PASS |
| Loopback device available | PASS |
| VB-CABLE input (we play here) | FAIL |
| VB-CABLE output (WhatsApp mic) | FAIL |
| Default-speaker loopback resolved | PASS |

- Capture device: `Speakers (Realtek(R) Audio) [Loopback]`
- Playback device: `None`
- WhatsApp microphone must be set to: `CABLE Output`

## Capture path

- Peak RMS: **0.0** (silence threshold 200)
- Verdict: **SILENCE - not working**
- File: `C:\Users\ahsan\Desktop\BIZXUSAI\phase-32\bizxus-code\spikes\milestone-0\results\spike2\captured_caller.wav`

## Loopback self-test (no WhatsApp / no VB-CABLE needed)

- Played a known file to the default speakers and captured `Speakers (Realtek(R) Audio) [Loopback]`
- Frames: 764, peak RMS **11912.9**
- Verdict: **WASAPI loopback works on this machine**

## Playback path

_Not run._

## Echo bleed (why phase 1 is half-duplex)

_Not run._

## Verdict (fill in after a real call)

```text
Caller audio captured from a live WhatsApp call?   ______
Caller heard the played audio?                     ______
Echo/feedback acceptable with headphones?          ______
Proceed with this approach? (yes/no)               ______
```