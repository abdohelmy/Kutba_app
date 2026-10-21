"""Outbound-only worker. Optional, bounded local transcript debugging; never saves audio."""

import argparse
import base64
import getpass
import io
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import zlib
from array import array
from datetime import UTC, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

API_DEFAULT = "https://35.207.58.39.sslip.io/api/v1"
ASR_DEFAULT = "http://127.0.0.1:8001/v1"
MODEL_DEFAULT = "large-v3"
COHERE_MODEL = "CohereLabs/cohere-transcribe-arabic-07-2026"
SEMANTIC_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class SemanticShadow:
    """Local CPU experiment only. Never supplies a result to the matcher."""

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(SEMANTIC_MODEL, device="cpu")
        self.key = None
        self.embeddings = None

    def compare(self, passages, text):
        started = time.monotonic()
        # Bound experimental work and make truncation explicit in the log.
        selected = passages[:512]
        key = tuple((p["index"], p["text"]) for p in selected)
        if not key or len(text.split()) < 4:
            return {"skipped": "insufficient_text"}
        if key != self.key:
            self.embeddings = self.model.encode(
                [p["text"] for p in selected], normalize_embeddings=True,
                show_progress_bar=False, batch_size=16,
            )
            self.key = key
        query = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        scores = self.embeddings @ query
        order = sorted(range(len(selected)), key=lambda i: float(scores[i]), reverse=True)[:3]
        return {
            "model": SEMANTIC_MODEL, "mode": "shadow_only",
            "candidates": [{"passage": selected[i]["index"], "similarity": round(float(scores[i]), 4)}
                           for i in order],
            "margin": round(float(scores[order[0]] - scores[order[1]]), 4) if len(order) > 1 else None,
            "passage_count": len(selected), "corpus_truncated": len(passages) > len(selected),
            "max_sequence_tokens": self.model.max_seq_length,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


class CohereEngine:
    """Single-clip CUDA ASR with CPU Silero gating. No remote inference."""

    def __init__(self, model):
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps
        from transformers import AutoProcessor, CohereAsrForConditionalGeneration

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. Check nvidia-smi inside WSL.")
        torch.set_num_threads(2)
        self.torch = torch
        self.vad = load_silero_vad(onnx=True)
        self.timestamps = get_speech_timestamps
        self.processor = AutoProcessor.from_pretrained(model)
        self.model = CohereAsrForConditionalGeneration.from_pretrained(
            model, dtype=torch.float16, device_map="cuda:0",
        ).eval()

    def speech_spans(self, samples):
        tensor = self.torch.tensor(samples, dtype=self.torch.float32)
        # Reset between independent chunks/sessions; no state crosses mosques.
        self.vad.reset_states()
        return self.timestamps(tensor, self.vad, sampling_rate=16000,
                               threshold=0.6, min_speech_duration_ms=250,
                               min_silence_duration_ms=250, speech_pad_ms=0)

    def transcribe(self, samples, *, quick):
        import numpy as np
        with self.torch.inference_mode():
            inputs = self.processor(np.asarray(samples, dtype=np.float32),
                                    sampling_rate=16000, return_tensors="pt", language="ar")
            chunk_index = inputs.get("audio_chunk_index")
            inputs.to(self.model.device, dtype=self.model.dtype)
            output = self.model.generate(**inputs, max_new_tokens=80 if quick else 160,
                                         do_sample=False, num_beams=1)
            decoded = self.processor.decode(output, skip_special_tokens=True,
                                            audio_chunk_index=chunk_index, language="ar")
            return decoded[0] if isinstance(decoded, list) else decoded


def cohere_transcription(audio, engine, diagnostics=None, *, quick=False):
    started = time.monotonic()
    with wave.open(io.BytesIO(audio)) as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            raise ValueError("Expected mono 16 kHz PCM16 WAV")
        pcm = array("h", wav.readframes(wav.getnframes()))
    samples = [value / 32768 for value in pcm]
    duration = len(samples) / 16000
    rms = math.sqrt(sum(x*x for x in samples) / len(samples)) if samples else 0
    details = diagnostics if diagnostics is not None else {}
    details.update(audio_seconds=round(duration, 3), rms=round(rms, 6),
                   model_called=False, vad_model="silero-onnx-cpu", vad_skipped=True)
    # Only near-digital silence bypasses VAD; quiet speech still gets evaluated.
    if rms < 0.0001:
        details.update(vad_reason="digital_silence", speech_seconds=0, speech_fraction=0)
        return []
    spans = engine.speech_spans(samples)
    speech_samples = sum(max(0, min(len(samples), s["end"]) - max(0, s["start"])) for s in spans)
    speech_seconds = speech_samples / 16000
    fraction = speech_samples / len(samples)
    details.update(vad_ms=round((time.monotonic()-started)*1000),
                   speech_seconds=round(speech_seconds, 3), speech_fraction=round(fraction, 3))
    if not spans or speech_seconds < 0.45 or fraction < 0.15:
        details["vad_reason"] = "insufficient_speech"
        return []
    # Keep natural internal pauses; trim leading/trailing noise with 150 ms padding.
    start, end = max(0, spans[0]["start"]-2400), min(len(samples), spans[-1]["end"]+2400)
    details.update(vad_skipped=False, vad_reason="speech_detected",
                   asr_audio_seconds=round((end-start)/16000, 3), model_called=True)
    inference_started = time.monotonic()
    text = engine.transcribe(samples[start:end], quick=quick).strip()[:4000]
    encoded = text.encode("utf-8")
    candidate = dict(reference="none", text=text, avg_logprob=None, no_speech_prob=None,
                     compression_ratio=len(encoded)/len(zlib.compress(encoded)) if encoded else 0)
    details.update(inference_ms=round((time.monotonic()-inference_started)*1000),
                   candidates=[candidate], acoustic_scores_available=False)
    if candidate["compression_ratio"] > 2.4:
        details["asr_rejected"] = "repetitive_output"
        return []
    return [candidate] if text else []


class DebugLog:
    """Explicit local opt-in. Never overwrite an existing log or capture credentials."""

    def __init__(self, path, max_bytes=2_000_000):
        self.path = Path(path).expanduser().resolve()
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.file = os.fdopen(descriptor, "w", encoding="utf-8")
        self.max_bytes = max_bytes
        self.bytes = 0
        self.disabled = False

    def write(self, **entry):
        if self.disabled:
            return
        entry["time_utc"] = datetime.now(UTC).isoformat()
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        size = len(line.encode("utf-8"))
        if self.bytes + size > self.max_bytes:
            self.disabled = True
            print("Debug log limit reached; logging stopped. Speech processing continues.", flush=True)
            return
        try:
            self.file.write(line)
            self.file.flush()
            self.bytes += size
        except OSError:
            self.disabled = True
            print("Could not write debug log; logging stopped. Speech processing continues.", flush=True)

    def close(self):
        self.file.close()


def request(
    url,
    *,
    token=None,
    data=None,
    method="GET",
    content_type="application/json",
    timeout=20,
):
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = json.dumps(data).encode() if isinstance(data, dict) else data
    with urllib.request.urlopen(
        urllib.request.Request(url, data=payload, method=method, headers=headers),
        timeout=timeout,
    ) as response:
        return json.loads(response.read()) if response.status != 204 else None


def transcription(audio, asr_url, model, diagnostics=None):
    with wave.open(io.BytesIO(audio)) as wav:
        duration = wav.getnframes() / wav.getframerate()
        samples = array("h", wav.readframes(wav.getnframes()))
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768 if samples else 0
    if diagnostics is not None:
        diagnostics.update(audio_seconds=round(duration, 3), rms=round(rms, 6),
                           silence_skipped=rms < 0.004, model_called=False)
    if rms < 0.004:
        return ""  # Silence/noise floor: don't ask the model to invent speech.
    boundary = "khutba-audio-boundary"
    chunks = []
    for key, value in [
        ("model", model),
        ("language", "ar"),
        ("response_format", "json"),
    ]:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        )
    chunks.extend(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="speech.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
            audio,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    started = time.monotonic()
    if diagnostics is not None:
        diagnostics["model_called"] = True
    result = request(
        asr_url + "/audio/transcriptions",
        method="POST",
        data=b"".join(chunks),
        content_type="multipart/form-data; boundary=" + boundary,
        timeout=20,
    )
    text = str(result.get("text", ""))
    if diagnostics is not None:
        diagnostics.update(raw_stt_text=text[:4000], inference_ms=round((time.monotonic()-started)*1000))
    if "<asr_text>" in text:
        text = text.split("<asr_text>", 1)[1]
    return text.strip()[:4000]


def whisper_transcription(audio, engine, references, diagnostics=None, *, quick=False, verify_unprompted=False):
    """Sentence hints plus an independent decode during acquisition/recovery."""
    with wave.open(io.BytesIO(audio)) as wav:
        duration = wav.getnframes() / wav.getframerate()
        samples = array("h", wav.readframes(wav.getnframes()))
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768 if samples else 0
    if diagnostics is not None:
        diagnostics.update(audio_seconds=round(duration, 3), rms=round(rms, 6),
                           silence_skipped=rms < 0.004, model_called=False)
    if rms < 0.004:
        return []
    hints = [item for item in references[:2]
             if item.get("reference") in {"current", "next"} and item.get("text")]
    if quick or not hints:
        hints = [{"reference": "none", "text": ""}]
    elif len(hints) == 1:
        hints.append({"reference": "none", "text": ""})
    if verify_unprompted and not quick and not any(h["reference"] == "none" for h in hints):
        hints.insert(0, {"reference": "none", "text": ""})
    started = time.monotonic()
    alternatives = []
    passes = []
    for hint in hints:
        pass_started = time.monotonic()
        # Match faster-whisper's Tokenizer.encode(): reference text must not
        # inject start/end/task control tokens into the previous-text context.
        prompt = engine.hf_tokenizer.encode(
            " " + hint["text"][:1200].strip(), add_special_tokens=False
        ).ids[:180] if hint["text"] else None
        segments, _ = engine.transcribe(
            io.BytesIO(audio), language="ar", task="transcribe", beam_size=3 if quick else 5,
            temperature=0.0, condition_on_previous_text=False,
            initial_prompt=prompt, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            max_new_tokens=80 if quick else 160,
        )
        segments = list(segments)  # Inference is lazy; finish this pass before the next.
        count = sum(max(1, len(segment.tokens)) for segment in segments)
        candidate = {
            "reference": hint["reference"],
            "text": " ".join(segment.text.strip() for segment in segments).strip()[:4000],
            "avg_logprob": sum(segment.avg_logprob * max(1, len(segment.tokens))
                               for segment in segments) / count if count else -100.0,
            "no_speech_prob": max((segment.no_speech_prob for segment in segments), default=1.0),
            "compression_ratio": max((segment.compression_ratio for segment in segments), default=0.0),
        }
        alternatives.append(candidate)
        passes.append({**candidate, "inference_ms": round((time.monotonic() - pass_started) * 1000)})
    if diagnostics is not None:
        diagnostics.update(model_called=True, candidates=passes,
                           inference_ms=round((time.monotonic() - started) * 1000))
    return alternatives


def run(api_url, asr_url, model, token, debug_log=None, *, backend="vllm", compute_type="int8_float16",
        semantic_shadow=False):
    if semantic_shadow and debug_log is None:
        raise ValueError("Semantic shadow mode requires an explicit debug log")
    shadow = None
    if semantic_shadow:
        print("Loading semantic shadow model on the CPU.", flush=True)
        try:
            shadow = SemanticShadow()
        except ImportError:
            raise SystemExit("Install semantic dependencies with python -m pip install -r requirements-semantic.txt, or use --no-semantic-shadow.") from None
    with ThreadPoolExecutor(max_workers=1) as pool:
        return _run(api_url, asr_url, model, token, debug_log, backend=backend,
                    compute_type=compute_type, shadow=shadow, pool=pool)


def _run(api_url, asr_url, model, token, debug_log, *, backend, compute_type, shadow, pool):
    future = None
    engine = None
    if backend == "cohere":
        print("Loading Cohere Arabic on the GPU and Silero VAD on the CPU.", flush=True)
        try:
            engine = CohereEngine(model)
        except ImportError:
            raise SystemExit("Install requirements-cohere.txt in the khutba-cohere environment.") from None
        except (OSError, RuntimeError):
            raise SystemExit("Could not load Cohere. Check CUDA, free GPU memory, and Hugging Face model access (hf auth login).") from None
    if backend == "whisper":
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise SystemExit("Install the Whisper dependencies first: python -m pip install -r requirements-whisper.txt") from None
        print("Loading Whisper on the GPU; the first run downloads the model.", flush=True)
        engine = WhisperModel(model, device="cuda", compute_type=compute_type, num_workers=1)
    connected = False
    while True:
        try:
            # Only report ready after the local model server responds.
            if backend == "vllm":
                request(asr_url + "/models", timeout=5)
            if future is not None and future.done():
                try:
                    details = future.result()
                except Exception as exc:
                    # Optional instrumentation must not stop live tracking.
                    details = {"error_type": type(exc).__name__}
                debug_log.write(event="semantic_shadow", sequence=shadow_sequence,
                                session_id=shadow_session, **details)
                future = None
            job = request(api_url + "/live-worker/job" + ("?semantic_shadow=true" if shadow else ""), token=token)
            if not connected:
                print(
                    "Speech worker connected. Waiting for a mosque's live session.",
                    flush=True,
                )
                connected = True
            if not job:
                time.sleep(0.5)
                continue
            if backend == "cohere" and not job.get("supports_unscored_candidates"):
                request(api_url + "/live-worker/offline", token=token, method="POST")
                raise SystemExit("The API needs the Cohere compatibility update. Deploy it before starting this worker.")
            audio = b""
            text = ""
            alternatives = None
            diagnostics = {"kind": job.get("kind", "full")} if debug_log else None
            chunk_started = time.monotonic()
            try:
                audio = base64.b64decode(job["audio_base64"], validate=True)
                if backend == "cohere":
                    alternatives = cohere_transcription(audio, engine, diagnostics, quick=job.get("kind") == "quick")
                elif engine is not None:
                    alternatives = whisper_transcription(audio, engine, job.get("references", []), diagnostics,
                                                         quick=job.get("kind") == "quick",
                                                         verify_unprompted=job.get("verify_unprompted", False))
                else:
                    text = transcription(audio, asr_url, model, diagnostics)
            except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
                if diagnostics is not None:
                    diagnostics.update(error_type=type(exc).__name__, http_status=getattr(exc,"code",None))
                    debug_log.write(event="stt_error", sequence=job["sequence"], **diagnostics)
                request(api_url + "/live-worker/offline", token=token, method="POST")
                text = ""
                print(
                    "Local transcription failed. Check the GPU/runtime setup.", flush=True
                )
            try:
                result = request(
                    api_url + "/live-worker/result",
                    token=token,
                    method="POST",
                    data={
                        "session_id": job["session_id"],
                        "job_id": job["job_id"],
                        "text": text,
                        **({"candidates": alternatives} if alternatives else {}),
                        **({"debug": True} if debug_log else {}),
                    },
                )
                if diagnostics is not None:
                    diagnostics["matcher"] = result.get("debug") if isinstance(result, dict) else None
                    diagnostics["result_status"] = result.get("status") if isinstance(result, dict) else None
                    if alternatives:
                        selected = (diagnostics["matcher"] or {}).get("selected_reference")
                        text = next((item["text"] for item in alternatives if item["reference"] == selected),
                                    alternatives[0]["text"] if len(alternatives) == 1 else "")
                if backend in {"whisper", "cohere"} and time.monotonic() - chunk_started > 4:
                    print("Speech processing took more than 4 seconds; live tracking may lag. Timing is in the debug log when enabled.", flush=True)
            except urllib.error.HTTPError as exc:
                if diagnostics is not None:
                    diagnostics["result_http_status"] = exc.code
                if exc.code != 409:
                    raise
            finally:
                if debug_log:
                    debug_log.write(event="chunk", sequence=job["sequence"], stt_text=text,
                                    total_ms=round((time.monotonic()-chunk_started)*1000), **diagnostics)
            # Submit only AFTER the authoritative result, never hold it up.
            # One task at a time; no backlog of private speech or stale jobs.
            if shadow and job.get("kind") == "full" and text.strip():
                passages = job.get("semantic_passages")
                if passages and future is None:
                    shadow_sequence, shadow_session = job["sequence"], job["session_id"]
                    future = pool.submit(shadow.compare, passages, text)
                else:
                    debug_log.write(event="semantic_shadow", sequence=job["sequence"],
                                    session_id=job["session_id"],
                                    skipped="busy" if future else "api_corpus_unavailable")
            del (
                job,
                audio,
                text,
                alternatives,
            )  # No recordings; transcripts are retained only in explicit debug logs.
            diagnostics = None
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SystemExit(
                    "Worker token was rejected. Issue a new token in the owner dashboard."
                ) from None
            print(f"Connection unavailable (HTTP {exc.code}); retrying.", flush=True)
            connected = False
            time.sleep(5)
        except (OSError, ValueError, urllib.error.URLError):
            print("API or local model unavailable; retrying.", flush=True)
            connected = False
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API_DEFAULT)
    parser.add_argument("--asr", default=ASR_DEFAULT)
    parser.add_argument("--backend", choices=("cohere", "whisper", "vllm"), default="cohere")
    parser.add_argument("--model", default=None)
    parser.add_argument("--compute-type", choices=("int8_float16", "float16"), default="int8_float16")
    logging = parser.add_mutually_exclusive_group()
    logging.add_argument("--debug-log", nargs="?", const="auto", default="auto", metavar="PATH",
                         help="Local Arabic transcript/diagnostics log (enabled by default); optional custom path")
    logging.add_argument("--no-debug-log", dest="debug_log", action="store_const", const=None,
                         help="Disable local logging and semantic shadow analysis")
    parser.add_argument("--semantic-shadow", action=argparse.BooleanOptionalAction, default=True,
                        help="CPU semantic suggestions in debug logs (enabled by default); never moves the highlight")
    args = parser.parse_args()
    if args.semantic_shadow and not args.debug_log:
        args.semantic_shadow = False
    args.model = args.model or {"cohere": COHERE_MODEL, "whisper": MODEL_DEFAULT,
                               "vllm": "Qwen/Qwen3-ASR-1.7B"}[args.backend]
    api = urllib.parse.urlparse(args.api)
    asr = urllib.parse.urlparse(args.asr)
    if api.scheme != "https" and api.hostname not in {"localhost", "127.0.0.1"}:
        parser.error("Use HTTPS for the remote API")
    if asr.hostname not in {"localhost", "127.0.0.1"}:
        parser.error(
            "Run the local ASR server on loopback; do not expose a public port"
        )
    token = getpass.getpass(
        "Paste the speech-worker token from the owner dashboard (hidden): "
    )
    if not token.strip():
        parser.error("A worker token is required")
    debug_log = None
    if args.debug_log:
        path = args.debug_log
        if path == "auto":
            directory = Path.home() / "khutba-live-debug"
            path = directory / ("stt-debug-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f") + ".jsonl")
        try:
            if args.debug_log == "auto":
                directory.mkdir(mode=0o700, exist_ok=True)
            debug_log = DebugLog(path)
        except OSError:
            parser.error("Could not create debug log. Choose an existing folder and a new filename.")
        print(f"Debug log: {debug_log.path}\nContains private speech text. No audio or token is saved.", flush=True)
        debug_log.write(event="debug_started", model=args.model, backend=args.backend,
                        semantic_shadow=args.semantic_shadow,
                        compute_type="float16" if args.backend == "cohere" else args.compute_type if args.backend == "whisper" else None)
    try:
        run(args.api.rstrip("/"), args.asr.rstrip("/"), args.model, token.strip(), debug_log,
            backend=args.backend, compute_type=args.compute_type, semantic_shadow=args.semantic_shadow)
    except KeyboardInterrupt:
        try:
            request(
                args.api.rstrip("/") + "/live-worker/offline",
                token=token.strip(),
                method="POST",
                timeout=3,
            )
        except (OSError, urllib.error.URLError):
            pass
        print("Speech worker stopped.")
    finally:
        if debug_log:
            debug_log.close()


if __name__ == "__main__":
    main()
