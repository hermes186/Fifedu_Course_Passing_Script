import asyncio
import json
import websockets

class CDPClient:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.pending_responses = {}
        self.target_id = None
        self.session_id = None
        self.listen_task = None

    async def connect(self, target_url_keyword="fifedu.com"):
        while True:
            try:
                with open(r"C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\DevToolsActivePort") as f:
                    lines = f.read().splitlines()
                    port = lines[0]
                    browser_path = lines[1]
                
                ws_url = f"ws://127.0.0.1:{port}{browser_path}"
                self.ws = await websockets.connect(ws_url, max_size=20*1024*1024, open_timeout=300)
                self.listen_task = asyncio.create_task(self._listen())
                
                # Get targets
                res = await self.send("Target.getTargets")
                targets = res.get("targetInfos", [])
                page_targets = [t for t in targets if t.get("type") == "page"]
                
                matching_target = None
                for t in page_targets:
                    if target_url_keyword in t.get("url", ""):
                        matching_target = t
                        break
                if not matching_target and page_targets:
                    matching_target = page_targets[0]
                    
                if not matching_target:
                    raise Exception("No matching page target found")
                    
                self.target_id = matching_target["targetId"]
                print(f"Target found: {matching_target.get('title')} -> {matching_target.get('url')[:60]}")
                
                # Attach to target
                attach_res = await self.send("Target.attachToTarget", {"targetId": self.target_id, "flatten": True})
                self.session_id = attach_res.get("sessionId")
                print(f"Attached to target session: {self.session_id}")
                return
            except Exception as e:
                print(f"Connect waiting: {e}")
                await asyncio.sleep(3)

    async def _listen(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                if "id" in data and data["id"] in self.pending_responses:
                    self.pending_responses[data["id"]].set_result(data)
                elif data.get("method") == "Target.attachedToTarget":
                    # Can capture sessionId if needed
                    if not self.session_id:
                        self.session_id = data.get("params", {}).get("sessionId")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print("Listen error:", e)

    async def send(self, method, params=None, use_session=False):
        self.msg_id += 1
        current_id = self.msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending_responses[current_id] = fut
        
        msg = {"id": current_id, "method": method}
        if params:
            msg["params"] = params
        if use_session and self.session_id:
            msg["sessionId"] = self.session_id
            
        await self.ws.send(json.dumps(msg))
        try:
            res = await asyncio.wait_for(fut, timeout=6.0)
        except asyncio.TimeoutError:
            if current_id in self.pending_responses:
                del self.pending_responses[current_id]
            return {}
        if current_id in self.pending_responses:
            del self.pending_responses[current_id]
        if "error" in res:
            raise Exception(f"CDP Error: {res['error']}")
        return res.get("result", {})

    async def eval(self, expression):
        try:
            res = await self.send("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True
            }, use_session=True)
            return res.get("result", {}).get("value")
        except Exception:
            return None

    async def press_arrow_right(self):
        await self.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "windowsVirtualKeyCode": 39, "key": "ArrowRight", "code": "ArrowRight"
        }, use_session=True)
        await asyncio.sleep(0.02)
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp", "windowsVirtualKeyCode": 39, "key": "ArrowRight", "code": "ArrowRight"
        }, use_session=True)

    async def press_page_down(self):
        await self.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "windowsVirtualKeyCode": 34, "key": "PageDown", "code": "PageDown"
        }, use_session=True)
        await asyncio.sleep(0.02)
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp", "windowsVirtualKeyCode": 34, "key": "PageDown", "code": "PageDown"
        }, use_session=True)

    async def press_end(self):
        await self.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown", "windowsVirtualKeyCode": 35, "key": "End", "code": "End"
        }, use_session=True)
        await asyncio.sleep(0.02)
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp", "windowsVirtualKeyCode": 35, "key": "End", "code": "End"
        }, use_session=True)

    async def click_at(self, x, y):
        await self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
        }, use_session=True)
        await asyncio.sleep(0.05)
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
        }, use_session=True)

    async def wheel_down(self, x, y, delta_y=500):
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": delta_y
        }, use_session=True)

    async def close(self):
        if self.listen_task:
            self.listen_task.cancel()
        if self.ws:
            await self.ws.close()

if __name__ == "__main__":
    async def run_test():
        client = CDPClient()
        await client.connect()
        info = await client.eval("""(() => {
            const video = document.querySelector('video');
            return {
                title: document.title,
                url: window.location.href,
                hasVideo: !!video,
                paused: video ? video.paused : null,
                currentTime: video ? video.currentTime : null,
                duration: video ? video.duration : null,
                playbackRate: video ? video.playbackRate : null
            };
        })()""")
        print("Page Video Info:", info)
        await client.close()

    asyncio.run(run_test())
