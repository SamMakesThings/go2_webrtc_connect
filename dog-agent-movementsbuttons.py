#!/usr/bin/env python3
"""
Go2 Robot Voice Agent - Local Audio Version

This script creates a voice-controlled agent using Pipecat AI with local system audio.
It uses SmallWebRTCTransport for audio input/output through a web browser client,
while maintaining the ability to send commands to the Go2 robot separately.

Features:
- Local system audio: Browser microphone input and speaker output
- Speech-to-text and text-to-speech processing
- OpenAI LLM for natural conversation
- Real-time audio streaming via WebRTC
- Go2 robot connection available for future command integration

Usage:
    python dog-agent-local.py
    Then open your browser to http://localhost:7860

Environment Variables Required:
    OPENAI_API_KEY - Your OpenAI API key
    CARTESIA_API_KEY - Your Cartesia API key (for TTS)
    DEEPGRAM_API_KEY - Your Deepgram API key (for STT)
    GO2_SERIAL_NUMBER - Your robot's serial number (optional, for future commands)
"""

# Global robot connection variable - MUST be defined before any async operations
go2_robot_connection = None
robot_connection_in_progress = False

# IMMEDIATE ROBOT CONNECTION - Before any other imports or initialization
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Import robot modules immediately after environment variables
from go2_webrtc_driver.webrtc_driver import Go2WebRTCConnection, WebRTCConnectionMethod

print("🤖 IMMEDIATE ROBOT CONNECTION - Before any other initialization...")

async def immediate_robot_connection():
    """Connect to robot immediately, before any other code runs."""
    global go2_robot_connection
    

    
    try:
        serial_number = os.getenv("GO2_SERIAL_NUMBER")
        robot_ip = os.getenv("GO2_ROBOT_IP")
        
        if not serial_number and not robot_ip:
            print("ℹ️ No robot credentials found - will run in chat-only mode")
            return None
        
        # Use the simple working pattern from the examples
        if serial_number:
            print(f"🔗 Connecting to robot with serial number: {serial_number}")
            go2_robot_connection = Go2WebRTCConnection(WebRTCConnectionMethod.LocalSTA, serialNumber=serial_number)
        else:
            print(f"🔗 Connecting to robot with IP address: {robot_ip}")
            go2_robot_connection = Go2WebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=robot_ip)
        
        # Simple connection - just like the working examples
        await go2_robot_connection.connect()
        
        print("✅ ROBOT CONNECTED SUCCESSFULLY! Physical tricks are now available!")
        return go2_robot_connection
        
    except Exception as e:
        print(f"❌ Failed to connect to robot: {e}")
        go2_robot_connection = None
        return None

# Robot connection will be established in the main event loop to prevent connection closure

# NOW continue with normal imports after robot is connected
import logging
import io
import wave
import time
import random
from typing import Optional, Dict
import weave

# FastAPI imports for web server
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import RedirectResponse
import uvicorn

# SmallWebRTC imports
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport
from pipecat.transports.network.webrtc_connection import SmallWebRTCConnection
from pipecat.transports.base_transport import TransportParams
from pipecat.audio.vad.silero import SileroVADAnalyzer

# Go2 WebRTC imports for robot command integration
from go2_webrtc_driver.constants import RTC_TOPIC, SPORT_CMD

# Import keyboard control libraries
import threading
import termios
import tty
import select

# Global flag to control keyboard thread
keyboard_control_active = True

def get_key():
    """Get a single keypress from stdin."""
    tty.setraw(sys.stdin.fileno())
    select.select([sys.stdin], [], [], 0)
    key = sys.stdin.read(1)
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key

async def move_dog(direction: str):
    """Move the dog in the specified direction."""
    if not go2_robot_connection:
        print("❌ Robot not connected")
        return
    
    try:
        # Standard movement distance
        distance = 0.3
        
        # Map direction to x, y coordinates
        if direction == "forward":
            x, y = distance, 0
        elif direction == "backward":
            x, y = -distance, 0
        elif direction == "left":
            x, y = 0, distance
        elif direction == "right":
            x, y = 0, -distance
        else:
            return
        
        print(f"🤖 Moving {direction}...")
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {
                "api_id": SPORT_CMD["Move"],
                "parameter": {"x": x, "y": y, "z": 0}
            }
        )
    except Exception as e:
        print(f"❌ Movement failed: {e}")

async def turn_dog(direction: str):
    """Turn the dog left or right."""
    if not go2_robot_connection:
        print("❌ Robot not connected")
        return
    
    try:
        # Map direction to z rotation
        if direction == "left":
            z = 0.5  # Positive Z turns left
        elif direction == "right":
            z = -0.5  # Negative Z turns right
        else:
            return
        
        print(f"🤖 Turning {direction}...")
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {
                "api_id": SPORT_CMD["Move"],
                "parameter": {"x": 0, "y": 0, "z": z}
            }
        )
    except Exception as e:
        print(f"❌ Turn failed: {e}")

def keyboard_control_thread(loop):
    """Thread function to handle keyboard input."""
    global keyboard_control_active
    
    print("""
🎮 Keyboard Controls:
   I
J  K  L   U O
I = Forward
K = Backward
J = Left
L = Right
U = Turn Left
O = Turn Right
Q = Quit keyboard control
""")
    
    while keyboard_control_active:
        key = get_key().lower()
        
        if key == 'q':
            print("Stopping keyboard control...")
            keyboard_control_active = False
            break
            
        # Map keys to movements
        if key == 'i':
            asyncio.run_coroutine_threadsafe(move_dog("forward"), loop)
        elif key == 'k':
            asyncio.run_coroutine_threadsafe(move_dog("backward"), loop)
        elif key == 'j':
            asyncio.run_coroutine_threadsafe(move_dog("left"), loop)
        elif key == 'l':
            asyncio.run_coroutine_threadsafe(move_dog("right"), loop)
        elif key == 'u':
            asyncio.run_coroutine_threadsafe(turn_dog("left"), loop)
        elif key == 'o':
            asyncio.run_coroutine_threadsafe(turn_dog("right"), loop)

# Store terminal settings
settings = termios.tcgetattr(sys.stdin)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Weave for audio tracing (after robot connection)
weave.init(project_name="dog-agent-local")

# Try to import the prebuilt UI
try:
    from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI
except ImportError:
    logger.warning("pipecat_ai_small_webrtc_prebuilt not found. Install with: pip install pipecat-ai-small-webrtc-prebuilt")
    SmallWebRTCPrebuiltUI = None


@weave.op()
async def save_audio(audio: bytes, sample_rate: int, num_channels: int, name: str):
    """Save audio data to a buffer for Weave tracking."""
    if len(audio) > 0:
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wf:
                wf.setsampwidth(2)
                wf.setnchannels(num_channels)
                wf.setframerate(sample_rate)
                wf.writeframes(audio)
            logger.info(f"Saving {name} audio data ({len(audio)} bytes)")
            buffer.seek(0)
            return wave.open(io.BytesIO(buffer.getvalue()), "rb")
    else:
        logger.debug(f"No {name} audio data to save")


async def initialize_robot_connection():
    """Initialize connection to the Go2 robot using the simple working pattern."""
    global go2_robot_connection
    
    try:
        serial_number = os.getenv("GO2_SERIAL_NUMBER")
        robot_ip = os.getenv("GO2_ROBOT_IP")
        
        if not serial_number and not robot_ip:
            logger.warning("No robot credentials found. Robot commands will not be available.")
            return None
        
        # Use the simple working pattern from the examples
        if serial_number:
            logger.info(f"🤖 Connecting to robot with serial number: {serial_number}")
            go2_robot_connection = Go2WebRTCConnection(WebRTCConnectionMethod.LocalSTA, serialNumber=serial_number)
        else:
            logger.info(f"🤖 Connecting to robot with IP address: {robot_ip}")
            go2_robot_connection = Go2WebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=robot_ip)
        
        # Simple connection - just like the working examples
        await go2_robot_connection.connect()
        
        logger.info("✅ Successfully connected to Go2 robot! Woof woof! Physical tricks are now available!")
        return go2_robot_connection
        
    except Exception as e:
        logger.error(f"❌ Failed to connect to robot: {e}")
        go2_robot_connection = None
        return None


# Robot command functions for the LLM
@weave.op()
async def dog_hello():
    """Make the dog perform a greeting/hello movement. This also works for shaking hands."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot perform hello movement."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["Hello"]}
        )
        return "Performing hello greeting movement!"
    except Exception as e:
        return f"Failed to perform hello: {e}"


@weave.op()
async def dog_sit():
    """Make the dog sit down."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot sit."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["Sit"]}
        )
        return "Sitting down!"
    except Exception as e:
        return f"Failed to sit: {e}"


@weave.op()
async def dog_stand():
    """Make the dog stand up."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot stand up."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["StandUp"]}
        )
        return "Standing up!"
    except Exception as e:
        return f"Failed to stand up: {e}"


@weave.op()
async def dog_dance(dance_number: int = 1):
    """Make the dog perform a dance routine.
    
    Args:
        dance_number: 1 or 2 for different dance routines
    """
    if not go2_robot_connection:
        return "Robot is not connected. Cannot dance."
    
    dance_cmd = SPORT_CMD["Dance1"] if dance_number == 1 else SPORT_CMD["Dance2"]
    dance_name = f"Dance {dance_number}"
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": dance_cmd}
        )
        return f"Performing {dance_name}!"
    except Exception as e:
        return f"Failed to perform {dance_name}: {e}"


# @weave.op()
# async def dog_backflip():
#     """Make the dog perform a backflip."""
#     if not go2_robot_connection:
#         return "Robot is not connected. Cannot perform backflip."
#     
#     try:
#         await go2_robot_connection.datachannel.pub_sub.publish_request_new(
#             RTC_TOPIC["SPORT_MOD"], 
#             {"api_id": SPORT_CMD["BackFlip"], "parameter": {"data": True}}
#         )
#         return "Performing a backflip!"
#     except Exception as e:
#         return f"Failed to perform backflip: {e}"


@weave.op()
async def dog_stretch():
    """Make the dog perform a stretching movement."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot stretch."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["Stretch"]}
        )
        return "Stretching!"
    except Exception as e:
        return f"Failed to stretch: {e}"


@weave.op()
async def dog_wiggle_hips():
    """Make the dog wiggle its hips."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot wiggle hips."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["WiggleHips"]}
        )
        return "Wiggling hips!"
    except Exception as e:
        return f"Failed to wiggle hips: {e}"


@weave.op()
async def dog_finger_heart():
    """Make the dog perform a finger heart gesture."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot make finger heart."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {"api_id": SPORT_CMD["FingerHeart"]}
        )
        return "Making a finger heart!"
    except Exception as e:
        return f"Failed to make finger heart: {e}"


@weave.op()
async def dog_move(direction: str = "forward", distance: float = 0.3):
    """Make the dog move in a specified direction.
    
    Args:
        direction: "forward", "backward", "left", or "right"
        distance: How far to move (0.1 to 12.0)
    """
    if not go2_robot_connection:
        return "Robot is not connected. Cannot move."
    
    # Clamp distance to safe range
    distance = max(0.1, min(12.0, distance))
    
    # Set movement parameters based on direction
    if direction.lower() == "forward":
        x, y = distance, 0
    elif direction.lower() == "backward":
        x, y = -distance, 0
    elif direction.lower() == "left":
        x, y = 0, distance
    elif direction.lower() == "right":
        x, y = 0, -distance
    else:
        return f"Unknown direction: {direction}. Use 'forward', 'backward', 'left', or 'right'."
    
    try:
        await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["SPORT_MOD"], 
            {
                "api_id": SPORT_CMD["Move"],
                "parameter": {"x": x, "y": y, "z": 0}
            }
        )
        return f"Moving {direction} with distance {distance}!"
    except Exception as e:
        return f"Failed to move {direction}: {e}"


@weave.op()
async def switch_to_ai_mode():
    """Switch the robot to AI mode for advanced capabilities and movements."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot switch to AI mode."
    
    try:
        # First check current mode
        response = await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"], 
            {"api_id": 1001}
        )
        
        if response and response.get('data', {}).get('header', {}).get('status', {}).get('code') == 0:
            import json
            data = json.loads(response['data']['data'])
            current_mode = data['name']
            
            if current_mode == "ai":
                return "Already in AI mode! Ready for advanced moves! Woof!"
            
            # Switch to AI mode
            await go2_robot_connection.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["MOTION_SWITCHER"], 
                {
                    "api_id": 1002,
                    "parameter": {"name": "ai"}
                }
            )
            return f"Switched from {current_mode} mode to AI mode! Now I can do advanced tricks! Woof woof!"
        else:
            return "Could not check current mode, but attempting to switch to AI mode..."
            
    except Exception as e:
        return f"Failed to switch to AI mode: {e}"


@weave.op()
async def switch_to_normal_mode():
    """Switch the robot to normal/general mode for basic sport movements."""
    if not go2_robot_connection:
        return "Robot is not connected. Cannot switch to normal mode."
    
    try:
        # First check current mode
        response = await go2_robot_connection.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"], 
            {"api_id": 1001}
        )
        
        if response and response.get('data', {}).get('header', {}).get('status', {}).get('code') == 0:
            import json
            data = json.loads(response['data']['data'])
            current_mode = data['name']
            
            if current_mode == "normal":
                return "Already in normal mode! Ready for basic commands! Woof!"
            
            # Switch to normal mode
            await go2_robot_connection.datachannel.pub_sub.publish_request_new(
                RTC_TOPIC["MOTION_SWITCHER"], 
                {
                    "api_id": 1002,
                    "parameter": {"name": "normal"}
                }
            )
            return f"Switched from {current_mode} mode to normal mode! Back to basics! Woof woof!"
        else:
            return "Could not check current mode, but attempting to switch to normal mode..."
            
    except Exception as e:
        return f"Failed to switch to normal mode: {e}"


@weave.op()
async def check_robot_status():
    """Check if the robot is connected and ready for commands."""
    if go2_robot_connection:
        return "Robot is connected and ready for commands! Woof woof!"
    else:
        return "Robot is not connected right now. I can still chat with you though!"


@weave.op()
async def run_voice_agent(transport):
    """Run the voice agent pipeline with the given transport."""
    # Import Pipecat modules ONLY when needed, after robot connection
    from pipecat.frames.frames import (
        InputAudioRawFrame,
        OutputAudioRawFrame,
        Frame,
        StartFrame,
        EndFrame,
        CancelFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
    from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.services.cartesia.tts import CartesiaTTSService
    from pipecat.services.deepgram.stt import DeepgramSTTService

    
    session_id = f"{int(time.time())}-{random.randint(0, 1000)}"
    logger.info(f"Starting voice agent session: {session_id}")
    
    # DON'T initialize robot connection immediately - wait for browser to connect first
    # This avoids WebRTC data channel conflicts between browser and robot connections
    
    # Initialize AI services
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    
    # Type assertions since we already checked these exist
    assert deepgram_key is not None
    assert openai_key is not None
    assert cartesia_key is not None
    
    stt = DeepgramSTTService(api_key=deepgram_key)
    
    # Create LLM with function tools for dog commands
    robot_tools = [
        {
            "type": "function",
            "function": {
                "name": "check_robot_status",
                "description": "Check if the robot body is connected and ready for physical commands",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dog_hello",
                "description": "Make the dog perform a greeting or hello movement. This also works for shaking hands.",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dog_sit",
                "description": "Make the dog sit down",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dog_stand",
                "description": "Make the dog stand up",
            }
        },
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "dog_dance",
        #         "description": "Make the dog perform a dance routine",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "dance_number": {
        #                     "type": "integer",
        #                     "description": "Dance routine number (1 or 2)",
        #                     "enum": [1, 2]
        #                 }
        #             }
        #         }
        #     }
        # },
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "dog_backflip",
        #         "description": "Make the dog perform a backflip. Make sure it explicitly asks for space around it and confirms people aren't close before performing this.",
        #     }
        # },
        {
            "type": "function",
            "function": {
                "name": "dog_stretch",
                "description": "Make the dog stretch",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dog_wiggle_hips",
                "description": "Make the dog wiggle its hips",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dog_finger_heart",
                "description": "Make the dog perform a finger heart gesture",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "dog_move",
                "description": "Make the dog move in a specified direction",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "description": "Direction to move",
                            "enum": ["forward", "backward", "left", "right"]
                        },
                        "distance": {
                            "type": "number",
                            "description": "Distance to move (0.1 to 12.0)",
                            "minimum": 0.1,
                            "maximum": 12.0
                        }
                    },
                    "required": ["direction"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "switch_to_ai_mode",
                "description": "Switch the robot to AI mode for advanced capabilities and movements",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "switch_to_normal_mode",
                "description": "Switch the robot to normal/general mode for basic sport movements",
            }
        }
    ]
    
    llm = OpenAILLMService(
        api_key=openai_key,
        model="gpt-4o-mini"
    )
    
    tts = CartesiaTTSService(
        api_key=cartesia_key,
        voice_id="4df027cb-2920-4a1f-8c34-f21529d5c3fe"  # Movieman voice
    )
    
    # Set up conversation context with robot capabilities
    messages = [
        {
            "role": "system",
            "content": "You are a playful robot dog named Bee with a big personality! Your responses should be fewer than 10 words."
                      "You interact over voice. Don't include any emojis or special characters in your responses."
                      "You can hear through your ears and speak through your voice. Your physical robot body may be "
                      "connecting in the background, so you can check your status anytime with check_robot_status. "
                      "As a dog, you love to: say hello with tail wags, sit like a good dog, stand proudly, "
                      "stretch when you wake up, wiggle your hips when happy, "
                      "make finger hearts to show love, and run around (forward/backward/left/right). "
                      "You can also switch between AI mode (for advanced capabilities) and normal mode (for basic movements) "
                      "using switch_to_ai_mode and switch_to_normal_mode functions. "
                      "You should frequently say 'woof woof' and make dog puns in your responses. "
                      "Be friendly, energetic, and mischievous - you might decide to do tricks or moves on your own "
                      "when you think it would be fun or appropriate, not just when explicitly asked. "
                      "You're like an excited puppy who loves to play and show off your abilities! "
                      "Keep responses brief since they're spoken aloud. No special characters. "
                      "Start by introducing yourself as the dog you are. You can end responses by saying `woof`."
        }
    ]
    
    # Set up conversation context and management
    context = OpenAILLMContext(messages, tools=robot_tools)  # type: ignore
    context_aggregator = llm.create_context_aggregator(context)
    
    # Register all robot functions with the LLM service (like the working example)
    logger.info(f"🔧 Registering {len(robot_tools)} functions with LLM service...")
    
    async def handle_robot_function_call(params):
        """Handle robot function calls using new FunctionCallParams format."""
        function_name = params.function_name
        args = params.arguments
        
        logger.info(f"🤖 Executing robot function: {function_name} with args: {args}")

        try:
            # Check robot connection before calling any robot functions
            if function_name != "check_robot_status" and not go2_robot_connection:
                return {"message": "Robot is not connected. Cannot perform physical actions."}
            

            
            # Call the appropriate function
            if function_name == "check_robot_status":
                result = await check_robot_status()
            elif function_name == "dog_hello":
                result = await dog_hello()
            elif function_name == "dog_sit":
                result = await dog_sit()
            elif function_name == "dog_stand":
                result = await dog_stand()
            elif function_name == "dog_dance":
                result = await dog_dance(args.get("dance_number", 1))
            # elif function_name == "dog_backflip":
            #     result = await dog_backflip()
            elif function_name == "dog_stretch":
                result = await dog_stretch()
            elif function_name == "dog_wiggle_hips":
                result = await dog_wiggle_hips()
            elif function_name == "dog_finger_heart":
                result = await dog_finger_heart()
            elif function_name == "dog_move":
                result = await dog_move(
                    args.get("direction", "forward"),
                    args.get("distance", 0.3)
                )
            elif function_name == "switch_to_ai_mode":
                result = await switch_to_ai_mode()
            elif function_name == "switch_to_normal_mode":
                result = await switch_to_normal_mode()
            else:
                result = f"Unknown function: {function_name}"
            
            logger.info(f"✅ Robot function result: {result}")
            
            # Return the result directly (new format)
            return {"message": str(result)}
            
        except Exception as e:
            logger.error(f"❌ Error executing {function_name}: {e}")
            return {"message": f"Error executing {function_name}: {e}"}
    
    # Register each function with the LLM service
    function_names = [
        "check_robot_status", "dog_hello", "dog_sit", "dog_stand", "dog_dance",
        # "dog_backflip",  # Commented out for safety
        "dog_stretch", "dog_wiggle_hips", "dog_finger_heart", 
        "dog_move", "switch_to_ai_mode", "switch_to_normal_mode"
    ]
    
    for function_name in function_names:
        llm.register_function(function_name, handle_robot_function_call)
        logger.info(f"  ✅ Registered function: {function_name}")
    
    # Add function call handler for robot commands (keeping for compatibility)
    @llm.event_handler("on_function_calls_update")
    async def on_function_calls_update(function_calls):
        # Handle function calls from the LLM
        for function_call in function_calls:
            function_name = function_call.get("name")
            function_args = function_call.get("arguments", "{}")
            call_id = function_call.get("id")
            
            try:
                import json
                args = json.loads(function_args) if function_args else {}
                
                logger.info(f"🤖 Executing robot command: {function_name} with args: {args}")
                
                # Call the appropriate function
                if function_name == "check_robot_status":
                    result = await check_robot_status()
                elif function_name == "dog_hello":
                    result = await dog_hello()
                elif function_name == "dog_sit":
                    result = await dog_sit()
                elif function_name == "dog_stand":
                    result = await dog_stand()
                elif function_name == "dog_dance":
                    result = await dog_dance(args.get("dance_number", 1))
                # elif function_name == "dog_backflip":
                #     result = await dog_backflip()
                elif function_name == "dog_stretch":
                    result = await dog_stretch()
                elif function_name == "dog_wiggle_hips":
                    result = await dog_wiggle_hips()
                elif function_name == "dog_finger_heart":
                    result = await dog_finger_heart()
                elif function_name == "dog_move":
                    result = await dog_move(
                        args.get("direction", "forward"),
                        args.get("distance", 0.3)
                    )
                elif function_name == "switch_to_ai_mode":
                    result = await switch_to_ai_mode()
                elif function_name == "switch_to_normal_mode":
                    result = await switch_to_normal_mode()
                else:
                    result = f"Unknown function: {function_name}"
                
                logger.info(f"✅ Robot command result: {result}")
                
                # Add the function result to the conversation context
                if call_id:
                    from openai.types.chat.chat_completion_tool_message_param import ChatCompletionToolMessageParam
                    tool_message = ChatCompletionToolMessageParam(
                        role="tool",
                        tool_call_id=call_id,
                        content=str(result)
                    )
                    context.add_message(tool_message)
                
            except Exception as e:
                logger.error(f"❌ Error executing {function_name}: {e}")
                result = f"Error executing {function_name}: {e}"
                
                # Add error result to context
                if call_id:
                    from openai.types.chat.chat_completion_tool_message_param import ChatCompletionToolMessageParam
                    tool_message = ChatCompletionToolMessageParam(
                        role="tool",
                        tool_call_id=call_id,
                        content=str(result)
                    )
                    context.add_message(tool_message)
    
    # Create audio buffer processor for recording
    audiobuffer = AudioBufferProcessor(enable_turn_audio=True)
    
    # Build the pipeline with interruption support
    pipeline = Pipeline([
        transport.input(),              # Receive audio from web client
        stt,                            # Convert speech to text
        context_aggregator.user(),      # Add user messages to context
        llm,                            # Process text with LLM
        tts,                            # Convert text to speech
        audiobuffer,
        transport.output(),             # Send audio responses to web client
        context_aggregator.assistant(), # Add assistant responses to context
    ])
    
    # Create and run task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        conversation_id=session_id,
    )
    
    # Set up audio buffer event handlers for Weave tracking
    @audiobuffer.event_handler("on_audio_data")
    @weave.op()
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        await save_audio(audio, sample_rate, num_channels, "full")
    
    @audiobuffer.event_handler("on_user_turn_audio_data")
    @weave.op()
    async def on_user_turn_audio_data(buffer, audio, sample_rate, num_channels):
        logger.info("Recording user turn audio")
        await save_audio(audio, sample_rate, num_channels, "user")
    
    @audiobuffer.event_handler("on_bot_turn_audio_data")
    @weave.op()
    async def on_bot_turn_audio_data(buffer, audio, sample_rate, num_channels):
        logger.info("Recording bot turn audio")
        await save_audio(audio, sample_rate, num_channels, "bot")
    
    # Start recording
    await audiobuffer.start_recording()
    
    # Set up transport event handlers
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, webrtc_connection):
        logger.info("Web client connected for audio")
        # Queue initial frame to start the pipeline
        await task.queue_frame(StartFrame())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, webrtc_connection):
        logger.info("Web client disconnected")
        await task.cancel()
    
    # Run the pipeline
    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    await runner.run(task)


async def async_startup():
    """Async startup function that connects robot and starts web server in same event loop."""
    
    # Check for required environment variables
    required_env_vars = ["OPENAI_API_KEY", "CARTESIA_API_KEY", "DEEPGRAM_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these in your .env file or environment")
        sys.exit(1)
    
    # 🔧 FIX: Connect robot in the SAME event loop as the web server
    print("🤖 Connecting robot in main event loop to keep WebRTC connection alive...")
    serial_number = os.getenv("GO2_SERIAL_NUMBER")
    robot_ip = os.getenv("GO2_ROBOT_IP")
    
    if serial_number or robot_ip:
        try:
            await immediate_robot_connection()
            print("✅ Robot connected successfully in main event loop!")
            logger.info("✅ Robot connection established and will stay alive with web server")
        except Exception as e:
            print(f"❌ Robot connection failed: {e}")
            logger.warning("⚠️ Robot connection failed - continuing in chat-only mode")
    else:
        print("ℹ️ No robot credentials found - running in chat-only mode")
        logger.info("ℹ️ No robot connection available - agent will work in chat-only mode")
    
    # Now start the web server 
    try:
        # Create FastAPI app
        app = FastAPI()
        
        # Store connections by pc_id
        pcs_map: Dict[str, SmallWebRTCConnection] = {}
        
        ice_servers = ["stun:stun.l.google.com:19302"]
        
        # Mount the prebuilt UI if available
        if SmallWebRTCPrebuiltUI:
            app.mount("/client", SmallWebRTCPrebuiltUI)
        else:
            logger.warning("Prebuilt UI not available. You'll need to create your own WebRTC client.")
        
        @app.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url="/client/")
        
        @app.get("/debug/status")
        async def debug_status():
            return {
                "status": "running",
                "connections": len(pcs_map),
                "ice_servers": ice_servers
            }
        
        @app.get("/test")
        async def test_client():
            # Serve the simple test client
            try:
                with open("test_webrtc_client.html", "r") as f:
                    html_content = f.read()
                from fastapi.responses import HTMLResponse
                return HTMLResponse(content=html_content)
            except FileNotFoundError:
                return {"error": "test_webrtc_client.html not found. Make sure it's in the same directory."}
        
        @app.post("/api/offer")
        async def offer(request: dict, background_tasks: BackgroundTasks):
            try:
                logger.info(f"Received offer request: {request}")
                pc_id = request.get("pc_id")
                
                if pc_id and pc_id in pcs_map:
                    pipecat_connection = pcs_map[pc_id]
                    logger.info(f"Reusing existing connection for pc_id: {pc_id}")
                    await pipecat_connection.renegotiate(
                        sdp=request["sdp"],
                        type=request["type"],
                        restart_pc=request.get("restart_pc", False),
                    )
                else:
                    logger.info("Creating new WebRTC connection")
                    pipecat_connection = SmallWebRTCConnection(ice_servers)
                    await pipecat_connection.initialize(sdp=request["sdp"], type=request["type"])
                    
                    @pipecat_connection.event_handler("closed")
                    async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
                        logger.info(f"Discarding peer connection for pc_id: {webrtc_connection.pc_id}")
                        pcs_map.pop(webrtc_connection.pc_id, None)
                    
                    logger.info("Creating transport")
                    # Configure transport with VAD for interruptions
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
                            vad_analyzer=SileroVADAnalyzer(),
                            vad_audio_passthrough=True,
                        ),
                    )
                    logger.info("Starting voice agent task")
                    background_tasks.add_task(run_voice_agent, transport)
                
                answer = pipecat_connection.get_answer()
                logger.info(f"Sending answer: {answer}")
                # Updating the peer connection inside the map
                pcs_map[answer["pc_id"]] = pipecat_connection
                
                return answer
                
            except Exception as e:
                logger.error(f"Error in offer endpoint: {e}")
                raise
        
        logger.info("Voice agent server starting...")
        logger.info("Open your browser to http://localhost:7860")
        logger.info("Press Ctrl+C to stop...")
        
        # Use uvicorn's async server to avoid event loop conflicts
        config = uvicorn.Config(app, host="0.0.0.0", port=7860, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
        
    except Exception as e:
        logger.error(f"Error running voice agent server: {e}")
        raise


def main():
    """Main function - robot will be connected in the main event loop."""
    
    # Check for required environment variables first
    required_env_vars = ["OPENAI_API_KEY", "CARTESIA_API_KEY", "DEEPGRAM_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file or environment")
        sys.exit(1)
    
    print("🚀 Starting Go2 Voice Agent with Keyboard Control")
    print("=" * 60)
    print("🔧 Robot will connect in main event loop to maintain WebRTC connection")
    
    # Initialize Weave for audio tracing
    print("📊 Initializing Weave audio tracing...")
    weave.init(project_name="dog-agent-local")
    
    # Start web server
    print("🌐 Starting web server...")
    try:
        # Check if FastAPI and uvicorn are available
        try:
            import fastapi
            import uvicorn
        except ImportError:
            print("FastAPI and uvicorn are required. Install with: pip install fastapi uvicorn")
            sys.exit(1)
        
        print("🚀 Starting web server on http://localhost:7860")
        print("🎤 Voice agent ready for browser connections!")
        print("=" * 60)
        
        # Start the web server and keyboard control
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Start keyboard control thread
            keyboard_thread = threading.Thread(target=keyboard_control_thread, args=(loop,))
            keyboard_thread.daemon = True  # Thread will exit when main program exits
            keyboard_thread.start()
            print("🎮 Keyboard control thread started")
            
            # Run the main event loop
            loop.run_until_complete(async_startup())
        finally:
            # Clean up
            global keyboard_control_active
            keyboard_control_active = False  # Signal keyboard thread to stop
            if 'keyboard_thread' in locals():
                keyboard_thread.join(timeout=1.0)  # Wait for keyboard thread
            loop.close()
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        
    except Exception as e:
        print(f"❌ Error running voice agent server: {e}")
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nVoice agent stopped by user")
        sys.exit(0) 