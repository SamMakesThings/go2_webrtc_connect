import marimo

__generated_with = "0.10.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import asyncio
    import base64
    import cv2
    import numpy as np
    import anywidget
    import traitlets
    from go2_webrtc_driver.webrtc_driver import (
        Go2WebRTCConnection,
        WebRTCConnectionMethod,
    )
    from go2_webrtc_driver.constants import RTC_TOPIC, SPORT_CMD

    return (
        Go2WebRTCConnection,
        RTC_TOPIC,
        SPORT_CMD,
        WebRTCConnectionMethod,
        anywidget,
        asyncio,
        base64,
        cv2,
        mo,
        np,
        traitlets,
    )


@app.cell
def _(anywidget, traitlets):
    class Go2VideoWidget(anywidget.AnyWidget):
        """Widget to display live video from Go2 robot camera."""

        _esm = """
        function render({ model, el }) {
            const container = document.createElement("div");
            container.style.textAlign = "center";

            const img = document.createElement("img");
            img.style.maxWidth = "100%";
            img.style.border = "1px solid #ccc";
            img.style.borderRadius = "4px";
            img.src = model.get("src") || "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

            const status = document.createElement("div");
            status.style.marginTop = "8px";
            status.style.color = "#666";
            status.textContent = "Waiting for video...";

            container.appendChild(img);
            container.appendChild(status);
            el.appendChild(container);

            model.on("change:src", () => {
                const src = model.get("src");
                if (src) {
                    img.src = src;
                    status.textContent = "Live";
                    status.style.color = "#22c55e";
                }
            });
        }
        export default { render };
        """
        src = traitlets.Unicode("").tag(sync=True)
        frame = traitlets.Any(None)  # numpy array (not synced to JS)

    return (Go2VideoWidget,)


@app.cell
def _(
    Go2WebRTCConnection,
    RTC_TOPIC,
    WebRTCConnectionMethod,
    asyncio,
    base64,
    cv2,
    mo,
):
    class Go2Controller:
        """Controller for Go2 robot connection and commands."""

        def __init__(self, widget):
            self.widget = widget
            self.conn = None
            self.loop = None
            self._connected = False

        def start(self):
            """Start connection in mo.Thread - automatically cleans up on cell re-run."""

            def run_video_loop():
                thread = mo.current_thread()

                # Create asyncio loop for WebRTC
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

                async def main():
                    try:
                        # Connect to robot
                        self.conn = Go2WebRTCConnection(WebRTCConnectionMethod.LocalAP)
                        await self.conn.connect()
                        self._connected = True
                        self.conn.video.switchVideoChannel(True)

                        # Frame receiving callback
                        async def recv_frames(track):
                            while not thread.should_exit:
                                try:
                                    frame = await track.recv()
                                    img = frame.to_ndarray(format="bgr24")
                                    self.widget.frame = img
                                    # Update widget with base64 JPEG
                                    _, buf = cv2.imencode(
                                        ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80]
                                    )
                                    self.widget.src = f"data:image/jpeg;base64,{base64.b64encode(buf).decode()}"
                                except Exception:
                                    break

                        self.conn.video.add_track_callback(recv_frames)

                        # Keep running until should_exit
                        while not thread.should_exit:
                            await asyncio.sleep(0.1)

                    except Exception as e:
                        print(f"Connection error: {e}")
                    finally:
                        # Cleanup
                        if self.conn and self._connected:
                            try:
                                await self.conn.disconnect()
                            except Exception:
                                pass
                        self._connected = False

                self.loop.run_until_complete(main())
                self.loop.close()

            mo.Thread(target=run_video_loop).start()

        def send_command(self, api_id, parameter=None):
            """Send SPORT_CMD to the robot via the asyncio loop."""
            if self.conn and self.loop and self._connected:

                async def _send():
                    try:
                        payload = {"api_id": api_id}
                        if parameter is not None:
                            payload["parameter"] = parameter
                        await self.conn.datachannel.pub_sub.publish_request_new(
                            RTC_TOPIC["SPORT_MOD"], payload
                        )
                    except Exception as e:
                        print(f"Command error: {e}")

                asyncio.run_coroutine_threadsafe(_send(), self.loop)

        def move(self, x=0.0, y=0.0, z=0.0):
            """Move the robot with velocity (x: forward/back, y: strafe, z: rotation)."""
            from go2_webrtc_driver.constants import SPORT_CMD

            self.send_command(SPORT_CMD["Move"], {"x": x, "y": y, "z": z})

    return (Go2Controller,)


@app.cell
def _(Go2VideoWidget):
    # Create the video widget instance
    video_widget = Go2VideoWidget()
    return (video_widget,)


@app.cell
def _(Go2Controller, video_widget):
    # Create controller and start connection
    controller = Go2Controller(video_widget)
    controller.start()
    return (controller,)


@app.cell
def _(mo, video_widget):
    mo.md("## Go2 Robot Camera")
    video_widget
    return ()


@app.cell
def _(SPORT_CMD, controller, mo):
    # Basic controls
    stand_up_btn = mo.ui.button(
        label="Stand Up",
        on_click=lambda _: controller.send_command(SPORT_CMD["StandUp"]),
    )
    stand_down_btn = mo.ui.button(
        label="Stand Down",
        on_click=lambda _: controller.send_command(SPORT_CMD["StandDown"]),
    )
    sit_btn = mo.ui.button(
        label="Sit", on_click=lambda _: controller.send_command(SPORT_CMD["Sit"])
    )
    damp_btn = mo.ui.button(
        label="Damp", on_click=lambda _: controller.send_command(SPORT_CMD["Damp"])
    )
    recovery_btn = mo.ui.button(
        label="Recovery",
        on_click=lambda _: controller.send_command(SPORT_CMD["RecoveryStand"]),
    )
    balance_btn = mo.ui.button(
        label="Balance",
        on_click=lambda _: controller.send_command(SPORT_CMD["BalanceStand"]),
    )

    mo.md("### Basic Controls")
    mo.hstack(
        [stand_up_btn, stand_down_btn, sit_btn, damp_btn, recovery_btn, balance_btn],
        justify="start",
    )
    return balance_btn, damp_btn, recovery_btn, sit_btn, stand_down_btn, stand_up_btn


@app.cell
def _(SPORT_CMD, controller, mo):
    # Movement controls
    forward_btn = mo.ui.button(
        label="Forward", on_click=lambda _: controller.move(x=0.5, y=0, z=0)
    )
    backward_btn = mo.ui.button(
        label="Backward", on_click=lambda _: controller.move(x=-0.5, y=0, z=0)
    )
    left_btn = mo.ui.button(
        label="Left", on_click=lambda _: controller.move(x=0, y=0.3, z=0)
    )
    right_btn = mo.ui.button(
        label="Right", on_click=lambda _: controller.move(x=0, y=-0.3, z=0)
    )
    rotate_left_btn = mo.ui.button(
        label="Rotate L", on_click=lambda _: controller.move(x=0, y=0, z=0.5)
    )
    rotate_right_btn = mo.ui.button(
        label="Rotate R", on_click=lambda _: controller.move(x=0, y=0, z=-0.5)
    )
    stop_btn = mo.ui.button(
        label="STOP", on_click=lambda _: controller.send_command(SPORT_CMD["StopMove"])
    )

    mo.md("### Movement")
    mo.vstack(
        [
            mo.hstack([mo.md(""), forward_btn, mo.md("")], justify="center"),
            mo.hstack([left_btn, stop_btn, right_btn], justify="center"),
            mo.hstack(
                [rotate_left_btn, backward_btn, rotate_right_btn], justify="center"
            ),
        ]
    )
    return (
        backward_btn,
        forward_btn,
        left_btn,
        right_btn,
        rotate_left_btn,
        rotate_right_btn,
        stop_btn,
    )


@app.cell
def _(SPORT_CMD, controller, mo):
    # Trick buttons
    hello_btn = mo.ui.button(
        label="Hello", on_click=lambda _: controller.send_command(SPORT_CMD["Hello"])
    )
    stretch_btn = mo.ui.button(
        label="Stretch",
        on_click=lambda _: controller.send_command(SPORT_CMD["Stretch"]),
    )
    dance1_btn = mo.ui.button(
        label="Dance 1", on_click=lambda _: controller.send_command(SPORT_CMD["Dance1"])
    )
    dance2_btn = mo.ui.button(
        label="Dance 2", on_click=lambda _: controller.send_command(SPORT_CMD["Dance2"])
    )
    wiggle_btn = mo.ui.button(
        label="Wiggle",
        on_click=lambda _: controller.send_command(SPORT_CMD["WiggleHips"]),
    )
    wallow_btn = mo.ui.button(
        label="Wallow", on_click=lambda _: controller.send_command(SPORT_CMD["Wallow"])
    )

    mo.md("### Tricks")
    mo.hstack(
        [hello_btn, stretch_btn, dance1_btn, dance2_btn, wiggle_btn, wallow_btn],
        justify="start",
    )
    return dance1_btn, dance2_btn, hello_btn, stretch_btn, wallow_btn, wiggle_btn


@app.cell
def _(mo, np, video_widget):
    # Access the numpy array for analysis
    mo.md("### Frame Data")

    frame = video_widget.frame
    if frame is not None:
        mo.md(f"""
        **Frame Info:**
        - Shape: `{frame.shape}`
        - Dtype: `{frame.dtype}`
        - Size: `{frame.size}` pixels
        - Memory: `{frame.nbytes / 1024:.1f}` KB
        """)
    else:
        mo.md("_No frame captured yet_")

    # Export frame for use in other cells
    frame
    return (frame,)


if __name__ == "__main__":
    app.run()
