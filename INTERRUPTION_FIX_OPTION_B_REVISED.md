# Voice Interruption Fix - Option B Revised: Monkey-Patching Approach

## Date
November 21, 2025

## Status
✅ **REVISED & READY FOR TESTING** - Fixed implementation method

## Background

### First Attempt (Commit 7c601fa)
Initial implementation used class inheritance to override `_handle_user_interruption()`:
- Created `InterruptAwareInput` class extending `original_input.__class__`
- **FAILED**: Method wasn't actually being called - no interrupt logs appeared

### Issue Identified
From test logs, we saw:
```
2025-11-21 11:14:56.206 | DEBUG | pipecat.transports.base_input:_handle_user_interruption:242 - User started speaking
```

But **NEVER** saw our custom logs:
- ❌ `🔥 INTERRUPT DETECTED - Clearing all audio queues!`
- ❌ `🧹 Clearing N audio chunks from WebRTC track`

**Root cause**: Class inheritance approach wasn't properly overriding the instance method.

### Solution (Commit 903a307)
Switched to **direct monkey-patching** using `types.MethodType`:
- Save reference to original `_handle_user_interruption` method
- Create patched version that calls original + clears buffers
- Bind patched function to instance using `types.MethodType`

## Implementation Details

### Monkey-Patch Approach
**Location:** `dog-agent-web-ui.py:875-906`

```python
# ADD INTERRUPT HANDLING AT TRANSPORT LEVEL
# Monkey-patch the transport's input to detect interruptions and clear audio queues
original_input = transport.input()

# Save the original handler
original_handle_interruption = original_input._handle_user_interruption

async def patched_handle_user_interruption(self, *args, **kwargs):
    """Patched handler to clear audio queues when user interruption is detected."""
    logger.info("🔥 INTERRUPT DETECTED - Clearing all audio queues!")

    # Call original handler first
    result = await original_handle_interruption(*args, **kwargs)

    # Clear the WebRTC audio track queue
    try:
        output_transport = transport.output()
        if hasattr(output_transport, '_client') and hasattr(output_transport._client, '_audio_output_track'):
            audio_track = output_transport._client._audio_output_track
            if hasattr(audio_track, '_chunk_queue'):
                logger.info(f"🧹 Clearing {len(audio_track._chunk_queue)} audio chunks from WebRTC track")
                audio_track._chunk_queue.clear()
                logger.info("✅ Audio queue cleared successfully!")
    except Exception as e:
        logger.error(f"❌ Error clearing audio queue: {e}")

    return result

# Monkey-patch the method
import types
original_input._handle_user_interruption = types.MethodType(patched_handle_user_interruption, original_input)
logger.info("✅ Configured interrupt handler to clear WebRTC audio buffers on interruption")
```

### Why This Works

1. **types.MethodType** properly binds the function to the instance
2. **Direct assignment** replaces the method on the specific instance (not the class)
3. **Closure** captures `original_handle_interruption` so we can call it
4. **Instance binding** ensures `self` is correctly passed

### InterruptibleAudioOutput (Still Included)
**Location:** `dog-agent-web-ui.py:773-813`

The `InterruptibleAudioOutput` FrameProcessor is still in the pipeline to handle `CancelFrame` events:

```python
class InterruptibleAudioOutput(FrameProcessor):
    """Audio output processor that properly handles interrupts by clearing queued audio."""

    def __init__(self):
        super().__init__()
        self._audio_queue = []
        self._is_playing = False
        self._current_audio_task = None
        self._running = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and handle interrupts properly."""
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._running = True
            logger.info("InterruptibleAudioOutput: Started")
            await self.push_frame(frame, direction)

        elif isinstance(frame, (EndFrame, CancelFrame)):
            logger.info(f"InterruptibleAudioOutput: Received {type(frame).__name__} - clearing audio queue")
            self._running = False
            await self._clear_audio_queue()
            await self.push_frame(frame, direction)

        elif isinstance(frame, OutputAudioRawFrame) and self._running:
            logger.debug("InterruptibleAudioOutput: Processing audio frame")
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _clear_audio_queue(self):
        """Clear any pending audio processing."""
        logger.info("InterruptibleAudioOutput: Clearing audio queue and stopping playback")
        self._audio_queue.clear()
        self._is_playing = False
```

## Testing Instructions

### 1. Start the Server
```bash
python3 dog-agent-web-ui.py
```

### 2. Watch for Startup Logs
You should see:
```
✅ Created InterruptibleAudioOutput handler for better interruption support
✅ Configured interrupt handler to clear WebRTC audio buffers on interruption
```

### 3. Open Voice Interface
Navigate to: http://localhost:7860

### 4. Test Interruption
1. Start a conversation with the bot
2. Ask: "Tell me a long story about robot dogs"
3. **While the bot is speaking**, start talking yourself
4. Bot should **immediately stop** and listen to you

### 5. Monitor Logs - THIS IS THE KEY TEST

#### SUCCESS ✅ - You should now see:
```
2025-11-21 HH:MM:SS | DEBUG | pipecat.transports.base_input:_handle_user_interruption:242 - User started speaking
INFO:__main__:🔥 INTERRUPT DETECTED - Clearing all audio queues!
INFO:__main__:🧹 Clearing N audio chunks from WebRTC track
INFO:__main__:✅ Audio queue cleared successfully!
INFO:__main__:InterruptibleAudioOutput: Received CancelFrame - clearing audio queue
```

#### FAILURE ❌ - If you only see:
```
2025-11-21 HH:MM:SS | DEBUG | pipecat.transports.base_input:_handle_user_interruption:242 - User started speaking
```

Without the "🔥 INTERRUPT DETECTED" message, then the monkey-patch didn't work either.

## What Changed From Previous Version

| First Attempt (7c601fa) | Revised (903a307) |
|-------------------------|-------------------|
| Created `InterruptAwareInput` subclass | Direct monkey-patching |
| Used `super().__init__()` and `__dict__.update()` | Used `types.MethodType` |
| **Method never called** | **Should be called** |
| Class-level override attempt | Instance-level replacement |

## Troubleshooting

### If Monkey-Patch Still Doesn't Work

If you STILL don't see the "🔥 INTERRUPT DETECTED" logs, it means Pipecat's internal implementation has changed. Try this diagnostic:

```python
# Add after line 880 (after saving original_handle_interruption)
logger.info(f"Original handler type: {type(original_handle_interruption)}")
logger.info(f"Original handler: {original_handle_interruption}")
logger.info(f"Input transport type: {type(original_input)}")
```

### Alternative: Hook at Different Level

If monkey-patching doesn't work, we may need to hook at a different level:

**Option C: Override at VAD Level**
```python
# Hook into VAD analyzer's user_started_speaking event
original_vad = transport.input()._vad_analyzer

original_user_started = original_vad._user_started_speaking

async def patched_user_started(self):
    logger.info("🔥 VAD DETECTED USER SPEAKING - Triggering interrupt!")
    await original_user_started()
    # Clear buffers here
    ...

import types
original_vad._user_started_speaking = types.MethodType(patched_user_started, original_vad)
```

### Expected Behavior After Fix

**Before Interrupt:**
- Bot is speaking: "Woof woof! I'm a playful robot dog..."
- Audio continues streaming to browser

**User Interrupts (starts speaking):**
1. VAD detects speech: `User started speaking`
2. **NEW**: Monkey-patched handler runs: `🔥 INTERRUPT DETECTED`
3. **NEW**: WebRTC buffer cleared: `🧹 Clearing N audio chunks`
4. CancelFrame sent through pipeline
5. InterruptibleAudioOutput receives CancelFrame: `Received CancelFrame - clearing audio queue`
6. Bot stops immediately (within ~100-300ms)
7. User's speech is processed

## Files Modified

### `dog-agent-web-ui.py`
- **Lines 875-906**: Replaced class-based approach with monkey-patching
- **Line 880**: Save original handler reference
- **Lines 882-901**: Define patched handler function
- **Lines 904-906**: Apply monkey-patch using types.MethodType

## Known Limitations

Same as before:
1. **Context Truncation**: Bot's partial response not added to context
2. **Mid-Word Cutoff**: Bot may stop mid-word
3. **Function Calls**: Physical robot actions won't be interrupted
4. **Audio Lag**: 100-300ms latency due to WebRTC buffering

## Next Steps

### If This Works ✅
- Measure and document interruption latency
- Tune VAD parameters if needed
- Get user feedback on conversation quality

### If This Still Doesn't Work ❌
We need to investigate why `_handle_user_interruption` isn't being called at all:

1. **Check Pipecat Version**:
   ```bash
   pip show pipecat-ai
   ```

2. **Check Method Name**:
   ```python
   # List all methods on the input transport
   print(dir(original_input))
   ```

3. **Try VAD-Level Hook** (Option C above)

4. **File Pipecat Issue**: If the interruption system isn't working at all in your Pipecat version

## Comparison to dog-agent-movementsbuttons-interrupt-fix.py

The working reference implementation uses a **class-based approach**, but it does so differently:

```python
class InterruptAwareInput(original_input.__class__):
    def __init__(self, original_input_instance):
        super().__init__(original_input_instance._client, original_input_instance._params, ...)
        self.__dict__.update(original_input_instance.__dict__)
```

**Our revised approach is simpler** - we just monkey-patch the specific method instead of replacing the entire instance. This should be more reliable and easier to debug.

---

**Current Status**: Ready for testing with monkey-patch approach. If this still doesn't show the interrupt logs, we'll need to investigate Pipecat's internals more deeply.
