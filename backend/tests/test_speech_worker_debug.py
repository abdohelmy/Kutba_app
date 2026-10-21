import base64
import importlib.util
import io
import json
import stat
import sys
import urllib.error
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    "speech_worker", Path(__file__).resolve().parents[2] / "live-worker" / "worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_semantic_shadow_caches_corpus_and_returns_only_rankings(monkeypatch):
    class Matrix:
        def __matmul__(self, query):
            return [0.2, 0.8]
    class Encoder:
        max_seq_length = 128
        def __init__(self):
            self.calls = []
        def encode(self, texts, **kwargs):
            self.calls.append(texts)
            assert kwargs["normalize_embeddings"]
            return Matrix() if len(texts) == 2 else [[1]]
    encoder = Encoder()
    def create(model, device):
        assert device == "cpu"
        return encoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=create))
    shadow = worker.SemanticShadow()
    corpus = [{"index": 2, "text": "نص أول"}, {"index": 3, "text": "نص آخر"}]
    for _ in range(2):
        result = shadow.compare(corpus, "هذا نص عربي للاختبار")
        assert result["mode"] == "shadow_only"
        assert result["candidates"][0] == {"passage": 3, "similarity": 0.8}
        assert result["margin"] == 0.6
        assert "نص" not in json.dumps(result, ensure_ascii=False)
    assert len(encoder.calls) == 3  # One corpus encoding, two transcripts.
    corpus[0]["text"] = "تعديل النص"
    shadow.compare(corpus, "هذا نص عربي للاختبار")
    assert len(encoder.calls) == 5


def test_semantic_shadow_requires_explicit_private_debug_log():
    with pytest.raises(ValueError, match="debug log"):
        worker.run("unused", "unused", "unused", "secret", semantic_shadow=True)


def test_semantic_shadow_posts_tracking_first_and_never_queues_backlog(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "CohereEngine", lambda _: FakeCohere([{"start": 0, "end": 16000}]))
    posted, submitted = [], []
    class Pool:
        def submit(self, *args):
            assert len(posted) == 1
            submitted.append(args)
            return SimpleNamespace(done=lambda: False)
    def request(url, **kwargs):
        if "/job?" in url:
            if len(posted) == 2:
                raise KeyboardInterrupt
            return {"session_id": "s", "job_id": str(len(posted)), "sequence": len(posted),
                    "kind": "full", "supports_unscored_candidates": True,
                    "audio_base64": base64.b64encode(audio()).decode(),
                    "semantic_passages": [{"index": 0, "text": "نص عربي"}]}
        posted.append(kwargs["data"])
        assert "semantic" not in json.dumps(kwargs["data"])
        return {"status": "accepted", "debug": {"selected_reference": "none"}}
    monkeypatch.setattr(worker, "request", request)
    log = worker.DebugLog(tmp_path / "shadow.jsonl")
    try:
        with pytest.raises(KeyboardInterrupt):
            worker._run("https://api.test", "unused", worker.COHERE_MODEL, "secret", log,
                        backend="cohere", compute_type="float16",
                        shadow=SimpleNamespace(compare=lambda *args: None), pool=Pool())
    finally:
        log.close()
    assert len(submitted) == 1 and len(posted) == 2
    entries = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert entries[-1]["skipped"] == "busy"


@pytest.mark.parametrize("backend,selected,expected", [
    ("cohere", None, worker.COHERE_MODEL),
    ("whisper", None, "large-v3"), ("whisper", "large-v2", "large-v2"),
    ("vllm", None, "Qwen/Qwen3-ASR-1.7B"),
])
def test_worker_backend_selection_keeps_whisper_and_vllm_options(monkeypatch, backend, selected, expected):
    argv = ["worker.py", "--no-debug-log", "--backend", backend] + (["--model", selected] if selected else [])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(worker.getpass, "getpass", lambda _: "private-token")
    received = []
    monkeypatch.setattr(worker, "run", lambda api, asr, model, token, log, **kw: received.append((model, kw["backend"])))
    worker.main()
    assert received == [(expected, backend)]


@pytest.mark.parametrize("flags,logged,semantic", [
    ([], True, True),
    (["--no-semantic-shadow"], True, False),
    (["--no-debug-log"], False, False),
    (["--debug-log", "custom.jsonl"], True, True),
])
def test_cli_defaults_and_disable_options(monkeypatch, tmp_path, flags, logged, semantic):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(worker.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["worker.py", *flags])
    monkeypatch.setattr(worker.getpass, "getpass", lambda _: "private-token")
    received = []
    def run(api, asr, model, token, log, **kwargs):
        received.append((model, kwargs["backend"], log is not None, kwargs["semantic_shadow"]))
    monkeypatch.setattr(worker, "run", run)
    worker.main()
    assert received == [(worker.COHERE_MODEL, "cohere", logged, semantic)]
    paths = list(tmp_path.rglob("*.jsonl"))
    assert len(paths) == int(logged)
    if paths:
        entry = json.loads(paths[0].read_text())
        assert entry["semantic_shadow"] == semantic
        assert "private-token" not in paths[0].read_text()


class FakeWhisper:
    def __init__(self):
        self.calls = []
        self.completed = 0
        def encode(hint, *, add_special_tokens=True):
            assert add_special_tokens is False, "Reference hints must contain text tokens only"
            return SimpleNamespace(ids=list(range(len(hint))))
        self.hf_tokenizer = SimpleNamespace(encode=encode)

    def transcribe(self, stream, **kwargs):
        assert len(self.calls) == self.completed  # First generator finished before second call.
        self.calls.append((stream.read(), kwargs))
        def generate():
            yield SimpleNamespace(text="إن الصدق يهدي القلب", tokens=[1, 2, 3, 4],
                                  avg_logprob=-0.3, no_speech_prob=0.02, compression_ratio=1.2)
            self.completed += 1
        return generate(), None


def test_whisper_decodes_same_audio_twice_with_bounded_separate_hints():
    engine = FakeWhisper()
    details = {}
    candidates = worker.whisper_transcription(audio(), engine, [
        {"reference": "current", "text": "الجملة الحالية " * 100},
        {"reference": "next", "text": "الجملة التالية"},
    ], details)
    assert engine.completed == 2
    assert engine.calls[0][0] == engine.calls[1][0] == audio()
    first, second = (call[1] for call in engine.calls)
    assert len(first["initial_prompt"]) == 180
    assert first["initial_prompt"] != second["initial_prompt"]
    assert first["language"] == "ar" and first["vad_filter"]
    assert first["temperature"] == 0 and not first["condition_on_previous_text"]
    assert "prefix" not in first
    assert [item["reference"] for item in candidates] == ["current", "next"]
    assert details["model_called"] and len(details["candidates"]) == 2
    assert "الجملة" not in json.dumps(details, ensure_ascii=False)
    assert worker.whisper_transcription(audio(0), engine, [], {}) == []
    assert engine.completed == 2


def test_short_check_uses_one_unprompted_decode():
    engine = FakeWhisper()
    candidates = worker.whisper_transcription(audio(), engine,
        [{"reference":"next", "text":"لا يجب فرض الجملة التالية"}], quick=True)
    assert engine.completed == 1
    assert engine.calls[0][1]["initial_prompt"] is None
    assert candidates[0]["reference"] == "none"
    assert engine.calls[0][1]["max_new_tokens"] == 80


def test_uncertain_full_check_adds_unprompted_recovery_without_extra_quick_passes():
    refs=[{"reference":"current","text":"الجملة الحالية"},
          {"reference":"next","text":"الجملة التالية"}]
    engine=FakeWhisper()
    result=worker.whisper_transcription(audio(),engine,refs,verify_unprompted=True)
    assert [item["reference"] for item in result] == ["none","current","next"]
    assert engine.calls[0][1]["initial_prompt"] is None and engine.completed == 3
    quick=FakeWhisper()
    assert len(worker.whisper_transcription(audio(),quick,refs,quick=True,verify_unprompted=True)) == 1
    assert quick.completed == 1


@pytest.mark.parametrize("references,expected", [([], ["none"]),
    ([{"reference":"current", "text":"آخر جملة"}], ["current", "none"])])
def test_whisper_handles_missing_reference_and_last_sentence(references, expected):
    candidates = worker.whisper_transcription(audio(), FakeWhisper(), references)
    assert [item["reference"] for item in candidates] == expected


def test_whisper_worker_sends_one_result_for_two_decodes(monkeypatch, tmp_path):
    engine = FakeWhisper()
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *a, **kw: engine))
    posted = []
    def request(url, **kwargs):
        if url.endswith("/job"):
            if posted:
                raise KeyboardInterrupt
            return {"session_id":"s", "job_id":"j", "sequence":1,
                    "audio_base64":base64.b64encode(audio()).decode(), "references":[
                        {"reference":"current", "text":"السياق الأول"},
                        {"reference":"next", "text":"السياق التالي"}]}
        assert url.endswith("/result")  # No vLLM or third decode request.
        posted.append(kwargs["data"])
        return {"status":"accepted", "debug":{"selected_reference":"next", "reason":"matched"}}
    monkeypatch.setattr(worker, "request", request)
    log = worker.DebugLog(tmp_path / "whisper.jsonl")
    try:
        with pytest.raises(KeyboardInterrupt):
            worker.run("https://api.test", "unused", "large-v3", "secret", log, backend="whisper")
    finally:
        log.close()
    assert engine.completed == 2 and len(posted) == 1
    assert len(posted[0]["candidates"]) == 2
    entry = json.loads(log.path.read_text())
    assert entry["stt_text"] == "إن الصدق يهدي القلب"
    assert "السياق" not in log.path.read_text() and "secret" not in log.path.read_text()


def audio(value=2000):
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(int(value).to_bytes(2, "little", signed=True) * 16000)
    return data.getvalue()


class FakeCohere:
    def __init__(self, spans):
        self.spans = spans
        self.vad_calls = 0
        self.calls = []

    def speech_spans(self, samples):
        self.vad_calls += 1
        return self.spans

    def transcribe(self, samples, *, quick):
        self.calls.append((len(samples), quick))
        return "إن الصدق يهدي القلب ويجعل الإنسان ثابت الخطوات صافي النية"


@pytest.mark.parametrize("spans", [[], [{"start":1000,"end":3000}]])
def test_cohere_vad_blocks_loud_non_speech_and_short_bursts(spans):
    engine = FakeCohere(spans)
    diagnostics = {}
    assert worker.cohere_transcription(audio(12000), engine, diagnostics) == []
    assert engine.vad_calls == 1 and not engine.calls
    assert diagnostics["vad_reason"] == "insufficient_speech"
    assert diagnostics["model_called"] is False


def test_cohere_vad_silence_and_quiet_speech_and_null_confidence():
    engine = FakeCohere([{"start":4000,"end":12000}])
    assert worker.cohere_transcription(audio(0), engine, {}) == []
    assert not engine.calls and engine.vad_calls == 0
    diagnostics = {}
    candidates = worker.cohere_transcription(audio(30), engine, diagnostics, quick=True)
    assert engine.calls == [(12800, True)]  # 0.5 seconds plus edge padding.
    assert candidates[0]["avg_logprob"] is None and candidates[0]["no_speech_prob"] is None
    assert candidates[0]["reference"] == "none"
    assert diagnostics["speech_seconds"] == 0.5 and diagnostics["model_called"]


def test_cohere_worker_posts_one_unprompted_candidate_and_vad_diagnostics(monkeypatch, tmp_path):
    engine = FakeCohere([{"start":0,"end":16000}])
    monkeypatch.setattr(worker, "CohereEngine", lambda model: engine)
    posted = []
    def request(url, **kwargs):
        if url.endswith("/job"):
            if posted:
                raise KeyboardInterrupt
            return {"session_id":"s", "job_id":"j", "sequence":1, "kind":"quick",
                    "supports_unscored_candidates":True,
                    "audio_base64":base64.b64encode(audio()).decode(),
                    "references":[{"reference":"next","text":"do not use a prompt"}]}
        assert url.endswith("/result")
        posted.append(kwargs["data"])
        return {"status":"accepted", "debug":{"selected_reference":"none"}}
    monkeypatch.setattr(worker, "request", request)
    log = worker.DebugLog(tmp_path / "cohere.jsonl")
    try:
        with pytest.raises(KeyboardInterrupt):
            worker.run("https://api.test", "unused", worker.COHERE_MODEL, "secret", log, backend="cohere")
    finally:
        log.close()
    assert len(engine.calls) == 1 and len(posted[0]["candidates"]) == 1
    entry = json.loads(log.path.read_text())
    assert entry["vad_model"] == "silero-onnx-cpu" and entry["speech_fraction"] == 1
    assert entry["stt_text"] and "secret" not in log.path.read_text()


def test_transcription_debug_captures_volume_and_text_but_silence_skips_model(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "request", lambda *a, **kw: calls.append(kw) or {"text":"<asr_text>الحمد لله"})
    details = {}
    assert worker.transcription(audio(), "http://127.0.0.1:8001/v1", "test", details) == "الحمد لله"
    assert details["raw_stt_text"] == "<asr_text>الحمد لله"
    assert details["audio_seconds"] == 1 and details["rms"] > 0.004
    assert details["model_called"] and not details["silence_skipped"]
    silence = {}
    assert worker.transcription(audio(0), "http://127.0.0.1:8001/v1", "test", silence) == ""
    assert silence["silence_skipped"] and not silence["model_called"]
    assert len(calls) == 1


def test_debug_log_is_private_bounded_and_never_overwrites(tmp_path):
    path = tmp_path / "test.jsonl"
    log = worker.DebugLog(path, max_bytes=250)
    log.write(event="test", stt_text="الحمد لله")
    log.write(event="too_large", stt_text="أ" * 500)
    log.close()
    assert log.disabled
    entries = path.read_text().splitlines()
    assert len(entries) == 1 and json.loads(entries[0])["stt_text"] == "الحمد لله"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        worker.DebugLog(path)


@pytest.mark.parametrize("debug", [False, True])
def test_worker_opt_in_log_and_matching_details_without_token_or_audio(
    tmp_path, monkeypatch, capsys, debug
):
    token = "private-worker-token"
    calls = []
    model_checks = 0
    def request(url, **kwargs):
        nonlocal model_checks
        if url.endswith("/models"):
            model_checks += 1
            if model_checks > 1:
                raise KeyboardInterrupt
            return {"data":[]}
        if url.endswith("/job"):
            return {"session_id":"session", "job_id":"job", "sequence":7,
                    "audio_base64":base64.b64encode(audio()).decode()}
        if url.endswith("/audio/transcriptions"):
            return {"text":"إن الصدق يهدي القلب"}
        if url.endswith("/result"):
            calls.append(kwargs["data"])
            return {"status":"accepted", "debug":{"reason":"low_overlap", "state":"waiting"}}
        raise AssertionError(url)
    monkeypatch.setattr(worker, "request", request)
    path = tmp_path / "debug.jsonl"
    log = worker.DebugLog(path) if debug else None
    try:
        with pytest.raises(KeyboardInterrupt):
            worker.run("https://api.test", "http://127.0.0.1:8001/v1", "test", token, log)
    finally:
        if log:
            log.close()
    assert bool(calls[0].get("debug")) is debug
    stdout = capsys.readouterr().out
    assert token not in stdout and "إن الصدق" not in stdout
    if not debug:
        assert not path.exists()
    else:
        content = path.read_text()
        entry = json.loads(content)
        assert entry["sequence"] == 7 and entry["stt_text"] == "إن الصدق يهدي القلب"
        assert entry["matcher"]["reason"] == "low_overlap"
        assert "audio_base64" not in content and token not in content


@pytest.mark.parametrize("failure", ["stt_http_error", "expired_result"])
def test_debug_records_failures_without_exception_details(tmp_path, monkeypatch, failure):
    model_checks = 0
    def request(url, **kwargs):
        nonlocal model_checks
        if url.endswith("/models"):
            model_checks += 1
            if model_checks > 1:
                raise KeyboardInterrupt
            return {}
        if url.endswith("/job"):
            return {"session_id":"s", "job_id":"j", "sequence":9,
                    "audio_base64":base64.b64encode(audio()).decode()}
        if url.endswith("/audio/transcriptions"):
            if failure == "stt_http_error":
                raise urllib.error.HTTPError(url, 500, "private exception detail", {}, None)
            return {"text":"الحمد لله"}
        if url.endswith("/offline"):
            return None
        if url.endswith("/result"):
            if failure == "expired_result":
                raise urllib.error.HTTPError(url, 409, "private exception detail", {}, None)
            return {"status":"accepted", "debug":{"reason":"empty_or_non_arabic_text"}}
        raise AssertionError(url)
    monkeypatch.setattr(worker, "request", request)
    log = worker.DebugLog(tmp_path / "failure.jsonl")
    try:
        with pytest.raises(KeyboardInterrupt):
            worker.run("https://api.test", "http://127.0.0.1:8001/v1", "test", "secret-token", log)
    finally:
        log.close()
    content = log.path.read_text()
    assert "private exception detail" not in content and "secret-token" not in content
    entries = [json.loads(line) for line in content.splitlines()]
    if failure == "stt_http_error":
        assert entries[0]["event"] == "stt_error" and entries[0]["http_status"] == 500
    else:
        assert entries[0]["result_http_status"] == 409
