# Voice Interruption Fix - Option A: Bot Speaking State Reset (Diagnostic Version)

## Date
November 21, 2025

## Status
🔬 **DIAGNOSTIC VERSION** - Added extensive logging to identify bot speaking state flags

## Problem

After the first interruption, the bot goes completely silent and never speaks again, even though:
- ✅ Interruption detection works
- ✅ WebRTC audio buffer clearing works
- ✅ LLM generates responses
- ✅ STT works
- ✅ Robot commands execute
- ❌ TTS (Text-to-Speech) never generates audio after first interruption

**Key observation from logs**: After first interruption at 12:00:39, CartesiaTTSService stops generating TTS completely. No "Bot started speaking" logs appear.

## Root Cause Hypothesis

The bot speaking state isn't being reset after interruption. This state likely prevents TTS from generating new audio because the system thinks the bot is still speaking.

## Previous Fix Attempts

### Attempt 1: Call `_bot_stopped_speaking()` method
```python
if hasattr(output_transport, '_bot_stopped_speaking'):
    await output_transport._bot_stopped_speaking()
    logger.info("✅ Reset bot speaking state")
```

**Result**: Log "✅ Reset bot speaking state" never appeared → method doesn't exist

## Current Diagnostic Implementation

**Location:** `dog-agent-web-ui.py:882-926`

Added extensive diagnostic logging to identify:
1. What the actual transport objects are
2. What state flags exist (e.g., `_is_bot_speaking`, `_is_speaking`, `_should_listen`)
3. Values of these flags before and after reset

```python
async def patched_handle_user_interruption(self, *args, **kwargs):
    """Patched handler to clear audio queues when user interruption is detected."""
    logger.info("🔥 INTERRUPT DETECTED - Clearing all audio queues!")

    # Call original handler first - THIS is what sends CancelFrame and manages bot speaking state
    result = await original_handle_interruption(*args, **kwargs)

    # Clear the WebRTC audio track queue AND reset bot speaking state
    try:
        output_transport = transport.output()
        input_transport = transport.input()

        # Clear WebRTC audio buffer
        if hasattr(output_transport, '_client') and hasattr(output_transport._client, '_audio_output_track'):
            audio_track = output_transport._client._audio_output_track
            if hasattr(audio_track, '_chunk_queue'):
                logger.info(f"🧹 Clearing {len(audio_track._chunk_queue)} audio chunks from WebRTC track")
                audio_track._chunk_queue.clear()
                logger.info("✅ Audio queue cleared successfully!")

        # DEBUG: Check what attributes control bot speaking state
        logger.info(f"🔍 Input transport type: {type(input_transport)}")
        logger.info(f"🔍 Input _is_bot_speaking: {getattr(input_transport, '_is_bot_speaking', 'NOT FOUND')}")
        logger.info(f"🔍 Input _should_listen: {getattr(input_transport, '_should_listen', 'NOT FOUND')}")
        logger.info(f"🔍 Output transport type: {type(output_transport)}")
        logger.info(f"🔍 Output _is_speaking: {getattr(output_transport, '_is_speaking', 'NOT FOUND')}")

        # Reset bot speaking state on INPUT transport (where interruption is detected)
        if hasattr(input_transport, '_is_bot_speaking'):
            logger.info(f"🔍 BEFORE reset: _is_bot_speaking = {input_transport._is_bot_speaking}")
            input_transport._is_bot_speaking = False
            logger.info("✅ Reset input transport _is_bot_speaking = False")

        # Also reset on output transport if it exists
        if hasattr(output_transport, '_is_speaking'):
            logger.info(f"🔍 BEFORE reset: output _is_speaking = {output_transport._is_speaking}")
            output_transport._is_speaking = False
            logger.info("✅ Reset output transport _is_speaking = False")

    except Exception as e:
        logger.error(f"❌ Error in interrupt handler: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

    return result
```

## Testing Instructions

### 1. Start the Server
```bash
python3 dog-agent-web-ui.py
```

### 2. Open Voice Interface
Navigate to: http://localhost:7860

### 3. Test Interruption
1. Start a conversation with the bot
2. Ask: "Tell me a long story about robot dogs"
3. **While the bot is speaking**, start talking yourself
4. Bot should stop immediately

### 4. Critical: Check Diagnostic Logs

After the first interruption, you should see diagnostic logs like:

```
🔥 INTERRUPT DETECTED - Clearing all audio queues!
🧹 Clearing N audio chunks from WebRTC track
✅ Audio queue cleared successfully!
🔍 Input transport type: <class 'pipecat.transports.network.small_webrtc.SmallWebRTCInputTransport'>
🔍 Input _is_bot_speaking: True  <-- THIS IS THE KEY!
🔍 Input _should_listen: True
🔍 Output transport type: <class 'pipecat.transports.network.small_webrtc.SmallWebRTCOutputTransport'>
🔍 Output _is_speaking: False
🔍 BEFORE reset: _is_bot_speaking = True
✅ Reset input transport _is_bot_speaking = False
```

### 5. Test Second Response

After the first interruption, try speaking again:
- Say: "Hello, can you hear me?"
- **Expected (if fixed)**: Bot responds with TTS
- **Previous behavior**: Bot stays silent (LLM responds, but no TTS)

### 6. Monitor for TTS Generation

**Success indicators:**
```
2025-11-21 HH:MM:SS | DEBUG | CartesiaTTSService#0: Generating TTS [...]
2025-11-21 HH:MM:SS | DEBUG | Bot started speaking
```

**Failure indicators (previous behavior):**
- LLM generates response
- Robot functions execute
- But NO "Generating TTS" logs
- No "Bot started speaking" logs

## What This Diagnostic Version Does

1. **Identifies the transport types**: Shows the exact class names
2. **Checks multiple state flags**: Looks for `_is_bot_speaking`, `_should_listen`, `_is_speaking`
3. **Logs before/after values**: Shows if our reset is working
4. **Resets both input and output**: Covers both possible locations of the state

## Expected Outcome

The diagnostic logs will reveal:
1. **Which flag is stuck**: Is it `_is_bot_speaking` on input, or `_is_speaking` on output?
2. **Is the flag accessible**: Does it exist? (NOT FOUND vs actual value)
3. **Is our reset working**: Do we see the value change from True → False?
4. **Does TTS resume**: Does CartesiaTTS generate audio after we reset the flag?

## Next Steps Based on Results

### If we see `_is_bot_speaking: True` and it gets reset to `False`:
- ✅ We found the right flag!
- Check if TTS resumes after this
- If TTS still doesn't work, the issue is elsewhere (maybe in aggregator)

### If we see `_is_bot_speaking: NOT FOUND`:
- The flag has a different name
- Look for alternative flags in the diagnostic output
- May need to inspect the Pipecat source code

### If flag resets but TTS still doesn't work:
- Bot speaking state might be in the `OpenAIAssistantContextAggregator` instead
- May need to send explicit `BotStoppedSpeakingFrame` through pipeline
- Could be an issue with TTS service itself

## Files Modified

### `dog-agent-web-ui.py`
- **Lines 882-926**: Enhanced interrupt handler with extensive diagnostic logging
- **Lines 903-907**: Log transport types and state flags
- **Lines 910-919**: Attempt to reset bot speaking state on both transports

## Known Limitations

Same as before:
1. **Context Truncation**: Bot's partial response not added to context
2. **Mid-Word Cutoff**: Bot may stop mid-word
3. **Function Calls**: Physical robot actions won't be interrupted
4. **Audio Lag**: 100-300ms latency due to WebRTC buffering

## Comparison to Previous Attempts

| Previous Attempt | Current Diagnostic Version |
|------------------|---------------------------|
| Assumed `_bot_stopped_speaking()` method exists | Checks what actually exists |
| Only checked output transport | Checks both input and output |
| No visibility into state values | Logs state before and after |
| Silent failure (no logs) | Comprehensive diagnostic logs |

---

**Current Status**: Ready for testing with diagnostic logging. The logs will reveal exactly what state flags control bot speaking and whether our reset is working.

## User Instructions

**Please run this version and share the logs from an interruption**. Look specifically for:
1. The 🔍 diagnostic log lines after "🔥 INTERRUPT DETECTED"
2. Any "NOT FOUND" messages
3. Whether you see "✅ Reset input transport _is_bot_speaking = False"
4. Whether CartesiaTTS generates audio after the interruption

This will tell us exactly what we need to fix!
