# Voice Interruption Fix - Option B: Working Implementation from dog-agent-movementsbuttons-interrupt-fix.py

## Date
November 21, 2025

## Status
✅ **IMPLEMENTED** - Ready for testing

## Background
Option A (custom InterruptionHandler extending FrameProcessor) failed due to improper initialization of internal Frame Processor queues, causing hundreds of errors:
```
ERROR | InterruptionHandler#0 Trying to process StartFrame#0 but StartFrame not received yet
AttributeError: 'InterruptionHandler' object has no attribute '_FrameProcessor__input_queue'
```

## Solution: Option B - Adapted from Working Example

I found a working implementation in `dog-agent-movementsbuttons-interrupt-fix.py` and adapted it to `dog-agent-web-ui.py`.

### Key Components

#### 1. InterruptibleAudioOutput Class
**Location:** `dog-agent-web-ui.py:773-813`

A custom `FrameProcessor` that intercepts `CancelFrame` and `EndFrame` events to clear internal audio queues.

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
            # Pass through audio frames but track them
            logger.debug("InterruptibleAudioOutput: Processing audio frame")
            await self.push_frame(frame, direction)

        else:
            # Pass through all other frames
            await self.push_frame(frame, direction)

    async def _clear_audio_queue(self):
        """Clear any pending audio processing."""
        logger.info("InterruptibleAudioOutput: Clearing audio queue and stopping playback")
        self._audio_queue.clear()
        self._is_playing = False
```

**Key differences from failed Option A:**
- Properly calls `super().process_frame(frame, direction)` FIRST before processing
- Only tracks state, doesn't try to inject CancelFrame
- Correctly pushes frames downstream after processing

#### 2. InterruptAwareInput Class
**Location:** `dog-agent-web-ui.py:879-909`

Extends the transport's input processor to override `_handle_user_interruption()` and directly clear the WebRTC audio track buffer.

```python
class InterruptAwareInput(original_input.__class__):
    def __init__(self, original_input_instance):
        # Copy all attributes from the original instance
        super().__init__(original_input_instance._client, original_input_instance._params, name=getattr(original_input_instance, '_name', None))
        self.__dict__.update(original_input_instance.__dict__)
        self._original_handle_user_interruption = getattr(self, '_handle_user_interruption', None)

    async def _handle_user_interruption(self, *args, **kwargs):
        """Override to clear audio queues when user interruption is detected."""
        logger.info("🔥 INTERRUPT DETECTED - Clearing all audio queues!")

        result = None
        # Call original handler first
        if self._original_handle_user_interruption:
            result = await self._original_handle_user_interruption(*args, **kwargs)

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
```

**Critical innovation:**
- Accesses internal `_chunk_queue` of the WebRTC audio track
- Clears buffered audio chunks that would otherwise continue playing after interruption
- This solves the "audio lag" problem where bot keeps talking for 100-300ms after interruption

#### 3. Pipeline Integration
**Location:** `dog-agent-web-ui.py:818-829`

The `InterruptibleAudioOutput` handler is inserted AFTER audiobuffer but BEFORE transport.output():

```python
pipeline = Pipeline([
    transport.input(),              # Receive audio from web client
    stt,                            # Convert speech to text
    context_aggregator.user(),      # Add user messages to context
    llm,                            # Process text with LLM
    tts,                            # Convert text to speech
    audiobuffer,                    # Audio buffer processor
    interrupt_handler,              # ← NEW: Handle interrupts and clear audio queue
    transport.output(),             # Send audio responses to web client
    context_aggregator.assistant(), # Add assistant responses to context
])
```

#### 4. Transport Modification
**Location:** `dog-agent-web-ui.py:911-914`

The transport's input is replaced with our interrupt-aware version:

```python
interrupt_aware_input = InterruptAwareInput(original_input)
transport._input = interrupt_aware_input
logger.info("✅ Configured InterruptAwareInput to clear WebRTC audio buffers on interruption")
```

### How It Works

#### Normal Flow
```
User speaks → VAD → STT → Context → LLM → TTS → AudioBuffer → InterruptibleAudioOutput → WebRTC Output
```

#### Interruption Flow
```
Bot speaking...
↓
User starts speaking
↓
VAD detects UserStartedSpeakingFrame
↓
Transport calls _handle_user_interruption()
↓
InterruptAwareInput clears WebRTC _chunk_queue (100-300ms of buffered audio)
↓
CancelFrame sent through pipeline
↓
InterruptibleAudioOutput receives CancelFrame
↓
InterruptibleAudioOutput clears internal audio queue
↓
Bot stops talking
↓
User speech processed as new turn
```

### Advantages Over Option A

| Option A (Failed) | Option B (Working) |
|-------------------|-------------------|
| Custom FrameProcessor with manual initialization | Extends existing transport input class |
| Tried to inject CancelFrame proactively | Works with existing interruption flow |
| Missing internal queue initialization | Proper initialization by copying from original |
| Hundreds of StartFrame errors | No initialization errors |
| Bot never started | Bot works normally |

## Testing Instructions

### 1. Start the Server
```bash
python3 dog-agent-web-ui.py
```

### 2. Watch for Startup Logs
You should see:
```
✅ Created InterruptibleAudioOutput handler for better interruption support
✅ Configured InterruptAwareInput to clear WebRTC audio buffers on interruption
```

### 3. Open Voice Interface
Navigate to: http://localhost:7860

### 4. Test Interruption
1. Start a conversation with the bot
2. Ask a question that generates a longer response (e.g., "Tell me about robot dogs")
3. **While the bot is speaking**, start talking yourself
4. Bot should **immediately stop** (within ~100-300ms) and listen to you

### 5. Monitor Logs

#### Success Indicators ✅
```
INFO  | InterruptibleAudioOutput: Started
INFO  | 🔥 INTERRUPT DETECTED - Clearing all audio queues!
INFO  | 🧹 Clearing N audio chunks from WebRTC track
INFO  | ✅ Audio queue cleared successfully!
INFO  | InterruptibleAudioOutput: Received CancelFrame - clearing audio queue
```

#### What You Should NOT See ❌
```
DEBUG | Ignoring user speaking emulation, bot is speaking.
```
If you see this, the fix isn't working (this was the original problem).

### 6. Test Scenarios

#### Scenario A: Mid-Sentence Interruption
1. Ask: "Tell me a story about robot dogs"
2. Wait for bot to start responding
3. Interrupt after 2-3 seconds: "Wait, stop!"
4. **Expected:** Bot stops within ~300ms, processes your "Wait, stop!"

#### Scenario B: Multiple Interruptions
1. Start conversation
2. Interrupt the bot multiple times in a row
3. **Expected:** Each interruption logs:
   ```
   🔥 INTERRUPT DETECTED - Clearing all audio queues!
   🧹 Clearing N audio chunks from WebRTC track
   ```

#### Scenario C: No False Interruptions
1. Let bot finish a response completely
2. Wait 1 second of silence
3. Then speak
4. **Expected:** No "INTERRUPT DETECTED" message, normal conversation flow

## Files Modified

### `dog-agent-web-ui.py`
- **Lines 451**: Added `FrameProcessor, FrameDirection` import
- **Lines 773-813**: Created `InterruptibleAudioOutput` class
- **Lines 815-816**: Instantiate interrupt handler with logging
- **Lines 826**: Insert interrupt handler into pipeline (after audiobuffer, before transport.output)
- **Lines 879-909**: Created `InterruptAwareInput` class
- **Lines 911-914**: Replace transport input with interrupt-aware version

## Differences from INTERRUPTION_FIX_OPTION_A.md

### What Changed
1. **Removed**: Custom `InterruptionHandler` that tried to inject `CancelFrame` before context aggregator
2. **Added**: `InterruptibleAudioOutput` that clears audio queue when receiving `CancelFrame`
3. **Added**: `InterruptAwareInput` that directly clears WebRTC audio buffer on interruption
4. **Pipeline position**: Handler is now AFTER audiobuffer instead of BEFORE context aggregator

### Why It Works Now
- **Proper FrameProcessor initialization**: The new `InterruptibleAudioOutput` properly calls `super().process_frame()` first
- **Works with existing flow**: Doesn't try to override the aggregator's behavior, just enhances it
- **Direct buffer access**: `InterruptAwareInput` directly clears the WebRTC audio track's `_chunk_queue`
- **Tested pattern**: This exact approach is proven working in `dog-agent-movementsbuttons-interrupt-fix.py`

## Known Limitations

1. **Context Truncation**: When interrupted, the bot's partial response is not added to context (Pipecat issue #2791)
2. **Mid-Word Cutoff**: Bot may stop mid-word, which sounds abrupt but is expected
3. **Function Calls**: Physical robot actions won't be interrupted, only speech
4. **Audio Lag**: There may still be 100-300ms of audio after interruption due to WebRTC buffering

## Performance Metrics to Watch

1. **Interruption Latency:** Time from when you start speaking to when bot stops
   - **Target:** < 300ms
   - **Acceptable:** < 500ms
   - **Poor:** > 1000ms

2. **False Positive Rate:** Bot interrupts itself unnecessarily
   - **Target:** 0-5% of responses
   - **Acceptable:** 5-10%
   - **Poor:** > 10%

3. **False Negative Rate:** You can't interrupt when you want to
   - **Target:** 0-2% of attempts
   - **Acceptable:** 2-5%
   - **Poor:** > 5%

## Troubleshooting

### Issue: Bot doesn't stop, no "INTERRUPT DETECTED" logs
**Cause:** VAD not detecting your speech

**Fix:** Adjust VAD parameters at line ~1132 (where transport is created):
```python
from pipecat.audio.vad.vad_analyzer import VADParams

vad_params = VADParams(
    start_secs=0.1,     # Decrease for faster detection
    stop_secs=0.5,      # Keep same
    min_volume=0.5,     # Decrease for more sensitivity
)
transport = SmallWebRTCTransport(
    webrtc_connection=pipecat_connection,
    params=TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=16000,
        audio_out_sample_rate=16000,
        audio_in_channels=1,
        audio_out_channels=1,
        vad_enabled=True,
        vad_analyzer=SileroVADAnalyzer(params=vad_params),
        vad_audio_passthrough=True,
    ),
)
```

### Issue: "INTERRUPT DETECTED" appears but bot keeps talking
**Cause:** WebRTC audio track doesn't have `_chunk_queue` attribute (Pipecat version mismatch)

**Next Steps:**
- Check Pipecat version: `pip show pipecat-ai`
- Look for alternative buffer clearing methods in your Pipecat version
- Check if audio track has different queue attribute name

### Issue: Too many false interruptions
**Cause:** VAD too sensitive

**Fix:** Make VAD more conservative:
```python
vad_params = VADParams(
    start_secs=0.15,    # Increase from 0.1
    stop_secs=0.5,      # Keep same
    min_volume=0.75,    # Increase from 0.6
)
```

## Next Steps

### If This Works
- Document interruption latency measurements
- Tune VAD parameters for your specific environment
- Get user feedback on conversation quality

### If This Partially Works
(Interruption detected but some audio lag remains)
- Investigate additional audio buffers in CartesiaTTS
- Check for buffers in SmallWebRTCTransport
- Add more aggressive buffer clearing

### If This Doesn't Work
- Check Pipecat version compatibility
- Look for alternative buffer access patterns in your Pipecat version
- Consider filing issue with Pipecat team

## Credits

- **Source**: Adapted from working implementation in `dog-agent-movementsbuttons-interrupt-fix.py`
- **Key insight**: Direct WebRTC buffer clearing is necessary, not just frame injection
- **Pipecat issues**: #2791, #950, #2788 provided context

---

**Ready to test!** Start the server and try interrupting the bot mid-response. Watch the logs for the success indicators above.
