import asyncio
import contextlib
import json
import os
import time
from collections import deque
from difflib import SequenceMatcher
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

try:
    # When running as a package: `uvicorn src.main:app`
    from .brain import Brain
    from .skills import SkillRouter
    from .voice import Voice
except Exception:  # pragma: no cover
    # When running as a script: `python src/main.py`
    from brain import Brain
    from skills import SkillRouter
    from voice import Voice

app = FastAPI()
brain = Brain()
voice = Voice()

# This finds the folder where main.py actually lives
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR.parent
html_path = BASE_DIR / "index.html"

skills = SkillRouter(workspace_dir=WORKSPACE_DIR)

with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()


def _normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = " ".join(text.split())
    return "".join(ch for ch in text if ch.isalnum() or ch.isspace())


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

@app.get("/")
async def get():
    return HTMLResponse(content=html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_ai_task: asyncio.Task | None = None
    current_stop_event: asyncio.Event | None = None
    timer_tasks: set[asyncio.Task] = set()

    # Keep a short rolling window of what AMANE recently said so we can ignore
    # Whisper transcripts that are actually just the speakers leaking into the mic.
    recent_assistant: deque[tuple[float, str]] = deque(maxlen=40)

    def remember_assistant(text: str) -> None:
        norm = _normalize_text(text)
        if norm:
            recent_assistant.append((time.time(), norm))

    def looks_like_assistant_echo(user_text: str) -> bool:
        norm_user = _normalize_text(user_text)
        if len(norm_user) < 8:
            return False

        now = time.time()
        for ts, norm_assistant in list(recent_assistant):
            if now - ts > 25:
                continue

            # Strong substring match handles partial captures.
            if norm_user in norm_assistant or norm_assistant in norm_user:
                if min(len(norm_user), len(norm_assistant)) >= 10:
                    return True

            if _similarity(norm_user, norm_assistant) >= 0.86:
                return True

        return False

    cancel_lock = asyncio.Lock()

    async def cancel_current_response(reason: str) -> None:
        nonlocal current_ai_task, current_stop_event
        async with cancel_lock:
            if current_ai_task and not current_ai_task.done():
                print(f"🛑 Cancelling current response ({reason})")
                if current_stop_event:
                    current_stop_event.set()
                current_ai_task.cancel()
                try:
                    await current_ai_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"⚠️ Cancel wait error: {e}")

                # Ask browser to stop audio immediately.
                try:
                    await websocket.send_json({"type": "interrupt"})
                except Exception:
                    pass

    async def send_sentence_with_audio(
        sentence: str,
        stop_event: asyncio.Event | None = None,
        *,
        send_text: bool = True,
    ) -> None:
        if stop_event and stop_event.is_set():
            return
        remember_assistant(sentence)
        if send_text:
            await websocket.send_json({"type": "sentence", "text": sentence})

        audio_gen = voice.generate_audio_bytes(sentence)
        while True:
            if stop_event and stop_event.is_set():
                break
            try:
                audio_chunk = await asyncio.to_thread(next, audio_gen)
            except StopIteration:
                break
            await websocket.send_bytes(audio_chunk)

    async def schedule_timer(seconds: int, label: str) -> None:
        try:
            await asyncio.sleep(seconds)
            # Timer is important: interrupt whatever is speaking.
            await cancel_current_response("timer_done")
            await send_sentence_with_audio(f"Timer finished: {label}.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"⚠️ Timer error: {e}")
    
    try:
        while True:
            message = await websocket.receive()
            text_data = message.get("text")
            bytes_data = message.get("bytes")

            if text_data is not None:
                try:
                    payload = json.loads(text_data)
                except json.JSONDecodeError:
                    continue

                if payload.get("type") == "interrupt":
                    await cancel_current_response("client_barge_in")
                continue

            if bytes_data is None:
                continue

            user_text = await voice.transcribe(bytes_data)
            if not user_text:
                continue

            if looks_like_assistant_echo(user_text):
                print(f"🔇 Ignoring likely assistant echo: {user_text!r}")
                continue

            # If she is currently thinking or speaking, kill it.
            if current_ai_task and not current_ai_task.done():
                await cancel_current_response("new_user_audio")

            async def run_ai(text: str, stop_event: asyncio.Event):
                sentence_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=8)
                tts_task: asyncio.Task | None = None

                async def tts_worker(*, send_text: bool) -> None:
                    try:
                        while True:
                            sentence = await sentence_queue.get()
                            if sentence is None:
                                break
                            if stop_event.is_set():
                                break
                            await send_sentence_with_audio(sentence, stop_event, send_text=send_text)
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"⚠️ TTS worker error: {e}")

                try:
                    print(f"✅ User: {text}")
                    await websocket.send_json({"type": "transcription", "text": text})

                    skill_result = await skills.try_handle(text)
                    if skill_result is not None:
                        tts_task = asyncio.create_task(tts_worker(send_text=True))
                        # Handle actions first (e.g., timers, headlines for UI).
                        for action in skill_result.actions:
                            action_type = action.get("type")
                            if action_type == "timer_set":
                                secs = int(action.get("seconds", 0))
                                label = str(action.get("label") or f"{secs} seconds")
                                t = asyncio.create_task(schedule_timer(secs, label))
                                timer_tasks.add(t)
                                t.add_done_callback(lambda task: timer_tasks.discard(task))
                                continue

                            if action_type == "timer_cancel_all":
                                for t in list(timer_tasks):
                                    t.cancel()
                                timer_tasks.clear()
                                continue

                            # Generic UI action
                            await websocket.send_json(action)

                        for sentence in skill_result.sentences:
                            if stop_event.is_set():
                                break

                            # Enqueue quickly so we can overlap TTS with other work.
                            await sentence_queue.put(sentence)

                        # Stop the worker.
                        await sentence_queue.put(None)
                        if tts_task:
                            await tts_task

                        if not stop_event.is_set():
                            await websocket.send_json({"type": "done"})
                        return

                    # LLM response: stream text deltas for UI, while speaking chunked audio.
                    await websocket.send_json({"type": "assistant_start"})
                    tts_task = asyncio.create_task(tts_worker(send_text=False))

                    async for kind, piece in brain.think_stream_events(text):
                        if stop_event.is_set():
                            break

                        if kind == "delta":
                            if piece:
                                await websocket.send_json({"type": "assistant_delta", "text": piece})
                            continue

                        if kind == "segment":
                            sentence = (piece or "").strip()
                            if not sentence:
                                continue
                            await sentence_queue.put(sentence)

                    await sentence_queue.put(None)
                    if tts_task:
                        await tts_task

                    if not stop_event.is_set():
                        await websocket.send_json({"type": "assistant_end"})

                    if not stop_event.is_set():
                        await websocket.send_json({"type": "done"})
                except asyncio.CancelledError:
                    print("🧠 AI Task Cancelled.")
                except Exception as e:
                    print(f"⚠️ AI error: {e}")
                    if not stop_event.is_set():
                        await send_sentence_with_audio(
                            "Sorry, I had a problem thinking. I can still do commands like time, weather, notes, and reading PDFs.",
                            stop_event,
                        )
                        await websocket.send_json({"type": "done"})
                finally:
                    if tts_task and not tts_task.done():
                        tts_task.cancel()
                        with contextlib.suppress(Exception):
                            await tts_task

            current_stop_event = asyncio.Event()
            current_ai_task = asyncio.create_task(run_ai(user_text, current_stop_event))

    except WebSocketDisconnect:
        if current_ai_task:
            if current_stop_event:
                current_stop_event.set()
            current_ai_task.cancel()

        for t in list(timer_tasks):
            t.cancel()
        print("👋 Browser disconnected.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)