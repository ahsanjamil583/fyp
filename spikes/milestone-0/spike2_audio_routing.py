"""Spike 2 - Can we capture the caller and speak back through WhatsApp?

This is the load-bearing assumption of the whole voice project. If WASAPI loopback
capture or VB-CABLE playback does not work on this machine, no amount of backend
work rescues it. Nothing here touches the backend or the GUI on purpose.

The routing being proved:

    caller speaks -> WhatsApp Desktop -> headset output
                  -> WASAPI loopback capture -> us            (capture path)

    our audio -> CABLE Input -> [VB-CABLE] -> CABLE Output
              -> WhatsApp Desktop microphone -> caller hears   (playback path)

Commands:
    devices    list every input, output and loopback device
    check      report what is installed and what is missing
    capture    record N seconds from a loopback device and report signal level
    play       play a WAV/MP3 into a chosen output (default: CABLE Input)
    duplex     capture and play at once, the way a real call behaves
    report     write results/spike2/REPORT.md

Examples:
    .venv\\Scripts\\python.exe spike2_audio_routing.py check
    .venv\\Scripts\\python.exe spike2_audio_routing.py capture --seconds 6
    .venv\\Scripts\\python.exe spike2_audio_routing.py play --file results/spike1/sample02_edge_en_us.mp3
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import pyaudiowpatch as pyaudio
except ImportError:  # pragma: no cover - the script's own error path
    print("pyaudiowpatch is missing. Install it with:")
    print("    .venv\\Scripts\\python.exe -m pip install pyaudiowpatch")
    sys.exit(1)

RESULTS = Path(__file__).parent / "results" / "spike2"
CABLE_INPUT_HINT = "cable input"      # what we play into
CABLE_OUTPUT_HINT = "cable output"    # what WhatsApp should use as its microphone

# Below this RMS the "recording" is effectively silence, which almost always means
# WhatsApp is playing to a different device than the one being captured.
SILENCE_RMS = 200


@dataclass
class DeviceInfo:
    index: int
    name: str
    max_input: int
    max_output: int
    rate: float
    is_loopback: bool
    host_api: str


def enumerate_devices(audio: "pyaudio.PyAudio") -> list[DeviceInfo]:
    devices = []
    for i in range(audio.get_device_count()):
        raw = audio.get_device_info_by_index(i)
        devices.append(
            DeviceInfo(
                index=int(raw["index"]),
                name=str(raw["name"]),
                max_input=int(raw["maxInputChannels"]),
                max_output=int(raw["maxOutputChannels"]),
                rate=float(raw["defaultSampleRate"]),
                is_loopback=bool(raw.get("isLoopbackDevice", False)),
                host_api=str(audio.get_host_api_info_by_index(int(raw["hostApi"]))["name"]),
            )
        )
    return devices


def find_by_hint(devices: list[DeviceInfo], hint: str, want_output: bool) -> DeviceInfo | None:
    for device in devices:
        if hint in device.name.lower():
            if want_output and device.max_output > 0 and not device.is_loopback:
                return device
            if not want_output and device.max_input > 0:
                return device
    return None


def default_loopback(audio: "pyaudio.PyAudio", devices: list[DeviceInfo]) -> DeviceInfo | None:
    """The loopback that mirrors the current default speakers - what WhatsApp uses."""
    try:
        wasapi = audio.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = audio.get_device_info_by_index(wasapi["defaultOutputDevice"])
        for device in devices:
            if device.is_loopback and speakers["name"] in device.name:
                return device
    except Exception:
        pass
    return next((d for d in devices if d.is_loopback), None)


def rms_of(frames: bytes) -> float:
    if not frames:
        return 0.0
    count = len(frames) // 2
    samples = struct.unpack(f"<{count}h", frames[: count * 2])
    return math.sqrt(sum(s * s for s in samples) / count) if count else 0.0


def cmd_devices(audio, devices) -> None:
    print(f"{'idx':>4}  {'in':>3} {'out':>3}  {'rate':>7}  {'loop':>5}  {'host api':<22} name")
    print("-" * 108)
    for d in devices:
        print(f"{d.index:>4}  {d.max_input:>3} {d.max_output:>3}  {d.rate:>7.0f}  "
              f"{'yes' if d.is_loopback else '':>5}  {d.host_api:<22} {d.name[:46]}")


def cmd_check(audio, devices) -> dict:
    loopbacks = [d for d in devices if d.is_loopback]
    cable_in = find_by_hint(devices, CABLE_INPUT_HINT, want_output=True)
    cable_out = find_by_hint(devices, CABLE_OUTPUT_HINT, want_output=False)
    chosen_loopback = default_loopback(audio, devices)

    checks = [
        # PortAudio reports this host API as "Windows WASAPI", so match on substring.
        ("WASAPI host API present", any("WASAPI" in d.host_api.upper() for d in devices),
         "PyAudioWPatch could not see WASAPI; loopback capture is impossible."),
        ("Loopback device available", bool(loopbacks),
         "No loopback device. Capture of the caller's voice cannot work."),
        ("VB-CABLE input (we play here)", cable_in is not None,
         "Install VB-CABLE and reboot, then re-run. Without it the caller hears nothing."),
        ("VB-CABLE output (WhatsApp mic)", cable_out is not None,
         "Install VB-CABLE and reboot. WhatsApp must use 'CABLE Output' as its microphone."),
        ("Default-speaker loopback resolved", chosen_loopback is not None,
         "Could not resolve which loopback mirrors the default speakers."),
    ]

    print("Environment check")
    print("-" * 74)
    for label, ok, remedy in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"         -> {remedy}")

    print("\nResolved devices")
    print("-" * 74)
    print(f"  capture (loopback) : {chosen_loopback.name if chosen_loopback else 'NONE'}")
    print(f"  playback target    : {cable_in.name if cable_in else 'NONE (install VB-CABLE)'}")
    print(f"  WhatsApp mic should be: {cable_out.name if cable_out else 'CABLE Output (install VB-CABLE)'}")
    print(f"\n  loopback devices found: {len(loopbacks)}")
    for d in loopbacks[:6]:
        print(f"    [{d.index}] {d.name[:66]}")

    return {
        "checks": [{"label": label, "pass": ok} for label, ok, _ in checks],
        "loopbackCount": len(loopbacks),
        "captureDevice": chosen_loopback.name if chosen_loopback else None,
        "playbackDevice": cable_in.name if cable_in else None,
        "whatsappMicDevice": cable_out.name if cable_out else None,
        "allPassed": all(ok for _, ok, _ in checks),
    }


def cmd_capture(audio, devices, seconds: float, device_index: int | None) -> dict:
    device = (
        next((d for d in devices if d.index == device_index), None)
        if device_index is not None
        else default_loopback(audio, devices)
    )
    if device is None:
        print("No loopback device available.")
        return {"ok": False, "reason": "no_loopback_device"}

    rate = int(device.rate)
    channels = min(device.max_input, 2) or 1
    print(f"Capturing {seconds:.0f}s from [{device.index}] {device.name}")
    print("Play audio through WhatsApp (or any app) NOW so there is something to capture.\n")

    RESULTS.mkdir(parents=True, exist_ok=True)
    destination = RESULTS / "captured_caller.wav"

    # A blocking read on an idle WASAPI loopback never returns - Windows delivers no
    # frames while the render device is silent. A callback stream keeps the wall clock
    # in our hands, so the spike reports "no audio" instead of hanging forever. The
    # companion app needs the same treatment.
    frames: list[bytes] = []
    levels: list[float] = []

    def on_audio(in_data, frame_count, time_info, status):  # noqa: ARG001 - PortAudio signature
        frames.append(in_data)
        levels.append(rms_of(in_data))
        return (None, pyaudio.paContinue)

    stream = audio.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                        input=True, input_device_index=device.index,
                        frames_per_buffer=1024, stream_callback=on_audio)
    stream.start_stream()
    deadline = time.time() + seconds
    try:
        while time.time() < deadline:
            level = levels[-1] if levels else 0.0
            bars = "#" * min(int(level / 250), 46)
            print(f"\r  level {level:7.0f} |{bars:<46}|", end="", flush=True)
            time.sleep(0.1)
    finally:
        stream.stop_stream()
        stream.close()
    print()

    if not frames:
        print("\n  No frames arrived at all. On Windows this means the render device was")
        print("  completely idle for the whole window - WASAPI delivers nothing until")
        print("  something plays. Start audio first, then re-run.")

    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(frames))

    peak = max(levels) if levels else 0.0
    mean = sum(levels) / len(levels) if levels else 0.0
    heard = peak > SILENCE_RMS
    print(f"\n  saved   : {destination}")
    print(f"  peak RMS: {peak:.0f}   mean RMS: {mean:.0f}")
    print(f"  verdict : {'AUDIO CAPTURED' if heard else 'SILENCE - capture path NOT working'}")
    if not heard:
        print("            Check that WhatsApp's speaker is the same device this loopback mirrors,")
        print("            and that something was actually playing during the recording.")
    return {"ok": heard, "device": device.name, "peakRms": round(peak, 1),
            "meanRms": round(mean, 1), "file": str(destination), "seconds": seconds}


def load_audio_as_pcm(path: Path) -> tuple[bytes, int, int]:
    """Return (pcm, rate, channels). MP3 is decoded via the stdlib-free wave path only."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path)) as handle:
            return handle.readframes(handle.getnframes()), handle.getframerate(), handle.getnchannels()
    raise ValueError(
        f"{path.name} is not a WAV. Re-render it as WAV, or use a WAV from results/spike1 "
        "(the Windows SAPI samples are WAV)."
    )


def cmd_play(audio, devices, file: Path, device_index: int | None) -> dict:
    device = (
        next((d for d in devices if d.index == device_index), None)
        if device_index is not None
        else find_by_hint(devices, CABLE_INPUT_HINT, want_output=True)
    )
    if device is None:
        print("CABLE Input not found. Install VB-CABLE, or pass --device <idx> to play elsewhere.")
        return {"ok": False, "reason": "no_playback_device"}
    if not file.exists():
        print(f"File not found: {file}")
        return {"ok": False, "reason": "file_missing"}

    try:
        pcm, rate, channels = load_audio_as_pcm(file)
    except ValueError as exc:
        print(exc)
        return {"ok": False, "reason": "unsupported_format"}

    print(f"Playing {file.name} -> [{device.index}] {device.name}")
    print("If a call is connected and WhatsApp's microphone is 'CABLE Output', the caller hears this.\n")
    stream = audio.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                        output=True, output_device_index=device.index)
    started = time.perf_counter()
    try:
        stream.write(pcm)
    finally:
        stream.stop_stream()
        stream.close()
    elapsed = time.perf_counter() - started
    print(f"  played {elapsed:.1f}s of audio")
    return {"ok": True, "device": device.name, "file": str(file), "seconds": round(elapsed, 2)}


def cmd_duplex(audio, devices, seconds: float, file: Path) -> dict:
    """Play our audio while capturing, to see how badly it bleeds back in.

    Phase 1 is half-duplex precisely because of this: if the loopback picks up our own
    TTS, the agent transcribes itself and the call goes in circles.
    """
    capture = default_loopback(audio, devices)
    playback = find_by_hint(devices, CABLE_INPUT_HINT, want_output=True)
    if capture is None or playback is None:
        print("Need both a loopback device and CABLE Input for this test.")
        return {"ok": False, "reason": "missing_devices"}
    if not file.exists():
        print(f"File not found: {file}")
        return {"ok": False, "reason": "file_missing"}

    print("Measuring 2s of silence baseline...")
    rate, channels = int(capture.rate), min(capture.max_input, 2) or 1
    stream = audio.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                        input=True, input_device_index=capture.index, frames_per_buffer=1024)
    baseline = []
    deadline = time.time() + 2
    while time.time() < deadline:
        baseline.append(rms_of(stream.read(1024, exception_on_overflow=False)))
    baseline_mean = sum(baseline) / len(baseline) if baseline else 0.0

    print(f"  baseline RMS {baseline_mean:.0f}\nNow playing into CABLE Input while still capturing...")
    import threading

    def play():
        try:
            pcm, prate, pchannels = load_audio_as_pcm(file)
        except ValueError:
            return
        out = audio.open(format=pyaudio.paInt16, channels=pchannels, rate=prate,
                         output=True, output_device_index=playback.index)
        out.write(pcm)
        out.stop_stream()
        out.close()

    thread = threading.Thread(target=play, daemon=True)
    thread.start()
    during = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        during.append(rms_of(stream.read(1024, exception_on_overflow=False)))
    stream.stop_stream()
    stream.close()
    thread.join(timeout=2)

    during_mean = sum(during) / len(during) if during else 0.0
    bleed = during_mean > max(baseline_mean * 3, SILENCE_RMS)
    print(f"  during-playback RMS {during_mean:.0f}")
    print(f"  verdict: {'BLEED DETECTED - keep half-duplex muting' if bleed else 'no significant bleed'}")
    return {"ok": True, "baselineRms": round(baseline_mean, 1), "duringRms": round(during_mean, 1),
            "bleedDetected": bleed}


def cmd_selftest(audio, devices, file: Path) -> dict:
    """Prove the capture half works, without WhatsApp or VB-CABLE.

    Plays a known file to the default speakers while capturing the loopback that
    mirrors them. If the captured level rises, WASAPI loopback is functioning on this
    machine and only the VB-CABLE half remains unproven.
    """
    capture = default_loopback(audio, devices)
    if capture is None:
        return {"ok": False, "reason": "no_loopback_device"}
    if not file.exists():
        print(f"File not found: {file}")
        return {"ok": False, "reason": "file_missing"}

    try:
        pcm, prate, pchannels = load_audio_as_pcm(file)
    except ValueError as exc:
        print(exc)
        return {"ok": False, "reason": "unsupported_format"}

    print(f"Self-test: playing {file.name} to the default speakers")
    print(f"           while capturing [{capture.index}] {capture.name}\n")

    frames: list[bytes] = []
    levels: list[float] = []

    def on_audio(in_data, frame_count, time_info, status):  # noqa: ARG001
        frames.append(in_data)
        levels.append(rms_of(in_data))
        return (None, pyaudio.paContinue)

    rate, channels = int(capture.rate), min(capture.max_input, 2) or 1
    stream = audio.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                        input=True, input_device_index=capture.index,
                        frames_per_buffer=1024, stream_callback=on_audio)
    stream.start_stream()

    import threading

    def play():
        out = audio.open(format=pyaudio.paInt16, channels=pchannels, rate=prate, output=True)
        out.write(pcm)
        out.stop_stream()
        out.close()

    thread = threading.Thread(target=play, daemon=True)
    thread.start()
    while thread.is_alive():
        level = levels[-1] if levels else 0.0
        print(f"\r  level {level:7.0f} |{'#' * min(int(level / 250), 46):<46}|", end="", flush=True)
        time.sleep(0.1)
    thread.join(timeout=2)
    time.sleep(0.3)
    stream.stop_stream()
    stream.close()
    print()

    peak = max(levels) if levels else 0.0
    ok = peak > SILENCE_RMS
    RESULTS.mkdir(parents=True, exist_ok=True)
    destination = RESULTS / "selftest_loopback.wav"
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(frames))

    print(f"\n  frames captured: {len(frames)}   peak RMS: {peak:.0f}")
    print(f"  verdict: {'WASAPI LOOPBACK WORKS' if ok else 'no signal - loopback did not capture playback'}")
    print(f"  saved  : {destination}")
    return {"ok": ok, "peakRms": round(peak, 1), "frames": len(frames),
            "device": capture.name, "file": str(destination)}


def write_report(payload: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    check = payload.get("check", {})
    capture = payload.get("capture", {})
    play = payload.get("play", {})
    duplex = payload.get("duplex", {})

    lines = [
        "# Spike 2 - Audio routing",
        "",
        "Proves the assumption the whole voice project rests on: that the caller's audio",
        "can be captured from WhatsApp Desktop, and that our audio can be pushed back into",
        "the call. If this spike fails, the approach does not work on this machine.",
        "",
        "## Environment",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for item in check.get("checks", []):
        lines.append(f"| {item['label']} | {'PASS' if item['pass'] else 'FAIL'} |")
    lines += [
        "",
        f"- Capture device: `{check.get('captureDevice')}`",
        f"- Playback device: `{check.get('playbackDevice')}`",
        f"- WhatsApp microphone must be set to: `{check.get('whatsappMicDevice') or 'CABLE Output'}`",
        "",
        "## Capture path",
        "",
    ]
    if capture:
        lines += [
            f"- Peak RMS: **{capture.get('peakRms')}** (silence threshold {SILENCE_RMS})",
            f"- Verdict: **{'audio captured' if capture.get('ok') else 'SILENCE - not working'}**",
            f"- File: `{capture.get('file')}`",
        ]
    else:
        lines.append("_Not run._")
    lines += ["", "## Loopback self-test (no WhatsApp / no VB-CABLE needed)", ""]
    selftest = payload.get("selftest", {})
    if selftest:
        lines += [
            f"- Played a known file to the default speakers and captured `{selftest.get('device')}`",
            f"- Frames: {selftest.get('frames')}, peak RMS **{selftest.get('peakRms')}**",
            f"- Verdict: **{'WASAPI loopback works on this machine' if selftest.get('ok') else 'no signal'}**",
        ]
    else:
        lines.append("_Not run._")

    lines += ["", "## Playback path", ""]
    lines.append(
        f"- Played `{play.get('file')}` into `{play.get('device')}` - **{'ok' if play.get('ok') else 'failed'}**"
        if play else "_Not run._"
    )
    lines += ["", "## Echo bleed (why phase 1 is half-duplex)", ""]
    if duplex:
        lines += [
            f"- Baseline RMS {duplex.get('baselineRms')} -> during playback {duplex.get('duringRms')}",
            f"- Bleed detected: **{duplex.get('bleedDetected')}**",
            "",
            "Bleed means the loopback hears our own TTS. Muting capture while the agent",
            "speaks is therefore mandatory, not an optimisation.",
        ]
    else:
        lines.append("_Not run._")

    lines += [
        "",
        "## Verdict (fill in after a real call)",
        "",
        "```text",
        "Caller audio captured from a live WhatsApp call?   ______",
        "Caller heard the played audio?                     ______",
        "Echo/feedback acceptable with headphones?          ______",
        "Proceed with this approach? (yes/no)               ______",
        "```",
    ]
    (RESULTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {RESULTS / 'REPORT.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["devices", "check", "capture", "play", "duplex", "selftest", "report"])
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--device", type=int, default=None, help="Device index override.")
    parser.add_argument("--file", type=Path, default=RESULTS.parent / "spike1" / "sample02_sapi.wav")
    args = parser.parse_args()

    audio = pyaudio.PyAudio()
    try:
        devices = enumerate_devices(audio)
        state_path = RESULTS / "results.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

        if args.command == "devices":
            cmd_devices(audio, devices)
        elif args.command == "check":
            state["check"] = cmd_check(audio, devices)
        elif args.command == "capture":
            state["capture"] = cmd_capture(audio, devices, args.seconds, args.device)
        elif args.command == "play":
            state["play"] = cmd_play(audio, devices, args.file, args.device)
        elif args.command == "duplex":
            state["duplex"] = cmd_duplex(audio, devices, args.seconds, args.file)
        elif args.command == "selftest":
            state["selftest"] = cmd_selftest(audio, devices, args.file)
        elif args.command == "report":
            write_report(state)
            return

        if args.command != "devices":
            if "check" not in state:
                state["check"] = cmd_check(audio, devices)
            write_report(state)
    finally:
        audio.terminate()


if __name__ == "__main__":
    main()
