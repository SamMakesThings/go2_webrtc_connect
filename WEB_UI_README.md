# Go2 Robot Dog - Web UI Control System

## Overview

This system provides a **complete web-based interface** for controlling your Unitree Go2 robot dog with both **voice commands** AND **manual controls**, simultaneously!

## What You Get

✅ **Voice Agent** - Talk to your AI-powered robot dog
✅ **Manual Control UI** - Button-based movement controls
✅ **Keyboard Shortcuts** - Quick WASD-style controls
✅ **Real-time Status** - See connection status instantly
✅ **Works Together** - Voice and manual control at the same time!

---

## Files Created

1. **`dog-agent-web-ui.py`** - Main Python script with web server
2. **`dog_control_ui.html`** - Robot control interface
3. **`WEB_UI_README.md`** - This file

---

## Quick Start

### 1. Install Dependencies

Make sure you have all required packages:
```bash
pip install -e .
pip install fastapi uvicorn pipecat-ai-small-webrtc-prebuilt
```

### 2. Configure Environment

Edit your `.env` file with your API keys:
```bash
# Required API Keys
OPENAI_API_KEY=your_openai_key_here
CARTESIA_API_KEY=your_cartesia_key_here
DEEPGRAM_API_KEY=your_deepgram_key_here

# Robot Connection (choose one)
GO2_SERIAL_NUMBER=B42D2000XXXXXXXX
# or
# GO2_ROBOT_IP=192.168.8.181

# Optional
WANDB_API_KEY=your_wandb_key_here
```

### 3. Run the System

```bash
python3 dog-agent-web-ui.py
```

You should see:
```
🤖 Connecting robot in main event loop...
✅ ROBOT CONNECTED SUCCESSFULLY!
Voice agent server starting...
Open your browser to:
  - Voice Agent: http://localhost:7860
  - Robot Control UI: http://localhost:7860/control
```

### 4. Open in Browser

**Two Options:**

#### Option A: Voice Agent (with manual control)
Open: **http://localhost:7860**
- Voice conversation interface
- Manual controls available via /control in another tab

#### Option B: Manual Control Only
Open: **http://localhost:7860/control**
- Full movement control UI
- No voice needed
- Works independently

---

## Control Interface

### Movement Controls (9-button grid)

```
        ↑ Forward
    ↰   ↓ Back    ↱
← Left  ⏹ Stop  → Right

↰ = Turn Left
↱ = Turn Right
```

### Posture Controls
- **Stand Up** - Robot stands
- **Sit Down** - Robot sits

### Trick Controls
- **👋 Hello** - Wave greeting
- **🧘 Stretch** - Stretching movement
- **💃 Wiggle Hips** - Hip wiggle dance
- **❤️ Finger Heart** - Heart gesture

### Mode Controls
- **Normal Mode** - Basic sport movements
- **AI Mode** - Advanced capabilities

---

## Keyboard Shortcuts

When the control UI is focused:

| Key | Action |
|-----|--------|
| **W** | Move Forward |
| **S** | Move Backward |
| **A** | Strafe Left |
| **D** | Strafe Right |
| **Q** | Turn Left |
| **E** | Turn Right |
| **Space** | Stop |

---

## How It Works

### Architecture

```
┌──────────────────────────────────────────────┐
│           Browser (Port 7860)                 │
├─────────────────────┬────────────────────────┤
│   Voice Agent UI    │  Control UI (/control) │
│   (WebRTC Audio)    │  (HTTP REST API)       │
└──────────┬──────────┴───────────┬─────────────┘
           │                      │
           └──────────┬───────────┘
                      │
           ┌──────────▼──────────┐
           │   FastAPI Server     │
           │  (dog-agent-web-ui)  │
           └──────────┬───────────┘
                      │
           ┌──────────▼──────────┐
           │   Go2 Robot Dog     │
           │   (WebRTC + Data)   │
           └─────────────────────┘
```

### API Endpoints

The control UI communicates via REST API:

- `GET /api/robot/status` - Check connection
- `POST /api/robot/move` - Movement (forward/back/left/right)
- `POST /api/robot/turn` - Rotation (left/right)
- `POST /api/robot/stop` - Stop movement
- `POST /api/robot/sit` - Sit down
- `POST /api/robot/stand` - Stand up
- `POST /api/robot/hello` - Wave hello
- `POST /api/robot/stretch` - Stretch
- `POST /api/robot/wiggle_hips` - Wiggle hips
- `POST /api/robot/finger_heart` - Finger heart
- `POST /api/robot/mode` - Switch mode (normal/ai)

---

## Usage Scenarios

### Scenario 1: Voice Only
**Use Case:** Natural conversation with the robot

1. Open http://localhost:7860
2. Allow microphone access
3. Talk to the robot
4. Robot responds via voice and may do tricks

**Example:**
- *You: "Hey robot, can you wave hello?"*
- *Robot: "Woof woof! Sure thing! [waves]"*

### Scenario 2: Manual Control Only
**Use Case:** Direct piloting without voice

1. Open http://localhost:7860/control
2. Use buttons or keyboard
3. Control movements precisely

**Example:**
- Click Forward → Robot moves forward
- Press W → Robot moves forward
- Click Sit → Robot sits

### Scenario 3: Hybrid Control (BEST!)
**Use Case:** Voice conversation WHILE manually piloting

1. Open http://localhost:7860 (voice agent)
2. Open http://localhost:7860/control in another tab/window
3. Talk to the robot in one window
4. Control movements in the other

**Example:**
- *You: "What can you do?"* (in voice window)
- *Robot: "Woof! I can do lots of tricks! Watch this!"*
- [You click "Wiggle Hips" in control window]
- *Robot: "Haha! That's fun! Woof woof!"*

---

## Troubleshooting

### Issue: "Robot not connected"

**Check:**
1. Is the robot powered on?
2. Are you on the same network?
3. Is GO2_SERIAL_NUMBER or GO2_ROBOT_IP set correctly in `.env`?
4. Check terminal output for connection errors

**Solution:**
```bash
# Stop the server (Ctrl+C)
# Check your .env file
# Verify robot IP or serial number
# Restart: python3 dog-agent-web-ui.py
```

### Issue: Voice not working

**Check:**
1. Did you allow microphone access in browser?
2. Are your API keys valid (OPENAI, CARTESIA, DEEPGRAM)?
3. Check browser console for errors (F12)

**Solution:**
- Refresh the page and allow microphone again
- Check .env file for correct API keys
- Look at terminal logs for API errors

### Issue: Controls not responding

**Check:**
1. Is the status indicator green?
2. Check browser console (F12) for errors
3. Check terminal logs for command failures

**Solution:**
- Refresh the control page
- Check robot connection status
- Verify robot is not in an error state

### Issue: "Another WebRTC client connected"

**Cause:** The official Unitree app is open

**Solution:**
1. Close the Unitree mobile app
2. Wait 10 seconds
3. Restart dog-agent-web-ui.py

---

## Safety Notes

⚠️ **Important Safety Guidelines:**

1. **Clear Space** - Ensure 2m clearance around robot
2. **Supervision** - Always supervise robot operation
3. **Emergency Stop** - Know how to power off robot
4. **Stable Surface** - Operate on flat, stable ground
5. **Test Movements** - Start with small movements first

**Recommended Testing Sequence:**
1. Start with "Stand Up"
2. Try small movements (forward/back)
3. Test turns
4. Try tricks only when comfortable
5. Use "Sit" to safely stop

---

## Advanced Configuration

### Custom Movement Distance

Edit in `dog-agent-web-ui.py`:
```python
# Line ~918
result = await dog_move(direction, 0.3)  # Change 0.3 to your preferred distance
```

### Custom Turn Speed

Edit in `dog-agent-web-ui.py`:
```python
# Line ~932
z = 0.5 if direction == "left" else -0.5  # Change 0.5 for turn speed
```

### Change Server Port

Edit in `dog-agent-web-ui.py`:
```python
# Line ~1089
config = uvicorn.Config(app, host="0.0.0.0", port=7860, ...)  # Change 7860
```

---

## Comparison with Other Scripts

| Feature | dog-agent.py | dog-agent-local.py | dog-agent-web-ui.py |
|---------|--------------|-------------------|---------------------|
| Voice Agent | ✅ | ✅ | ✅ |
| Manual Control | ❌ | ❌ | ✅ |
| Keyboard Control | ❌ | ❌ | ✅ |
| Web UI | ❌ | ✅ (voice only) | ✅ (full) |
| Status | ⚠️ Broken | ✅ Working | ✅ Working |
| **Recommended** | ❌ | 🟡 Basic | ✅ **BEST** |

### When to Use Each:

- **`dog-agent-web-ui.py`** ← **Use this!** (Full featured)
- **`dog-agent-local.py`** → Voice only, no manual control
- **`dog-agent.py`** → Currently broken, needs repair

---

## FAQ

**Q: Can I use voice AND manual control at the same time?**
A: Yes! Open both http://localhost:7860 (voice) and http://localhost:7860/control (manual) in separate tabs.

**Q: Do I need the Unitree app?**
A: No! This replaces the Unitree app. Make sure the app is CLOSED before running.

**Q: Can I control from my phone?**
A: Yes! Open http://YOUR_COMPUTER_IP:7860/control on your phone's browser (must be on same network).

**Q: What if the robot doesn't move?**
A: Check that it's in "Normal" or "AI" mode. Some movements require specific modes.

**Q: Can I add custom movements?**
A: Yes! Add new endpoints in `dog-agent-web-ui.py` and buttons in `dog_control_ui.html`.

**Q: Is this safe to use?**
A: Yes, but always supervise the robot and maintain clear space around it.

---

## Next Steps

Want to extend functionality?

1. **Add new tricks** - Edit `dog-agent-web-ui.py` to add more SPORT_CMD commands
2. **Custom UI** - Modify `dog_control_ui.html` for your own design
3. **Mobile app** - The REST API can be called from any client
4. **Automation** - Write scripts that call the API endpoints
5. **Video feed** - Add robot camera stream to the UI

---

## Support

Having issues? Check:

1. Terminal logs for errors
2. Browser console (F12) for JavaScript errors
3. `CLAUDE.md` for architecture details
4. Original `README.md` for robot setup

**Common Log Messages:**

- `✅ ROBOT CONNECTED SUCCESSFULLY!` → Good!
- `❌ Failed to connect to robot` → Check network/credentials
- `Robot is not connected` → Check GO2_SERIAL_NUMBER in .env
- `Another WebRTC client connected` → Close Unitree app

---

## Credits

- **Base System:** go2_webrtc_connect by legion1581
- **Voice Agent:** Pipecat AI framework
- **Web UI:** Created with Claude Code

**Enjoy controlling your robot dog! 🐕🤖**
