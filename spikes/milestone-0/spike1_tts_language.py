"""Spike 1 - Does text-to-speech work on this agent's actual replies?

Question this answers (decision D1):
    The agent answers in Roman Urdu - Urdu written in Latin script, e.g.
    "Ji, White Running Sneakers available hain. Qeemat PKR 4,500 hai."
    Mainstream TTS engines expect either English or Urdu script, so neither
    handles this directly. Which route sounds acceptable on a phone call?

        (a) force English replies on the voice channel
        (b) transliterate to Urdu script and use an Urdu voice
        (c) feed Roman Urdu straight to a multilingual voice

The spike pulls REAL replies from the running backend (not invented samples),
speaks each one with every candidate engine, and then feeds the audio back
through Groq Whisper. The round trip is the useful part: if Whisper cannot read
back what the TTS said, a caller will not understand it either.

Run:
    .venv\\Scripts\\python.exe spike1_tts_language.py
    .venv\\Scripts\\python.exe spike1_tts_language.py --offline   (skip the backend, use stored samples)

Outputs to results/spike1/, then open results/spike1/REPORT.md and listen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import httpx

RESULTS = Path(__file__).parent / "results" / "spike1"
API = os.environ.get("BIZXUS_API", "http://127.0.0.1:8000/api/v1")

# Public tenants to pull live replies from. Slugs, not ids, so this keeps working
# if the database is reseeded.
TENANT_SLUGS = ["style", "bonanza"]

# Questions chosen to force the agent into both languages and into the reply
# shapes that are hardest to speak: lists, prices, and confirmations.
PROBE_QUESTIONS = [
    "what products do you have?",
    "do you have shoes?",
    "what is the price of black formal shoes?",
    "koi footwear hai?",
    "kitne ka hai grey tracksuit?",
    "mujhe do black formal shoes chahiye",
    "do you deliver to Lahore?",
    "what are your timings?",
    "order 2 grey tracksuit",
    "yes confirm karo",
]

# Used with --offline, and as a backstop if the backend is unreachable. These are
# real replies captured from this agent during earlier testing.
FALLBACK_REPLIES = [
    "We have the following products available: White Running Sneakers PKR 4,500. Black Formal Shoes PKR 5,000. Brown Leather Loafers PKR 6,200.",
    "Yes, we have a variety of shoes. Would you like to know more about any of these?",
    "Ji, White Running Sneakers available hain. Qeemat PKR 4,500 hai.",
    "footwear hai: White Running Sneakers PKR 4,500, Black Formal Shoes PKR 5,000. kya chahiyeh?",
    "Maine Grey Tracksuit find kar liya hai aur quantity 2 ka draft tayar kar diya hai. Aap neeche draft confirm kar sakte hain.",
    "Grey Tracksuit ki price PKR 4,800 hai.",
    "This is a Fashion business, so pizza is not available here. You can ask about shirts, hoodies, shoes, jeans, sizes, or colors.",
    "Draft ready: 2x Black Formal Shoes. Total: PKR 10000. Delivery or pickup?",
]

# Candidate voices. edge-tts needs no API key, which keeps the spike reproducible.
VOICE_CANDIDATES = [
    ("edge_en_us", "en-US-AriaNeural", "English voice - route (a) and (c) baseline"),
    ("edge_en_in", "en-IN-NeerjaNeural", "Indian English - closer accent for South Asian names"),
    ("edge_ur_pk", "ur-PK-UzmaNeural", "Urdu voice - route (b) and (c)"),
]


def is_roman_urdu(text: str) -> bool:
    """Rough check: does this reply contain Roman Urdu markers?"""
    markers = {"hai", "hain", "ka", "ki", "ke", "aap", "mein", "kar", "chahiyeh", "chahiye",
               "qeemat", "kitne", "kya", "ji", "diya", "liya", "sakte", "nahi", "aur"}
    words = {w.strip(".,!?").lower() for w in text.split()}
    return len(words & markers) >= 2


@dataclass
class Sample:
    index: int
    question: str
    reply: str
    tenant: str
    language: str
    renders: list[dict] = field(default_factory=list)


async def collect_live_replies() -> list[Sample]:
    """Ask the real backend, so the spike measures what customers will hear."""
    samples: list[Sample] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for slug in TENANT_SLUGS:
            try:
                probe = await client.get(f"{API}/public/businesses/{slug}")
                if probe.status_code != 200:
                    print(f"  tenant {slug!r} not reachable ({probe.status_code}); skipping")
                    continue
            except Exception as exc:
                print(f"  backend not reachable: {exc}")
                return samples

            for question in PROBE_QUESTIONS:
                try:
                    response = await client.post(
                        f"{API}/public/businesses/{slug}/chat/messages",
                        json={"messageText": question},
                    )
                    if response.status_code == 429:
                        print("  rate limited; pausing 20s (the limiter is working as designed)")
                        await asyncio.sleep(20)
                        response = await client.post(
                            f"{API}/public/businesses/{slug}/chat/messages",
                            json={"messageText": question},
                        )
                    if response.status_code != 200:
                        print(f"  [{slug}] {question[:32]!r} -> HTTP {response.status_code}")
                        continue
                    messages = response.json()["data"]["messages"]
                    reply = messages[-1]["messageText"] if messages else ""
                except Exception as exc:
                    print(f"  [{slug}] {question[:32]!r} -> {type(exc).__name__}")
                    continue

                if not reply:
                    continue
                samples.append(
                    Sample(
                        index=len(samples) + 1,
                        question=question,
                        reply=reply,
                        tenant=slug,
                        language="roman_urdu" if is_roman_urdu(reply) else "english",
                    )
                )
                print(f"  [{slug}] captured #{len(samples)} ({samples[-1].language}): {reply[:58]}...")
                if len(samples) >= 10:
                    return samples
    return samples


def offline_samples() -> list[Sample]:
    return [
        Sample(
            index=i + 1,
            question="(stored sample)",
            reply=reply,
            tenant="captured",
            language="roman_urdu" if is_roman_urdu(reply) else "english",
        )
        for i, reply in enumerate(FALLBACK_REPLIES)
    ]


async def render_edge(text: str, voice: str, destination: Path) -> float:
    """Synthesize with edge-tts. Returns seconds taken."""
    import edge_tts

    started = time.perf_counter()
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(destination))
    return time.perf_counter() - started


def render_sapi(text: str, destination: Path) -> float:
    """Synthesize with the offline Windows voice, as a no-network baseline."""
    import win32com.client

    started = time.perf_counter()
    engine = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(str(destination), 3)  # 3 = create for write
    engine.AudioOutputStream = stream
    engine.Speak(text)
    stream.Close()
    return time.perf_counter() - started


MIME_BY_SUFFIX = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}


async def transcribe_with_groq(audio: Path, api_key: str) -> tuple[str, float]:
    """Round trip: can Whisper read back what the TTS just said?

    Groq's transcription endpoint accepts mp3 directly, so edge-tts output needs no
    conversion and the spike stays free of an ffmpeg dependency.
    """
    started = time.perf_counter()
    mime = MIME_BY_SUFFIX.get(audio.suffix.lower(), "application/octet-stream")
    async with httpx.AsyncClient(timeout=90) as client:
        # Groq's free tier throttles aggressively; without backoff the spike measures
        # the rate limit instead of the audio.
        for attempt in range(4):
            with audio.open("rb") as handle:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio.name, handle, mime)},
                    data={"model": "whisper-large-v3-turbo", "response_format": "json"},
                )
            if response.status_code != 429:
                break
            wait = float(response.headers.get("retry-after", 0) or (5 * (attempt + 1)))
            print(f"      rate limited, waiting {wait:.0f}s (attempt {attempt + 1}/4)")
            await asyncio.sleep(min(wait + 1, 30))
    elapsed = time.perf_counter() - started
    if response.status_code != 200:
        return f"<HTTP {response.status_code}>", elapsed
    return response.json().get("text", "").strip(), elapsed


def similarity(left: str, right: str) -> float:
    """Word overlap between the spoken text and what Whisper heard."""
    import difflib

    return difflib.SequenceMatcher(None, left.lower().split(), right.lower().split()).ratio()


def has_non_latin(text: str) -> bool:
    """Whisper often returns Urdu/Devanagari script for Roman Urdu audio."""
    return any("؀" <= c <= "ۿ" or "ऀ" <= c <= "ॿ" for c in text)


def content_tokens(text: str) -> set[str]:
    """The parts a caller must hear correctly: product words and numbers.

    Roman Urdu grammar words are not worth scoring - a customer does not care
    whether "hai" came back as "hai" or "hai" in another script. Product names and
    prices are the whole point of the call, and Whisper keeps those in Latin even
    when it renders the surrounding sentence in Urdu script.
    """
    import re

    tokens = set()
    for raw in re.findall(r"[A-Za-z]{3,}|\d[\d,]*", text):
        token = raw.replace(",", "").lower()
        if token.isdigit():
            tokens.add(token.lstrip("0") or "0")
        elif token not in GRAMMAR_WORDS:
            tokens.add(token)
    return tokens


# Function words in both languages; excluded so the score reflects content, not filler.
GRAMMAR_WORDS = {
    "the", "and", "you", "are", "for", "can", "any", "our", "have", "here", "this", "that",
    "with", "would", "like", "some", "about", "please", "your", "them", "these", "there",
    "hai", "hain", "aap", "mein", "kar", "ka", "ki", "ke", "aur", "kya", "yeh", "koi",
    "diya", "liya", "sakte", "nahi", "jee", "main", "raha", "rahe", "hoon", "gaya",
}


def content_recall(said: str, heard: str) -> float:
    """Fraction of business-critical tokens that survived the round trip."""
    wanted = content_tokens(said)
    if not wanted:
        return 1.0
    return round(len(wanted & content_tokens(heard)) / len(wanted), 3)


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path)) as handle:
            return handle.getnframes() / float(handle.getframerate())
    except Exception:
        return 0.0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use stored replies instead of calling the backend.")
    parser.add_argument("--no-stt", action="store_true", help="Skip the Whisper round trip.")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    print("=" * 74)
    print("SPIKE 1 - TTS and Roman Urdu (decision D1)")
    print("=" * 74)

    if args.offline:
        samples = offline_samples()
        print(f"\nUsing {len(samples)} stored replies (--offline).")
    else:
        print(f"\nCollecting live replies from {API} ...")
        samples = await collect_live_replies()
        if not samples:
            print("  no live replies; falling back to stored samples")
            samples = offline_samples()

    roman = sum(1 for s in samples if s.language == "roman_urdu")
    print(f"\n{len(samples)} replies: {roman} Roman Urdu, {len(samples) - roman} English")

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key and not args.no_stt:
        env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GROQ_API_KEY="):
                    groq_key = line.split("=", 1)[1].strip()
                    break
    do_stt = bool(groq_key) and not args.no_stt
    print(f"Whisper round trip: {'enabled' if do_stt else 'disabled'}")

    print("\nSynthesizing...")
    for sample in samples:
        for key, voice, _ in VOICE_CANDIDATES:
            out = RESULTS / f"sample{sample.index:02d}_{key}.mp3"
            try:
                seconds = await render_edge(sample.reply, voice, out)
                sample.renders.append({"engine": key, "voice": voice, "file": out.name, "synthSeconds": round(seconds, 2)})
                print(f"  #{sample.index:02d} {key:12} {seconds:5.2f}s -> {out.name}")
            except Exception as exc:
                print(f"  #{sample.index:02d} {key:12} FAILED: {type(exc).__name__}: {exc}")
                sample.renders.append({"engine": key, "voice": voice, "error": str(exc)[:160]})

        out = RESULTS / f"sample{sample.index:02d}_sapi.wav"
        try:
            seconds = render_sapi(sample.reply, out)
            sample.renders.append({"engine": "windows_sapi", "voice": "default", "file": out.name,
                                   "synthSeconds": round(seconds, 2), "durationSeconds": round(wav_duration(out), 2)})
            print(f"  #{sample.index:02d} {'windows_sapi':12} {seconds:5.2f}s -> {out.name}")
        except Exception as exc:
            print(f"  #{sample.index:02d} {'windows_sapi':12} FAILED: {type(exc).__name__}")
            sample.renders.append({"engine": "windows_sapi", "error": str(exc)[:160]})

    if do_stt:
        print("\nWhisper round trip (TTS output -> Groq Whisper -> compare)...")
        for sample in samples:
            for render in sample.renders:
                if "file" not in render:
                    continue
                audio = RESULTS / render["file"]
                heard, elapsed = await transcribe_with_groq(audio, groq_key)
                failed = heard.startswith("<HTTP")
                render["heard"] = heard
                render["sttSeconds"] = round(elapsed, 2)
                render["sttFailed"] = failed
                if not failed:
                    render["contentRecall"] = content_recall(sample.reply, heard)
                    render["similarity"] = round(similarity(sample.reply, heard), 3)
                    render["scriptShift"] = has_non_latin(heard)
                    flag = "OK " if render["contentRecall"] >= 0.7 else "LOW"
                    note = " [script-shift]" if render["scriptShift"] else ""
                    print(f"  #{sample.index:02d} {render['engine']:12} {flag} recall={render['contentRecall']:.2f} ({elapsed:.1f}s){note}")
                else:
                    print(f"  #{sample.index:02d} {render['engine']:12} ERR {heard}")
                await asyncio.sleep(1.5)  # stay under the free-tier rate limit

    payload = [
        {"index": s.index, "tenant": s.tenant, "language": s.language,
         "question": s.question, "reply": s.reply, "renders": s.renders}
        for s in samples
    ]
    (RESULTS / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(samples, do_stt)
    print(f"\nWrote {RESULTS / 'REPORT.md'}")
    print("Listen to the files, then fill in the verdict at the bottom of the report.")


def write_report(samples: list[Sample], did_stt: bool) -> None:
    lines = [
        "# Spike 1 - TTS and Roman Urdu",
        "",
        "Answers decision **D1**: which language route the voice channel should take.",
        "",
        "## How to read this",
        "",
        "Play each sample and judge two things: is it intelligible, and does it sound",
        "like a person answering a phone. The similarity column is a proxy, not a verdict -",
        "a high score with unnatural prosody is still a bad phone experience.",
        "",
        f"- Samples: **{len(samples)}** ({sum(1 for s in samples if s.language == 'roman_urdu')} Roman Urdu)",
        f"- Whisper round trip: **{'run' if did_stt else 'skipped'}**",
        "",
    ]

    by_engine: dict[str, list[float]] = {}
    shifts: dict[str, int] = {}
    for sample in samples:
        for render in sample.renders:
            if "contentRecall" in render:
                by_engine.setdefault(render["engine"], []).append(render["contentRecall"])
                if render.get("scriptShift"):
                    shifts[render["engine"]] = shifts.get(render["engine"], 0) + 1

    if by_engine:
        lines += [
            "## Round-trip content recall by engine",
            "",
            "Scored on the tokens that matter on a sales call - product words and prices.",
            "Grammar words are excluded, and a transcription returned in Urdu/Devanagari",
            "script is not penalised as long as the product names and numbers survive.",
            "",
            "| Engine | Renders | Mean content recall | Script shifts | Verdict |",
            "|---|---|---|---|---|",
        ]
        for engine, scores in sorted(by_engine.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
            mean = sum(scores) / len(scores)
            verdict = "usable" if mean >= 0.85 else ("borderline" if mean >= 0.7 else "poor")
            lines.append(f"| {engine} | {len(scores)} | {mean:.2f} | {shifts.get(engine, 0)} | {verdict} |")
        lines.append("")

    if did_stt:
        roman = [(s, r) for s in samples if s.language == "roman_urdu" for r in s.renders if "contentRecall" in r]
        english = [(s, r) for s in samples if s.language == "english" for r in s.renders if "contentRecall" in r]
        lines += ["## The question that matters", "",
                  "If Roman Urdu scores clearly worse than English on every engine, route (a) -",
                  "forcing English on the voice channel - is the safe choice for the demo.", ""]
        for label, rows in (("Roman Urdu", roman), ("English", english)):
            if rows:
                mean = sum(r["contentRecall"] for _, r in rows) / len(rows)
                lines.append(f"- **{label}**: mean content recall {mean:.2f} across {len(rows)} renders")
        lines.append("")

    lines += ["## Samples", ""]
    for sample in samples:
        lines += [f"### Sample {sample.index} ({sample.language}, tenant: {sample.tenant})", "",
                  f"**Asked:** {sample.question}", "", f"**Reply:** {sample.reply}", "",
                  "| Engine | File | Synth | STT | Content recall | Script | Whisper heard |",
                  "|---|---|---|---|---|---|---|"]
        for render in sample.renders:
            if "error" in render:
                lines.append(f"| {render['engine']} | - | FAILED | - | - | {render['error'][:60]} |")
                continue
            heard = str(render.get("heard", ""))[:70].replace("|", "/")
            script = "urdu/devanagari" if render.get("scriptShift") else "latin"
            lines.append(
                f"| {render['engine']} | `{render.get('file', '-')}` | {render.get('synthSeconds', '-')}s "
                f"| {render.get('sttSeconds', '-')}s | {render.get('contentRecall', '-')} | {script} | {heard} |"
            )
        lines.append("")

    lines += [
        "## Verdict (fill in after listening)",
        "",
        "```text",
        "Chosen route (a english-only / b transliterate / c multilingual): ______",
        "Chosen voice:                                                     ______",
        "Reason:                                                           ______",
        "Acceptable on a phone call? (yes/no)                              ______",
        "```",
        "",
        "Record this in the FYP report as the justification for D1.",
    ]
    (RESULTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Windows SAPI will be skipped on this platform.")
    asyncio.run(main())
