# Cohere Arabic + Silero on Windows / WSL2

Model: https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026

First open that page in your own Hugging Face account and accept the model's
access conditions. Create a read token with permission to access this model.
Keep that token private. It is different from the app's speech-worker token.

Stop the old Whisper worker (Ctrl+C), and stop any vLLM process occupying the GPU.
Extract this package to C:\Users\engab\Documents\khutba-cohere-worker.
Open Ubuntu / WSL, then run:

```bash
cd /mnt/c/Users/engab/Documents/khutba-cohere-worker
python3 -m venv ~/khutba-cohere
source ~/khutba-cohere/bin/activate
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements-cohere.txt
hf auth login
nvidia-smi
bash start-cohere.sh
```

At `hf auth login`, supply your Hugging Face read token. At the worker's hidden
prompt, supply the **speech-worker token** from the app owner dashboard.
The first run downloads the model. It announces readiness only after model
loading. Then start a new microphone session in the mosque page.

This uses Transformers directly on CUDA in FP16, batch size one, greedy decoding,
and short clips. The 2B model's weights alone are roughly 4 GB; total VRAM is
higher. Actual fit and speed on the RTX 3070 8 GB still need a local test.
If CUDA is unavailable, check the Windows NVIDIA driver and WSL GPU support.
If loading fails with access denied, check model approval and `hf auth whoami`.
If it runs out of GPU memory, stop other GPU applications first. This setup does
not silently offload to CPU or switch to another model.

## Audio processing

Silero VAD runs on CPU before Cohere. Chunks with less than 450 ms of detected
speech, or less than 15% speech, are skipped. Leading/trailing noise is trimmed
with 150 ms padding; internal pauses stay intact. Very quiet speech is still
checked by VAD. A detected speech region is not proof that the imam is speaking:
nearby conversations and TV voices can pass VAD. The script matcher still checks
whether the text belongs to the khutba.

Cohere makes one Arabic transcription per accepted clip. Sentence prompts are
not supplied because the documented model interface does not offer Whisper's
initial-prompt mechanism. The API uses the text for both full and quick matching.
Unavailable Whisper confidence scores are sent as null, never invented.

Logging is enabled by default. The file in ~/khutba-live-debug includes VAD decisions, speech
duration/fraction, transcription timing, and API matching/coverage diagnostics.
It contains private recognized speech, but no recordings or tokens. VAD reduces
silence hallucinations; it cannot guarantee their elimination.

The previous Whisper environment is preserved. To return to it, use
`bash start-whisper.sh --debug-log` from a package containing that launcher.

Sources: the model card above, https://github.com/snakers4/silero-vad and
https://huggingface.co/docs/transformers/model_doc/cohere_asr.

## Default semantic shadow experiment

Semantic shadow and logging are enabled by default. New installs include the
semantic dependency through requirements-cohere.txt. To update an existing
worker environment, run:

```bash
python -m pip install -r requirements-semantic.txt
python worker.py
```

This uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` on CPU.
Its first run downloads model weights. It compares full-check transcripts with
cached Arabic passage embeddings locally. Sermon text is not sent to an external
inference API. Suggestions NEVER affect highlights or transcription prompts.
Quick checks do not invoke the embedding model.

Authoritative transcription results are posted first. Semantic work runs in one
background thread with no backlog; busy checks are skipped. CPU competition can
still affect performance, so compare timings with shadow mode off. The log's
`semantic_shadow` events identify the session/sequence, top three passage
indices, cosine similarities, margin and elapsed time. Similarity is not a
probability. The model truncates inputs to its token limit; logs report that
limit and whether the corpus exceeded the experiment's 512-passage cap.

Use `python worker.py --no-semantic-shadow` to keep logging without semantic
analysis. Use `python worker.py --no-debug-log` to disable both. A custom log
path is still supported through `--debug-log /path/to/new-file.jsonl`.
Existing debug logs contain private speech, so share them only for intentional
troubleshooting.
