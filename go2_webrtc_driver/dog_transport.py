"""
DogTransport - A Pipecat transport for the Unitree Go2 robot.

This transport integrates with the Go2 robot's WebRTC audio streams,
providing a clean interface for Pipecat pipelines. Supports toggling
between robot speakers and local computer speakers.
"""

import asyncio
import logging
import numpy as np
import fractions
from typing import Optional, Any, Awaitable, Callable
from pydantic import BaseModel

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    StartFrame,
    EndFrame,
    CancelFrame,
    TransportMessageFrame,
    TransportMessageUrgentFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport

from aiortc import AudioStreamTrack
from av import AudioFrame

# PyAudio import for local audio output
try:
    import pyaudio
    pyaudio_available = True
except ImportError:
    pyaudio = None
    pyaudio_available = False
    logging.warning("PyAudio not available. Local audio output will be disabled.")

logger = logging.getLogger(__name__)


class DogCallbacks(BaseModel):
    """Callback handlers for Dog transport events."""
    on_app_message: Callable[[Any], Awaitable[None]]
    on_client_connected: Callable[[Any], Awaitable[None]]
    on_client_disconnected: Callable[[Any], Awaitable[None]]
    on_client_closed: Callable[[Any], Awaitable[None]]


class DogAudioStreamTrack(AudioStreamTrack):
    """Custom audio stream track for the Go2 robot."""
    
    def __init__(self, sample_rate=48000):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = 2  # Stereo
        self.samples_per_frame = 960  # 20ms of audio at 48kHz (matches working implementation)
        self.audio_queue = asyncio.Queue()
        self._timestamp = 0
        
    async def recv(self):
        """Receive the next audio frame."""
        try:
            # Get audio data from queue (blocks until available)
            audio_data = await self.audio_queue.get()
        except asyncio.TimeoutError:
            # Generate silence if no audio available
            audio_data = bytes(self.samples_per_frame * self.channels * 2)  # 16-bit stereo
            
        # Create AudioFrame (match working implementation)
        frame = AudioFrame(format='s16', layout='stereo', samples=self.samples_per_frame)
        frame.sample_rate = self.sample_rate
        frame.pts = self._timestamp
        self._timestamp += self.samples_per_frame
        
        # Fill frame with audio data (match working implementation)
        frame.planes[0].update(audio_data)
        
        return frame
    
    async def add_audio(self, audio_data: bytes):
        """Add audio data to the queue for playback."""
        await self.audio_queue.put(audio_data)


class LocalAudioManager:
    """Manages local audio input/output using PyAudio."""
    
    def __init__(self, enabled=False, sample_rate=48000, channels=2, output_device_id=None, input_device_id=None, input_enabled=False):
        self.enabled = enabled and pyaudio_available
        self.input_enabled = input_enabled and self.enabled
        self.sample_rate = sample_rate
        self.channels = channels
        self.output_device_id = output_device_id
        self.input_device_id = input_device_id
        self.pyaudio_instance = None
        self.output_stream = None
        self.input_stream = None
        self.input_queue = asyncio.Queue()
        self._input_task = None
        
        if self.enabled:
            self._initialize_pyaudio()
    
    def _initialize_pyaudio(self):
        """Initialize PyAudio for local audio input/output."""
        if not pyaudio:
            logger.error("PyAudio not available")
            self.enabled = False
            self.input_enabled = False
            return
            
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Open audio stream for output
            self.output_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                output_device_index=self.output_device_id,
                frames_per_buffer=1024
            )
            logger.info(f"Local audio output initialized - Sample rate: {self.sample_rate}Hz, Channels: {self.channels}")
            
            # Open audio stream for input if enabled
            if self.input_enabled:
                self.input_stream = self.pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=1,  # Mono input for better STT performance
                    rate=16000,  # Use 16kHz for input to match STT requirements
                    input=True,
                    input_device_index=self.input_device_id,
                    frames_per_buffer=1024,
                    stream_callback=self._input_callback
                )
                self.input_stream.start_stream()
                logger.info(f"Local microphone input initialized - Sample rate: 16000Hz, Channels: 1")
            
        except Exception as e:
            logger.error(f"Failed to initialize local audio: {e}")
            self.enabled = False
            self.input_enabled = False
    
    def _input_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio input stream."""
        if status:
            logger.warning(f"Local microphone input status: {status}")
        
        # Put audio data in queue for processing
        try:
            self.input_queue.put_nowait(in_data)
        except asyncio.QueueFull:
            logger.warning("Local microphone input queue full, dropping audio")
        
        if pyaudio:
            return (None, pyaudio.paContinue)
        else:
            return (None, 0)
    
    async def read_audio(self):
        """Read audio data from local microphone."""
        if not self.input_enabled:
            return None
        
        try:
            audio_data = await asyncio.wait_for(self.input_queue.get(), timeout=0.1)
            return audio_data
        except asyncio.TimeoutError:
            return None
    
    async def write_audio(self, audio_data: bytes):
        """Write audio data to local speakers."""
        if self.enabled and self.output_stream:
            try:
                # PyAudio write is blocking, so run in thread pool
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.output_stream.write, audio_data)
            except Exception as e:
                logger.error(f"Error writing to local audio: {e}")
    
    def close(self):
        """Close the local audio streams."""
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
        logger.info("Local audio input/output closed")


class DogClient:
    """Client that manages the Go2 WebRTC connection and audio streaming."""
    
    def __init__(self, go2_connection, callbacks: DogCallbacks, local_audio_enabled=False, local_audio_device=None, local_microphone_device=None):
        self._go2_connection = go2_connection
        self._callbacks = callbacks
        self._audio_queue = asyncio.Queue()
        self._audio_track = None
        self._audio_buffer = bytearray()
        self._running = False
        self._params = None
        self._in_sample_rate = None
        self._out_sample_rate = None
        self._connected = False
        self._local_microphone_task = None
        
        # Local audio manager for hybrid input/output
        self._local_audio = LocalAudioManager(
            enabled=local_audio_enabled,
            sample_rate=48000,  # Match robot output
            channels=2,
            output_device_id=local_audio_device,
            input_device_id=local_microphone_device,
            input_enabled=local_audio_enabled  # Enable microphone input when local audio is enabled
        )
        
    async def setup(self, params: TransportParams, frame: StartFrame):
        """Setup the client with transport parameters."""
        self._params = params
        self._in_sample_rate = params.audio_in_sample_rate or frame.audio_in_sample_rate or 16000
        # Always use 48kHz for output to the robot, regardless of input
        self._out_sample_rate = 48000  # Go2 robot requires 48kHz
        
        # Only create audio output track if we don't already have one
        if params.audio_out_enabled and not self._audio_track:
            self._audio_track = DogAudioStreamTrack(self._out_sample_rate)
            logger.info(f"DogClient: Created new audio track in setup with {self._out_sample_rate}Hz")
        
        # If we already have an audio track, ensure _out_sample_rate matches
        if self._audio_track:
            self._out_sample_rate = self._audio_track.sample_rate
            logger.info(f"DogClient: Using existing audio track with {self._out_sample_rate}Hz")
                
    async def connect(self):
        """Connect to the Go2 robot (already connected via Go2WebRTCConnection)."""
        if self._connected:
            logger.info("DogClient: Already connected, skipping")
            return
            
        if self._go2_connection.isConnected:
            logger.info("DogClient: Go2 connection established, setting up audio")
            
            # Add the audio track to the peer connection AFTER connection is established
            # This is the key difference from the previous implementation
            if self._audio_track and self._go2_connection.pc:
                logger.info("DogClient: Adding audio track to peer connection")
                self._go2_connection.pc.addTrack(self._audio_track)
                logger.info("DogClient: Audio track added successfully")
                
                # Log transceiver info
                transceivers = self._go2_connection.pc.getTransceivers()
                for i, transceiver in enumerate(transceivers):
                    if transceiver.kind == "audio":
                        logger.info(f"DogClient: Audio transceiver {i}: direction={transceiver.direction}, "
                                  f"sender.track={transceiver.sender.track if transceiver.sender else None}")
            elif not self._audio_track:
                logger.warning("DogClient: No audio track available for output")
            elif not self._go2_connection.pc:
                logger.error("DogClient: No peer connection available")
            
            # Enable audio channels
            self._go2_connection.audio.switchAudioChannel(True)
            
            # Configure audio input source based on local audio settings
            if self._local_audio.input_enabled:
                # Use local microphone only - disable robot microphone
                logger.info("DogClient: Using local microphone - robot microphone disabled")
                # Start local microphone task
                if not self._local_microphone_task:
                    self._local_microphone_task = asyncio.create_task(self._handle_local_microphone())
                    logger.info("DogClient: Local microphone task started")
            else:
                # Use robot microphone only
                logger.info("DogClient: Using robot microphone - local microphone disabled")
                # Register audio callback for robot microphone
                self._go2_connection.audio.add_track_callback(self._handle_robot_audio)
            
            self._running = True
            self._connected = True
            # Emit connected event
            await self._callbacks.on_client_connected(self._go2_connection)
        else:
            logger.error("DogClient: Go2 connection not established")
            
    async def disconnect(self):
        """Disconnect from the Go2 robot."""
        if not self._connected:
            return
        self._running = False
        self._connected = False
        
        # Stop local microphone task
        if self._local_microphone_task:
            self._local_microphone_task.cancel()
            try:
                await self._local_microphone_task
            except asyncio.CancelledError:
                pass
            self._local_microphone_task = None
            logger.info("DogClient: Local microphone task stopped")
        
        # Close local audio
        if self._local_audio:
            self._local_audio.close()
            
        await self._callbacks.on_client_disconnected(self._go2_connection)
        
    async def _handle_robot_audio(self, frame):
        """Handle incoming audio from robot."""
        if not self._running:
            return
            
        try:
            # Convert Go2 audio frame to numpy array
            audio_data = np.frombuffer(frame.to_ndarray(), dtype=np.int16)
            
            # Go2 provides 48kHz stereo audio
            # Convert stereo to mono by taking left channel
            if len(audio_data) % 2 == 0:
                stereo_data = audio_data.reshape(-1, 2)
                mono_data = stereo_data[:, 0]
            else:
                mono_data = audio_data
            
            # Downsample from 48kHz to 16kHz for better STT performance
            downsample_factor = 3  # 48000 / 16000 = 3
            downsampled_data = mono_data[::downsample_factor]
            
            # Create Pipecat audio frame
            audio_frame = InputAudioRawFrame(
                audio=downsampled_data.tobytes(),
                sample_rate=16000,
                num_channels=1
            )
            
            # Queue the frame for processing
            await self._audio_queue.put(audio_frame)
            
        except Exception as e:
            logger.error(f"DogClient: Error processing robot audio: {e}")
    
    async def _handle_local_microphone(self):
        """Handle incoming audio from local microphone."""
        logger.info("DogClient: Local microphone handler started")
        
        while self._running and self._local_audio.input_enabled:
            try:
                # Read audio from local microphone
                audio_data = await self._local_audio.read_audio()
                
                if audio_data:
                    # Convert bytes to numpy array
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    
                    # Create Pipecat audio frame (already 16kHz mono from LocalAudioManager)
                    audio_frame = InputAudioRawFrame(
                        audio=audio_array.tobytes(),
                        sample_rate=16000,
                        num_channels=1
                    )
                    
                    # Queue the frame for processing
                    await self._audio_queue.put(audio_frame)
                    
                else:
                    # Small delay to prevent busy waiting
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"DogClient: Error processing local microphone audio: {e}")
                await asyncio.sleep(0.1)
        
        logger.info("DogClient: Local microphone handler stopped")
            
    async def read_audio_frame(self):
        """Generator that yields audio frames from the robot."""
        while self._running:
            try:
                audio_frame = await self._audio_queue.get()
                yield audio_frame
            except Exception as e:
                logger.error(f"DogClient: Error reading audio frame: {e}")
                await asyncio.sleep(0.01)
                
    async def write_audio_frame(self, frame: OutputAudioRawFrame):
        """Write audio frame to both robot and local speakers (if enabled)."""
        if not self._running:
            logger.warning("DogClient: Not running, skipping audio frame")
            return
            
        try:
            # Get audio data from frame
            input_audio = np.frombuffer(frame.audio, dtype=np.int16)
            logger.debug(f"DogClient: Received audio frame - samples: {len(input_audio)}, rate: {frame.sample_rate}")
            
            # Calculate upsampling factor
            input_rate = frame.sample_rate or 16000
            output_rate = self._out_sample_rate or 48000
            upsample_factor = output_rate // input_rate
            
            # Upsample audio (simple repetition)
            if upsample_factor > 1:
                upsampled = np.repeat(input_audio, upsample_factor)
            else:
                upsampled = input_audio
                
            # Convert mono to stereo by duplicating the channel
            stereo_audio = np.stack([upsampled, upsampled], axis=1)
            stereo_bytes = stereo_audio.flatten().astype(np.int16).tobytes()
            
            # Send to local speakers first (lower latency for user feedback)
            if self._local_audio.enabled:
                await self._local_audio.write_audio(stereo_bytes)
                # When local audio is enabled, don't send to robot speakers
                logger.debug(f"DogClient: Sent audio to local speakers only")
                return
                
            # Send to robot speakers (only when local audio is disabled)
            if self._audio_track:
                # Ensure we have the right amount of data for a frame
                # Use the same calculation as the working implementation
                frame_size = self._audio_track.samples_per_frame * 2  # stereo
                frame_size_bytes = frame_size * 2  # 2 bytes per sample
                
                # Add to buffer
                self._audio_buffer.extend(stereo_bytes)
                
                # Send complete frames (match working implementation logic)
                frames_sent = 0
                while len(self._audio_buffer) >= frame_size_bytes:
                    frame_data = bytes(self._audio_buffer[:frame_size_bytes])
                    self._audio_buffer = self._audio_buffer[frame_size_bytes:]
                    
                    # Send to audio track
                    await self._audio_track.add_audio(frame_data)
                    frames_sent += 1
                    
                    # Prevent too many frames at once
                    if frames_sent >= 10:
                        break
                    
                if frames_sent > 0:
                    logger.debug(f"DogClient: Sent {frames_sent} audio frames to robot")
            else:
                logger.warning("DogClient: No audio track, skipping robot audio frame")
                
        except Exception as e:
            logger.error(f"DogClient: Error processing audio frame: {e}")
            
    async def send_message(self, frame: TransportMessageFrame | TransportMessageUrgentFrame):
        """Send a message through the data channel if available."""
        if self._running and hasattr(self._go2_connection, 'datachannel'):
            self._go2_connection.datachannel.send_message(frame.message)
            
    @property
    def is_connected(self) -> bool:
        return self._go2_connection.isConnected


class DogInputTransport(BaseInputTransport):
    """Input transport for receiving audio from the Go2 robot."""
    
    def __init__(self, client: DogClient, params: TransportParams, **kwargs):
        super().__init__(params, **kwargs)
        self._client = client
        self._params = params
        self._receive_audio_task = None
        self._initialized = False
        
    async def start(self, frame: StartFrame):
        """Start the input transport."""
        await super().start(frame)
        
        if self._initialized:
            return
            
        self._initialized = True
        
        await self._client.setup(self._params, frame)
        await self._client.connect()
        
        if not self._receive_audio_task and self._params.audio_in_enabled:
            self._receive_audio_task = self.create_task(self._receive_audio())
            
        await self.set_transport_ready(frame)
        
    async def stop(self, frame: EndFrame):
        """Stop the input transport."""
        await super().stop(frame)
        await self._stop_tasks()
        await self._client.disconnect()
        
    async def cancel(self, frame: CancelFrame):
        """Cancel the input transport."""
        await super().cancel(frame)
        await self._stop_tasks()
        await self._client.disconnect()
        
    async def _stop_tasks(self):
        """Stop all running tasks."""
        if self._receive_audio_task:
            await self.cancel_task(self._receive_audio_task)
            self._receive_audio_task = None
            
    async def _receive_audio(self):
        """Receive audio from the robot."""
        try:
            # Wait a bit to ensure pipeline is ready
            await asyncio.sleep(0.5)
            
            async for audio_frame in self._client.read_audio_frame():
                if audio_frame:
                    await self.push_audio_frame(audio_frame)
                    
        except Exception as e:
            logger.error(f"DogInputTransport: Exception receiving audio: {e}")
            
    async def push_app_message(self, message: Any):
        """Push an app message frame."""
        frame = TransportMessageUrgentFrame(message=message)
        await self.push_frame(frame)


class DogOutputTransport(BaseOutputTransport):
    """Output transport for sending audio to the Go2 robot."""
    
    def __init__(self, client: DogClient, params: TransportParams, **kwargs):
        super().__init__(params, **kwargs)
        self._client = client
        self._params = params
        self._initialized = False
        
    async def start(self, frame: StartFrame):
        """Start the output transport."""
        await super().start(frame)
        
        if self._initialized:
            return
            
        self._initialized = True
        
        await self._client.setup(self._params, frame)
        await self._client.connect()
        await self.set_transport_ready(frame)
        
    async def stop(self, frame: EndFrame):
        """Stop the output transport."""
        await super().stop(frame)
        await self._client.disconnect()
        
    async def cancel(self, frame: CancelFrame):
        """Cancel the output transport."""
        await super().cancel(frame)
        await self._client.disconnect()
        
    async def send_message(self, frame: TransportMessageFrame | TransportMessageUrgentFrame):
        """Send a message through the transport."""
        await self._client.send_message(frame)
        
    async def write_audio_frame(self, frame: OutputAudioRawFrame):
        """Write an audio frame to the robot."""
        logger.debug(f"DogOutputTransport: Writing audio frame")
        await self._client.write_audio_frame(frame)


class DogTransport(BaseTransport):
    """
    Transport for the Unitree Go2 robot that integrates with Pipecat pipelines.
    
    This transport handles bidirectional audio streaming between the robot
    and Pipecat, with automatic format conversion and event handling.
    Supports exclusive toggle between robot speakers and local computer speakers.
    """
    
    def __init__(
        self,
        go2_connection,
        params: TransportParams,
        input_name: Optional[str] = None,
        output_name: Optional[str] = None,
        local_audio_enabled: bool = False,
        local_audio_device: Optional[int] = None,
        local_microphone_device: Optional[int] = None,
    ):
        """
        Initialize the DogTransport.
        
        Args:
            go2_connection: An active Go2WebRTCConnection instance
            params: Transport parameters (audio settings, VAD, etc.)
            input_name: Optional name for the input transport
            output_name: Optional name for the output transport
            local_audio_enabled: Enable local computer speaker output and microphone input
            local_audio_device: PyAudio device ID for local output (None for default)
            local_microphone_device: PyAudio device ID for local input (None for default)
        """
        super().__init__(input_name=input_name, output_name=output_name)
        
        self._params = params
        self._go2_connection = go2_connection
        self._local_audio_enabled = local_audio_enabled
        self._local_audio_device = local_audio_device
        self._local_microphone_device = local_microphone_device
        
        self._callbacks = DogCallbacks(
            on_app_message=self._on_app_message,
            on_client_connected=self._on_client_connected,
            on_client_disconnected=self._on_client_disconnected,
            on_client_closed=self._on_client_closed,
        )
        
        # Create client with local audio support
        self._client = DogClient(
            go2_connection, 
            self._callbacks,
            local_audio_enabled=local_audio_enabled,
            local_audio_device=local_audio_device,
            local_microphone_device=local_microphone_device
        )
        
        self._input: Optional[DogInputTransport] = None
        self._output: Optional[DogOutputTransport] = None
        
        # Register supported handlers
        self._register_event_handler("on_app_message")
        self._register_event_handler("on_client_connected")
        self._register_event_handler("on_client_disconnected")
        self._register_event_handler("on_client_closed")
        
        # Log configuration
        if local_audio_enabled:
            output_device_str = f" (device {local_audio_device})" if local_audio_device is not None else " (default device)"
            input_device_str = f" (device {local_microphone_device})" if local_microphone_device is not None else " (default device)"
            logger.info(f"DogTransport: Local audio enabled - Computer speakers{output_device_str} and microphone{input_device_str}")
        else:
            logger.info("DogTransport: Robot audio enabled - Robot speakers and microphone only")
        
    def input(self) -> DogInputTransport:
        """Get the input transport."""
        if not self._input:
            self._input = DogInputTransport(
                self._client, self._params, name=self._input_name
            )
        return self._input
        
    def output(self) -> DogOutputTransport:
        """Get the output transport."""
        if not self._output:
            self._output = DogOutputTransport(
                self._client, self._params, name=self._output_name
            )
        return self._output
        
    async def send_audio(self, frame: OutputAudioRawFrame):
        """Send audio frame to robot."""
        if self._output:
            await self._output.queue_frame(frame, FrameDirection.DOWNSTREAM)
            
    async def send_image(self, frame: Frame):
        """Send image frame - not implemented for audio-only transport."""
        logger.warning("DogTransport: send_image called but not implemented for audio-only transport")
        
    async def _on_app_message(self, message: Any):
        """Handle app message."""
        if self._input:
            await self._input.push_app_message(message)
        await self._call_event_handler("on_app_message", message)
        
    async def _on_client_connected(self, connection):
        """Handle client connected event."""
        await self._call_event_handler("on_client_connected", self, connection)
        
    async def _on_client_disconnected(self, connection):
        """Handle client disconnected event."""
        await self._call_event_handler("on_client_disconnected", self, connection)
        
    async def _on_client_closed(self, connection):
        """Handle client closed event."""
        await self._call_event_handler("on_client_closed", self, connection)
