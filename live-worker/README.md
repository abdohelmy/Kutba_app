# Live imam tracking — Windows + NVIDIA RTX GPU

This worker defaults to **Cohere Transcribe Arabic 07-2026**, with CPU Silero VAD
and FP16 inference on one NVIDIA GPU. Start with **[COHERE-SETUP.md](COHERE-SETUP.md)**.
Run `python worker.py` in the configured environment. Local debug logging and
CPU semantic shadow analysis are also enabled by default. Use
`--no-semantic-shadow` to disable semantic analysis, or `--no-debug-log` to
disable both. Existing installations should first install
`python -m pip install -r requirements-semantic.txt` in the worker environment.
The API must have the Cohere compatibility update before starting this worker.
The instructions below retain the optional Whisper setup as a fallback. Arabic speech
recognition runs on your PC; the VM only buffers audio and matches words to the
prepared Arabic khutba. The PC makes outbound HTTPS requests, so no desktop
port forwarding, domain, or Cloudflare tunnel is needed.

The microphone capture screen is currently in the **web app** (usable on a phone).
Reader highlighting is implemented in web, Android, and iOS; native installations
need a new build. Keep the recording browser foreground and the phone unlocked.

## 1. Install WSL2

Use Windows 11 or Windows 10 21H2 or later and a current NVIDIA Windows driver.
In **administrator PowerShell**:

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
```

Restart Windows if prompted, then open Ubuntu and create its Linux account.
Run `nvidia-smi` inside Ubuntu. It must show your RTX 3060/3070 before proceeding.
Do not install a Linux NVIDIA display driver inside WSL.

## 2. Install Whisper in Ubuntu

End the website's live session. If upgrading from Qwen, press **Ctrl+C** in both
the old worker and vLLM terminals to release GPU memory. Keep that environment
installed; Whisper uses its own environment. Download and extract the latest ZIP,
then change to the extracted folder containing `worker.py` and these files.

```bash
python3 -m venv ~/khutba-whisper
~/khutba-whisper/bin/python -m pip install --upgrade pip
~/khutba-whisper/bin/python -m pip install -r requirements-whisper.txt
```

If Ubuntu reports that venv is missing, install it with
`sudo apt install python3-venv`, then repeat the first command.
Downloads need several GB of disk space. The launcher locates the CUDA 12/cuDNN 9
libraries installed in this environment; no separate vLLM server is needed.

If an existing installation fails with `TypeError: open() got an unexpected
keyword argument 'metadata_errors'`, its PyAV audio decoder is incompatible with
faster-whisper 1.2.1. Repair that environment, then restart the worker:

```bash
~/khutba-whisper/bin/python -m pip install --force-reinstall --no-deps 'av==16.0.1'
bash start-whisper.sh --debug-log
```

The requirements file pins this compatible PyAV version for new installations.

## 3. Start the worker

From the extracted folder, run:

```bash
bash start-whisper.sh --debug-log
```

Paste your existing worker token privately at the hidden prompt. If it expired,
the owner dashboard's **Windows speech worker → Issue worker token** supplies a
new one. Issuing another token revokes the old one. No token is saved by the worker.

The first launch downloads Whisper large-v3 and loads it into GPU memory. Wait
for **Speech worker connected** before starting the website microphone. Keep
this one terminal and the PC running. The API must also be running; its Friday
schedule is unchanged. Close games and other GPU-heavy applications while testing.

These are starting settings for an 8 GB GPU. Actual peak VRAM and two-pass speed
have not yet been measured on your Lenovo. If startup fails, share the first error
and `nvidia-smi` output, never the token. Use `--no-debug-log` to disable logging.

## 4. How the two sentence references work

The authenticated worker receives the current Arabic sentence and the next one.
At the beginning it uses the opening two sentences. Later hints follow the last
matched position, or a candidate position awaiting confirmation. Long sentences
are bounded to nearby context; the model hint is capped at 180 tokens.

Each full audio chunk is transcribed **twice in sequence**, reusing the same loaded
model: first with the current sentence as an `initial_prompt`, then with the next.
Reference text is encoded without special start/end/task tokens, matching
faster-whisper's own text tokenizer. Including those control tokens can make
the decoder repeat the hint as if it were part of the transcription.
Both calls use Arabic transcription, speech detection, beam size 5, and temperature
0. Hints are context, never forced output. At the final sentence, the second pass
has no hint. An older API with no references gets one unprompted pass.

During initial acquisition or uncertain tracking, a third, unprompted decode is
included so opening-sentence hints do not steer speech recognition away from a
mid-khutba start. All hypotheses go back in one result. The API evaluates them against identical
previous matching state and picks the better eligible match across the whole
khutba. It applies only one update per audio chunk: two decodes are not two fresh
confirmations. Weak audio scores, repetitive output, or conflicting plausible
positions hold the previous highlight. Sentence similarity is not proof that
Whisper heard the words; prompts can still bias recognition, so test off-script
speech as well as reading the text.

The browser sends a check every two seconds: short checks use the latest four
seconds of audio, and every eight seconds a full check covers all eight seconds.
The opening sentence is highlighted provisionally as soon as a reader follows a
new live session. It is only a display default: the first full check can locate
the imam anywhere in the khutba. Readers joining an already located session see
its confirmed position immediately. Short checks use one unprompted decode with beam size 3;
they can only enter the immediately next sentence, advance at most 24 Arabic
words, and need at least five matching words at 85% overlap, including three
distinct meaningful words in that next sentence. They cannot establish a new
position or confirm a long jump. Failed short checks leave the highlight alone.
Passage boundaries reuse the saved Arabic-to-translation sentence mappings, so
comma-joined Arabic can still move between separate English reader sentences.
Debug startup records the selected computation precision; short-check diagnostics
distinguish uncertain speech, a passage outside the allowed distance, and no local match.

The same GPU processes checks sequentially. Old waiting short checks are dropped
when a full check arrives; short checks never build up behind waiting full checks.
A warning appears if processing takes over four seconds. Extra short checks are
best effort: full checks take priority when the GPU falls behind. Debug entries include
`kind` (`quick` or `full`) to distinguish the two paths. Legacy workers may ignore
short checks until updated; full checks remain compatible.

### Optional Qwen fallback

Stop Whisper before restarting your existing vLLM server. From the worker folder:

```bash
python3 worker.py --backend vllm --model Qwen/Qwen3-ASR-1.7B --debug-log
```

The legacy vLLM path retains its single unprompted transcription. Server and worker
model names must match. The Whisper sentence-reference comparison uses the new worker.

## 5. Start a khutba

As the mosque admin, open a **published** khutba in the web workspace:

1. Live highlighting prepares automatically after publishing English or Danish,
   reusing unchanged editing mappings. Older khutbas prepare when an admin opens
   them. There is no separate preparation step and the worker need not be online.
   Any missing mappings use the configured translation provider; with OpenAI,
   this has API usage. Ongoing speech recognition does not use OpenAI.
2. Once ready and the worker is connected, click **Start microphone** and allow
   microphone access. If preparation fails, use **Retry live highlighting**.
3. Place the device close to a clean speaker/audio source, with the mosque's
   permission to process the imam's voice. Avoid crowd chatter and strong echo.
4. Readers open the same khutba and click **Follow imam**.
5. Use **Pause microphone**, **Resume microphone**, or **End live session**.

Six-second audio chunks have a two-second overlap. Live position is approximate,
not word-perfect. A strong, unique first passage can highlight after one chunk
plus transcription time; uncertain initial matches still need confirmation.
The mosque page's microphone input bar shows sound being picked up. If it stays
empty while speaking, check which microphone the browser is using. Sound detected
does not itself mean that the speech model has matched the khutba.
Uncertain/off-script speech holds the last reliable passage.
Large skips require fresh confirming speech. Ordinary reading and notes remain
usable when live tracking is unavailable. Editing the translation invalidates
only the changed passage's mapping/session. Missing mappings are prepared again
automatically on publication, including newly published Danish.

## Privacy, limits, and recovery

- Audio is temporarily held in bounded API memory, not stored in the database.
  Queued audio expires within 25 seconds and is cleared on pause/stop. The ASR
  worker does not save audio, and saves transcripts only if you explicitly enable
  the local debug option below. Do not enable request-body logging in proxies.
  The current/next Arabic reference excerpts are sent only to the authenticated
  local worker and are not written to its debug log.
- The API retains only a short rolling word window in memory while the session
  is active; it does not save a complete transcript.
- No transcript or original Arabic is sent to readers by the live endpoint.
- Four simultaneous mosque sessions maximum for the initial single-GPU setup;
  actual usable capacity depends on measured inference latency.
- A live session ends after three hours, 90 seconds without its recording tab,
  or an API restart. Readers do not keep abandoned recordings alive.
- Slow queues discard old audio rather than replaying obsolete progress.
- If the worker disconnects, recording pauses/stops and ordinary reading continues.
  Restart the worker and resume the microphone.

## Debugging missing highlights

The worker saves a local transcript log by default. To investigate a test, stop
the worker with **Ctrl+C**, then run from the extracted folder:

```bash
python worker.py
```

Paste the token privately at the hidden prompt. The terminal prints the log's
full path under `~/khutba-live-debug/`. Start the microphone in the web app,
read the original Arabic for 30–40 seconds, then stop the worker with Ctrl+C.

The UTF-8 `.jsonl` file contains both candidate transcripts, their audio scores and
processing times, the selected reference label, audio volume/duration, and the
API matcher's acceptance/rejection reason and highlight count. It saves
**no audio, token, authorization headers, or original khutba text**. The API never
stores this debug log or the transcript. Diagnostic reasons such as `low_overlap`
or `empty_or_non_arabic_text` distinguish recognition problems from matching.
Each run creates a new file and logging stops at 2 MB. Files remain on your PC
until you delete them; restarting with `--no-debug-log` turns logging and
semantic shadow analysis off. The Whisper fallback also needs
requirements-semantic.txt unless you pass `--no-semantic-shadow`.
Inspect the file before sharing it: transcripts can contain private speech.

Open the printed path in Windows Explorer by navigating to
`\\wsl.localhost\Ubuntu-24.04\home\YOUR_UBUNTU_USERNAME\khutba-live-debug`.
Attach that test log for debugging, never the worker token. If you used an older
worker, no past transcripts can be recovered; make a fresh test.

## Passage matching diagnostics

The API can recover nearby passages using ordered approximate Arabic word
matches, including spelling differences and immediate stutters. Uncertain
matches need new audio showing additional distinctive words and forward progress.
Quick checks can reach only the next passage; full checks can compare the next
two. Broad initial acquisition and distant jumps retain stricter confirmation.
This does not guarantee recognition of arbitrary dialect substitutions.

With `--debug-log`, the existing worker also saves the API's `result_age_ms`
(from server receipt through result arrival), `queue_wait_ms`, `observed_passage`,
and `confirmed_passages` (zero-based passage indexes), plus `passage_count`.
`nearby_speech_match` indicates accepted approximate matching;
`awaiting_fresh_local_evidence` means more independent speech is needed.
Results arriving more than 8 seconds after receipt for quick checks, or 16
seconds for full checks, are held with `delayed_audio_ignored`. These times do
not include microphone buffering or upload time before the API receives audio.

The session retains only observed passage indexes and their first/last sequence
numbers in memory. A jump does not mark intervening passages as covered. This
record shows where speech was confirmed, not proof that every word was recited.
It lasts through pause/resume, resets with a new session or API restart, and is
included in the optional local debug log. No additional model calls are made.

## Sources

- [faster-whisper setup, quantization, and speech detection](https://github.com/SYSTRAN/faster-whisper)
- [Whisper large-v3 model](https://huggingface.co/openai/whisper-large-v3)
- [Microsoft GPU acceleration in WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gpu-compute)
