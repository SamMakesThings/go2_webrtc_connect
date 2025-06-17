
from aiortc import AudioStreamTrack, RTCRtpSender
import logging
import sounddevice as sd
import numpy as np
import wave


class WebRTCAudioChannel:
    def __init__(self, pc, datachannel, audio_track=None) -> None:
        self.pc = pc
        self.datachannel = datachannel
        
        # If an audio track is provided, add it to the peer connection
        if audio_track:
            self.pc.addTrack(audio_track)
            logging.info("Added custom audio track to peer connection")
        else:
            # Only add transceiver if no track is provided
            self.pc.addTransceiver("audio", direction="sendrecv")
            logging.info("Added audio transceiver without track")

        # List to hold multiple callbacks
        self.track_callbacks = []
        
    async def frame_handler(self, frame):
        logging.info("Receiving audio frame")

        # Trigger all registered callbacks
        for callback in self.track_callbacks:
            try:
                # Call each callback function and pass the track
                await callback(frame)
            except Exception as e:
                logging.error(f"Error in callback {callback}: {e}")
    
    def add_track_callback(self, callback):
        """
        Adds a callback to be triggered when an audio track is received.
        """
        if callable(callback):
            self.track_callbacks.append(callback)
        else:
            logging.warning(f"Callback {callback} is not callable.")  

    def switchAudioChannel(self, switch: bool):
        self.datachannel.switchAudioChannel(switch)
