import asyncio
import json
import sys
import websockets

sys.stdout.reconfigure(encoding='utf-8')

class PersistentAutoStudy:
    def __init__(self):
        self.ws = None
        self.msg_id = 0
        self.pending = {}
        self.session_id = None
        self.target_id = None
        self.listen_task = None

    async def connect(self):
        with open(r"C:\Users\Lenovo\AppData\Local\Google\Chrome\User Data\DevToolsActivePort") as f:
            lines = f.read().splitlines()
            port = lines[0]
            browser_path = lines[1]
        
        ws_url = f"ws://127.0.0.1:{port}{browser_path}"
        print(f"[*] 正在连接 Chrome 调试接口 (若弹出提示请点击允许): {ws_url}")
        
        self.ws = await websockets.connect(
            ws_url,
            max_size=20*1024*1024,
            open_timeout=60,
            ping_interval=20,
            ping_timeout=20
        )
        self.listen_task = asyncio.create_task(self._listen())
        
        res = await self.send("Target.getTargets")
        targets = res.get("targetInfos", [])
        page_targets = [t for t in targets if t.get("type") == "page"]
        
        match = next((t for t in page_targets if "fifedu.com" in t.get("url", "")), None)
        if not match and page_targets:
            match = page_targets[0]
            
        if not match:
            raise Exception("未找到 fifedu.com 学习页面")
            
        self.target_id = match["targetId"]
        print(f"[+] 成功锁定页面: {match.get('title')} -> {match.get('url')}")
        
        attach_res = await self.send("Target.attachToTarget", {"targetId": self.target_id, "flatten": True})
        self.session_id = attach_res.get("sessionId")
        print(f"[+] 成功建立持久会话: {self.session_id}")

    async def _listen(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                if "id" in data and data["id"] in self.pending:
                    self.pending[data["id"]].set_result(data)
                elif data.get("method") == "Target.attachedToTarget":
                    if not self.session_id:
                        self.session_id = data.get("params", {}).get("sessionId")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print("[!] 监听异常:", e)

    async def send(self, method, params=None, use_session=False):
        self.msg_id += 1
        mid = self.msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut
        
        payload = {"id": mid, "method": method}
        if params:
            payload["params"] = params
        if use_session and self.session_id:
            payload["sessionId"] = self.session_id
            
        await self.ws.send(json.dumps(payload))
        res = await fut
        del self.pending[mid]
        if "error" in res:
            raise Exception(f"CDP Error: {res['error']}")
        return res.get("result", {})

    async def eval(self, script):
        res = await self.send("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True,
            "awaitPromise": True
        }, use_session=True)
        return res.get("result", {}).get("value")

    async def press_arrow_right(self):
        await self.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "windowsVirtualKeyCode": 39,
            "key": "ArrowRight",
            "code": "ArrowRight"
        }, use_session=True)
        await asyncio.sleep(0.05)
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "windowsVirtualKeyCode": 39,
            "key": "ArrowRight",
            "code": "ArrowRight"
        }, use_session=True)

    async def press_page_down(self):
        await self.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "windowsVirtualKeyCode": 34,
            "key": "PageDown",
            "code": "PageDown"
        }, use_session=True)
        await asyncio.sleep(0.05)
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "windowsVirtualKeyCode": 34,
            "key": "PageDown",
            "code": "PageDown"
        }, use_session=True)

    async def press_space(self):
        await self.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "windowsVirtualKeyCode": 32,
            "key": " ",
            "code": "Space"
        }, use_session=True)
        await asyncio.sleep(0.05)
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "windowsVirtualKeyCode": 32,
            "key": " ",
            "code": "Space"
        }, use_session=True)

    async def click_at(self, x, y):
        await self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        }, use_session=True)
        await asyncio.sleep(0.05)
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        }, use_session=True)

    async def wheel_down(self, x, y, delta_y=400):
        await self.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": x,
            "y": y,
            "deltaX": 0,
            "deltaY": delta_y
        }, use_session=True)

    async def run(self):
        await self.connect()
        print("[*] 自动化常驻守护进程已启动，持续监听并处理（视频/PPT/文档/PDF/练习/跳过单元检测）...")
        
        while True:
            try:
                # 1. 检查是否有弹窗需要确认（如交卷确认、跳转下一节提示）
                modal_handled = await self.eval("""
                (() => {
                    const confirmBtn = Array.from(document.querySelectorAll('.el-message-box__btns button, .el-dialog button, .el-button')).find(b => {
                        const t = b.innerText.trim();
                        return t === '确定' || t === '确认' || t === '继续' || t === '下一步';
                    });
                    if (confirmBtn) {
                        confirmBtn.click();
                        return true;
                    }
                    return false;
                })()
                """)
                if modal_handled:
                    print("[+] 检测到确认对话框，已自动点击【确定】")
                    await asyncio.sleep(2)
                    continue

                # 2. 获取当前页面与活动列表状态
                state = await self.eval("""
                (() => {
                    const items = Array.from(document.querySelectorAll('.activity-list-item')).map((el, i) => ({
                        i,
                        name: el.querySelector('.activity-name')?.innerText.trim() || '',
                        status: Array.from(el.querySelectorAll('.activityStatus')).map(s => s.innerText.trim()).join(' | '),
                        isActive: el.classList.contains('is-active'),
                        isFinish: !!el.querySelector('.is-finish')
                    }));
                    
                    const activeIndex = items.findIndex(x => x.isActive);
                    const curItem = activeIndex >= 0 ? items[activeIndex] : null;
                    const curName = curItem ? curItem.name : (document.querySelector('.chapter-activity-title, h3')?.innerText.trim() || '');
                    const curChapter = document.querySelector('.current-chapter-name, .chapter-name-title')?.innerText.split('\\n')[0].trim() || '';
                    
                    // 精确判断是否为单元检测模块（仅匹配章节名称或课件名称）
                    const isExam = (/单元检测|单元测验|阶段检测|阶段测验/i.test(curChapter)) || 
                                  (/单元检测|单元测验|阶段检测|阶段测验/i.test(curName));
                    
                    const video = document.querySelector('video');
                    const hasPPT = !!document.querySelector('.pptIframe, .pptContainer, .btnWrap');
                    const pptPage = document.querySelector('.btnWrap .page')?.innerText.trim() || '';
                    
                    // 判断是否为文档 .doc / .docx / .pdf
                    const isDoc = (/.\\.(doc|docx|pdf)($|\\s)/i.test(curName)) || 
                                  (curItem && (curItem.status.includes('DOC') || curItem.status.includes('PDF') || curItem.status.includes('文档'))) || 
                                  !!document.querySelector('.docWrap, .wordWrap, .pdfWrap, [class*="pdf"], [class*="word"], [class*="doc-preview"]');
                    
                    const hasExercise = !isExam && !isDoc && !hasPPT && !video && (
                        !!document.querySelector('.CloseBtn, [class*="exercise"]') || 
                        Array.from(document.querySelectorAll('button, .el-button')).some(b => b.innerText.includes('练习') || b.innerText.includes('选完了'))
                    );
                    
                    return {
                        items,
                        totalItems: items.length,
                        activeIndex: activeIndex >= 0 ? activeIndex : 0,
                        curName,
                        curChapter,
                        isExam,
                        isDoc,
                        hasVideo: !!video && (video.offsetWidth > 0 || video.duration > 0),
                        videoInfo: video ? {
                            currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
                            duration: Number.isFinite(video.duration) ? video.duration : 0,
                            paused: video.paused,
                            ended: video.ended
                        } : null,
                        hasPPT,
                        pptPage,
                        hasExercise
                    };
                })()
                """)
                
                if not state:
                    await asyncio.sleep(2)
                    continue
                    
                total_items = state.get('totalItems', 0)
                active_idx = state.get('activeIndex', 0)
                cur_chapter = state.get('curChapter', '')
                items = state.get('items', [])
                cur_item_name = state.get('curName') or (items[active_idx]['name'] if total_items > active_idx else '未知')
                is_last_item = (active_idx >= total_items - 1)
                
                # --- 1. 单元检测模块判断：直接跳转下一节 ---
                if state.get('isExam'):
                    print(f"[单元检测] 识别到单元检测模块 [{cur_chapter} / {cur_item_name}]，按规则直接跳转下一节...")
                    await asyncio.sleep(1.5)
                    await self._navigate_next(is_last_item=True, active_idx=0)
                    await asyncio.sleep(4)
                    continue

                # --- 2. 空章节检测（如无课件内容） ---
                if total_items == 0:
                    print(f"[*] 当前章节 [{cur_chapter}] 无课件内容，自动点击【继续学习下一节】进入下一章...")
                    await asyncio.sleep(2)
                    await self._navigate_next(is_last_item=True, active_idx=0)
                    await asyncio.sleep(4)
                    continue

                # --- 3. 文档与 PDF 处理 (.doc / .docx / .pdf) ---
                if state.get('isDoc'):
                    ext = "PDF" if ('.pdf' in cur_item_name.lower()) else "文档"
                    print(f"[{ext}] 正在处理课件 [{active_idx+1}/{total_items}]: {cur_item_name}")
                    print(f"[*] 正在将进度条从上往下拉到底...")
                    
                    doc_center = await self.eval("""
                    (() => {
                        const frame = document.querySelector('iframe, .pdfWrap, .docWrap, .main');
                        if (frame) {
                            const r = frame.getBoundingClientRect();
                            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                        }
                        return { x: window.innerWidth / 2, y: window.innerHeight / 2 };
                    })()
                    """)
                    if doc_center:
                        await self.click_at(doc_center['x'], doc_center['y'])
                        await asyncio.sleep(0.1)

                    for scroll_step in range(1, 11):
                        await self.eval(f"""
                        (() => {{
                            const ratio = {scroll_step} / 10;
                            const all = Array.from(document.querySelectorAll('*')).filter(el => {{
                                const s = window.getComputedStyle(el);
                                return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                            }});
                            
                            all.forEach(el => {{
                                el.scrollTop = el.scrollHeight * ratio;
                                el.dispatchEvent(new Event('scroll'));
                            }});
                            
                            window.scrollTo(0, document.body.scrollHeight * ratio);
                        }})()
                        """)
                        if doc_center:
                            await self.wheel_down(doc_center['x'], doc_center['y'], delta_y=500)
                        await self.press_page_down()
                        await asyncio.sleep(0.5)
                        
                    await self.eval("""
                    (() => {
                        const all = Array.from(document.querySelectorAll('*')).filter(el => {
                            const s = window.getComputedStyle(el);
                            return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                        });
                        all.forEach(el => {
                            el.scrollTop = el.scrollHeight;
                            el.dispatchEvent(new Event('scroll'));
                        });
                        window.scrollTo(0, document.body.scrollHeight);
                    })()
                    """)
                    print(f"[+] [{ext}] 已完全拉到底部，等待 3 秒同步阅读记录...")
                    await asyncio.sleep(3)
                    await self._navigate_next(is_last_item, active_idx)
                    await asyncio.sleep(4)
                    continue

                # --- 4. 视频处理 ---
                elif state.get('hasVideo') and state.get('videoInfo'):
                    v = state['videoInfo']
                    cur = v.get('currentTime') or 0.0
                    dur = v.get('duration') or 0.0
                    
                    if dur == 0.0:
                        print(f"[视频] 正在加载视频元数据: {cur_item_name}...")
                        await self.eval("document.querySelector('video')?.play()?.catch(e => {})")
                        await asyncio.sleep(1.5)
                        continue
                        
                    print(f"[视频] 正在处理课件 [{active_idx+1}/{total_items}]: {cur_item_name} (进度: {cur:.1f}/{dur:.1f}s)")
                    
                    if v.get('paused'):
                        await self.eval("""
                        (() => {
                            const v = document.querySelector('video');
                            if (v) v.play().catch(e => {});
                            const playBtn = document.querySelector('.xgplayer-start, .xgplayer-play, .xg-icon-play');
                            if (playBtn) playBtn.click();
                        })()
                        """)
                        await asyncio.sleep(1)
                        
                    if cur < dur - 3 and not v.get('ended'):
                        await self.press_arrow_right()
                        await self.eval("""
                        (() => {
                            const p = document.querySelector('.xgplayer') || document.querySelector('video') || window;
                            p.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39, bubbles: true }));
                        })()
                        """)
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        print(f"[视频] 课件播放完成: {cur_item_name}")
                        await asyncio.sleep(2)
                        await self._navigate_next(is_last_item, active_idx)
                        await asyncio.sleep(4)
                        continue

                # --- 5. PPT 处理 ---
                elif state.get('hasPPT'):
                    ppt_page = state.get('pptPage') or ""
                    print(f"[PPT] 正在处理课件 [{active_idx+1}/{total_items}]: {cur_item_name} (当前页码: {ppt_page})")
                    
                    is_ppt_done = False
                    if "/" in ppt_page:
                        parts = [p.strip() for p in ppt_page.split("/")]
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            if int(parts[0]) >= int(parts[1]):
                                is_ppt_done = True
                                
                    if not is_ppt_done:
                        iframe_center = await self.eval("""
                        (() => {
                            const iframe = document.querySelector('.pptIframe');
                            if (!iframe) return null;
                            const r = iframe.getBoundingClientRect();
                            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                        })()
                        """)
                        if iframe_center:
                            await self.click_at(iframe_center['x'], iframe_center['y'])
                            await asyncio.sleep(0.1)
                            await self.press_space()
                        else:
                            await self.eval("""
                            (() => {
                                const btn = document.querySelector('.btnWrap .arrow-right') || document.querySelector('.btnWrap .pptBtn:last-child');
                                if (btn) btn.click();
                            })()
                            """)
                        await asyncio.sleep(1.2)
                        continue
                    else:
                        print(f"[PPT] 课件翻页完毕: {cur_item_name}")
                        await self.press_space()
                        await asyncio.sleep(0.5)
                        await self.press_space()
                        await asyncio.sleep(2)
                        await self._navigate_next(is_last_item, active_idx)
                        await asyncio.sleep(4)
                        continue

                # --- 6. 自适应练习处理 ---
                elif state.get('hasExercise'):
                    print(f"[练习] 正在处理课件 [{active_idx+1}/{total_items}]: {cur_item_name}")
                    
                    start_btn_clicked = await self.eval("""
                    (() => {
                        const btn = Array.from(document.querySelectorAll('button, .el-button')).find(b => {
                            const t = b.innerText.trim();
                            return t.includes('继续练习') || t.includes('开始练习');
                        });
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    })()
                    """)
                    if start_btn_clicked:
                        print("[+] 已点击【开始/继续练习】")
                        await asyncio.sleep(3)
                        continue
                        
                    submit_clicked = await self.eval("""
                    (() => {
                        const closeBtn = document.querySelector('.CloseBtn') || Array.from(document.querySelectorAll('*')).find(e => e.innerText.trim() === '交卷');
                        if (closeBtn) {
                            closeBtn.click();
                            return true;
                        }
                        return false;
                    })()
                    """)
                    if submit_clicked:
                        print("[+] 已点击【交卷】")
                        await asyncio.sleep(1.5)
                        await self.eval("""
                        (() => {
                            const confirmBtn = Array.from(document.querySelectorAll('.el-message-box__btns button, .el-dialog button, .el-button')).find(b => {
                                const t = b.innerText.trim();
                                return t === '确定' || t === '确认';
                            });
                            if (confirmBtn) confirmBtn.click();
                        })()
                        """)
                        print("[+] 已确认交卷，等待结算...")
                        await asyncio.sleep(3)
                        await self._navigate_next(is_last_item, active_idx)
                        await asyncio.sleep(4)
                        continue
                    else:
                        print("[!] 当前练习已完成或未找到交卷按钮，进入下一个课件...")
                        await self._navigate_next(is_last_item, active_idx)
                        await asyncio.sleep(4)
                        continue

                else:
                    print(f"[*] 当前活动未知或正在加载中: {cur_chapter} / {cur_item_name}，稍候重试...")
                    await asyncio.sleep(2)

            except Exception as loop_e:
                print("[!] 循环异常:", loop_e)
                await asyncio.sleep(3)

    async def _navigate_next(self, is_last_item, active_idx):
        if is_last_item:
            print("[>>>] 正在点击【继续学习下一节】进入下一章...")
            await self.eval("""
            (() => {
                const nextSec = Array.from(document.querySelectorAll('button, .el-button, a')).find(b => {
                    const t = b.innerText.trim();
                    return t.includes('继续学习下一节') || t.includes('下一节');
                });
                if (nextSec) nextSec.click();
            })()
            """)
        else:
            next_idx = active_idx + 1
            print(f"[>>>] 当前课件已完成，正在切换至下一个课件 (序号: {next_idx + 1})...")
            await self.eval(f"""
            (() => {{
                const items = Array.from(document.querySelectorAll('.activity-list-item'));
                if (items.length > {next_idx}) {{
                    items[{next_idx}].click();
                }}
            }})()
            """)

if __name__ == "__main__":
    app = PersistentAutoStudy()
    asyncio.run(app.run())
