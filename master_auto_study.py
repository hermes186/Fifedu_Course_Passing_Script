import asyncio
import json
import sys
import time
from cdp_client import CDPClient

sys.stdout.reconfigure(encoding='utf-8')

WORK_HOME_URL = "https://icourse.fifedu.com/istp-manage/work/home"
INDEX_URL = "https://icourse.fifedu.com/istp-learning-center/index?courseId=228af449c3894cad9085fdf11da9e08d&classId=3704030000001038252&termId=a8d245fff4fa446cb59b135eb938a6dd"

class FIFMasterAutoStudy(CDPClient):
    def __init__(self):
        super().__init__()
        self.completed_sections = set()
        self.completed_courses = set()
        self.last_index_url = INDEX_URL
        # 初始跳过名单包含已全部刷过但平台端记录异常的小节
        self.skip_sections = {
            "8-1-6",
            "8-2-4",
            "8-2-3",
            "8-2-5",
            "8-2-6*",
            "振动和波动-拓展学习",
            "9-1-1",
            "薄膜干涉",
            "劈尖干涉",
            "9-2-1",
            "9-2-3",
            "波动光学-拓展学习",
            "11-3"
        }
        self.current_chapter_name = ""
        self.processed_in_visit = set()

    async def handle_modals(self):
        """通用模态框/弹窗确认处理"""
        clicked = await self.eval("""
        (() => {
            const isVisible = (el) => el.offsetWidth > 0 && el.offsetHeight > 0 && window.getComputedStyle(el).display !== 'none' && window.getComputedStyle(el).visibility !== 'hidden';
            const btns = Array.from(document.querySelectorAll('.el-message-box__btns button, .el-dialog button, .el-button, [class*="dialog"] button')).filter(isVisible);
            const targetBtn = btns.find(b => {
                const t = b.innerText.trim();
                return t === '确定' || t === '确认' || t === '我知道了' || t === '下一步';
            });
            if (targetBtn) {
                targetBtn.click();
                return targetBtn.innerText.trim();
            }
            return null;
        })()
        """)
        if clicked:
            print(f"[+] 自动处理对话框，点击【{clicked}】", flush=True)
            await asyncio.sleep(1.5)
            return True
        return False

    async def return_to_index(self):
        """返回课程首页"""
        self.processed_in_visit.clear()
        self.current_chapter_name = ""
        await self.eval(f"window.location.href = '{self.last_index_url}'")
        await asyncio.sleep(3.5)

    async def run(self):
        await self.connect("fifedu.com")
        print("="*60, flush=True)
        print("★ FIF 全自动断点漏刷补全系统已启动 ★", flush=True)
        print("="*60, flush=True)

        consecutive_stuck_cycles = 0

        while True:
            try:
                # 0. 优先处理弹窗
                if await self.handle_modals():
                    continue

                # 1. 检查当前页面 URL
                cur_url = await self.eval("window.location.href") or ""
                
                # ============================================================
                # 状态 0: 处于教学空间首页 (/istp-manage/work/home)
                # ============================================================
                if "/istp-manage/work/home" in cur_url:
                    print("\n[*] 当前处于【学习空间首页】，正在扫描未完成课程卡片...", flush=True)
                    course_res = await self.eval(r"""
                    (() => {
                        const cards = Array.from(document.querySelectorAll('.learningCourses .cardToLearn'));
                        return cards.map((c, idx) => {
                            const name = (c.querySelector('.courseName')?.innerText || '').trim();
                            const pctText = (c.querySelector('.SelfProgress .percent')?.innerText || '').trim();
                            const m = pctText.match(/(\d+)/);
                            const pct = m ? parseInt(m[1], 10) : 0;
                            return { idx, name, pct };
                        });
                    })()
                    """)
                    if not course_res:
                        await asyncio.sleep(2)
                        continue

                    pending = [c for c in course_res if c['pct'] < 100 and c['name'] not in self.completed_courses]
                    if not pending:
                        print("🎉 学习空间内所有可见课程均已完成！", flush=True)
                        break

                    target_course = pending[0]
                    print(f"[>>>] 准备进入课程: 【{target_course['name']}】 (当前进度: {target_course['pct']}%)...", flush=True)
                    await self.eval(f"""
                    (() => {{
                        const origOpen = window.open;
                        window.open = function(url) {{
                            if (url && url.includes('/istp-learning-center/')) {{
                                window.location.href = url;
                                return null;
                            }}
                            return origOpen.apply(this, arguments);
                        }};
                        const cards = Array.from(document.querySelectorAll('.learningCourses .cardToLearn'));
                        if (cards.length > {target_course['idx']}) cards[{target_course['idx']}].click();
                    }})()
                    """)
                    await asyncio.sleep(4)
                    continue

                # ============================================================
                # 状态 A: 处于课程首页 (/istp-learning-center/index)
                # ============================================================
                if "/istp-learning-center/index" in cur_url:
                    self.last_index_url = cur_url
                    consecutive_stuck_cycles = 0
                    self.processed_in_visit.clear()
                    self.current_chapter_name = ""
                    print("\n[*] 当前处于【课程首页】，正在扫描所有章节与漏刷小节...", flush=True)
                    
                    # 确保展开所有树节点
                    await self.eval("""
                    (() => {
                        const icons = document.querySelectorAll('.el-tree-node__expand-icon:not(.is-leaf), .arrow-right, .icon-arrow');
                        icons.forEach(ic => {
                            if (!ic.classList.contains('expanded')) ic.click();
                        });
                    })()
                    """)
                    await asyncio.sleep(1.5)

                    # 扫描所有未打勾、资源数 > 0 的小节
                    scan_res = await self.eval("""
                    (() => {
                        const rows = Array.from(document.querySelectorAll('.aside-row'));
                        const todoList = [];
                        let totalProgress = '';
                        
                        const progEl = Array.from(document.querySelectorAll('*')).find(e => e.innerText && e.innerText.includes('学习总进度'));
                        if (progEl) totalProgress = progEl.innerText.trim().replace(/\\s+/g, ' ');

                        rows.forEach((r, idx) => {
                            const nameEl = r.querySelector('.tree-node-name');
                            const resEl = r.querySelector('.right-content');
                            if (!nameEl || !resEl) return;

                            const isLeaf = nameEl.classList.contains('no-child');
                            const resText = resEl.innerText.trim();
                            const m = resText.match(/(\\d+)\\s*个资源活动/);
                            const count = m ? parseInt(m[1]) : 0;
                            const hasCheck = !!r.querySelector('.icon-isfinished, [class*="isfinish"]');
                            const name = nameEl.innerText.split('\\n')[0].trim();
                            const isExam = /单元检测|单元测验|阶段检测/.test(name);

                            // 仅选择: 是小节(isLeaf), 有活动(count > 0), 未打勾(!hasCheck), 排除单元检测(!isExam)
                            if (isLeaf && count > 0 && !hasCheck && !isExam) {
                                todoList.push({
                                    idx,
                                    name,
                                    count
                                });
                            }
                        });

                        return {
                            totalProgress,
                            todoList
                        };
                    })()
                    """)

                    if not scan_res:
                        await asyncio.sleep(2)
                        continue

                    total_prog = scan_res.get('totalProgress', '')
                    raw_todo = scan_res.get('todoList', [])
                    
                    # 过滤掉用户指定跳过或已知平台异常的小节
                    todo_list = [t for t in raw_todo if not any(kw in t['name'] for kw in self.skip_sections)]
                    print(f"[进度信息] {total_prog} | 剩余未完成小节数: {len(todo_list)} (已跳过异常小节: {len(raw_todo) - len(todo_list)} 节)", flush=True)

                    if len(todo_list) == 0:
                        print("="*60, flush=True)
                        print(f"🎉 恭喜！除跳过异常小节外，所有待学课程已全部刷完！当前进度: {total_prog}", flush=True)
                        print("="*60, flush=True)
                        break

                    # 选取第一个待完成小节
                    target = todo_list[0]
                    target_name = target['name']
                    target_idx = target['idx']
                    target_count = target['count']
                    print(f"[>>>] 准备进入未完成小节: 【{target_name}】 ({target_count} 个资源活动)...", flush=True)

                    # 点击进入该小节
                    click_ok = await self.eval(f"""
                    (() => {{
                        const rows = Array.from(document.querySelectorAll('.aside-row'));
                        if (rows.length > {target_idx}) {{
                            const row = rows[{target_idx}];
                            const el = row.querySelector('.tree-node-name') || row;
                            el.click();
                            return true;
                        }}
                        return false;
                    }})()
                    """)

                    if click_ok:
                        print(f"[+] 已点击进入【{target_name}】，等待章节详情页加载...", flush=True)
                        await asyncio.sleep(4)
                    else:
                        print("[!] 点击节点失败，刷新重试...", flush=True)
                        await asyncio.sleep(2)
                    continue

                # ============================================================
                # 状态 B: 处于小节学习页 (/pattern/chapter)
                # ============================================================
                elif "/pattern/chapter" in cur_url:
                    # 获取当前小节信息和活动列表
                    ch_info = await self.eval(r"""
                    (() => {
                        const curChapter = document.querySelector('.current-chapter-name, .chapter-name-title')?.innerText.split('\n')[0].trim() || '';
                        const items = Array.from(document.querySelectorAll('.activity-list-item')).map((el, i) => ({
                            i,
                            name: el.querySelector('.activity-name')?.innerText.trim() || '',
                            status: Array.from(el.querySelectorAll('.activityStatus')).map(s => s.innerText.trim()).join(' | '),
                            isActive: el.classList.contains('is-active'),
                            isFinish: !!el.querySelector('.is-finish, [class*="isfinish"]')
                        }));
                        
                        const activeIdx = items.findIndex(x => x.isActive);
                        const curItem = activeIdx >= 0 ? items[activeIdx] : null;
                        const curName = curItem ? curItem.name : (document.querySelector('.chapter-activity-title, h3')?.innerText.trim() || '');
                        
                        const isExam = /单元检测|单元测验|阶段检测/i.test(curChapter) || /单元检测|单元测验|阶段检测/i.test(curName);
                        const video = document.querySelector('video');
                        
                        const isDoc = (/[.](doc|docx|pdf)($|\s)/i.test(curName)) || 
                                      (curItem && (curItem.status.includes('DOC') || curItem.status.includes('PDF') || curItem.status.includes('文档'))) || 
                                      !!document.querySelector('.docWrap, .wordWrap, .pdfWrap, [class*="pdf"], [class*="word"]');
                        
                        const hasPPT = (/[.](ppt|pptx)($|\s)/i.test(curName)) ||
                                       (curItem && curItem.status.includes('PPT')) ||
                                       !!document.querySelector('.officeweb365-iframe, .pptIframe, .pptContainer, .btnWrap');
                        
                        const pptPage = document.querySelector('.btnWrap .page')?.innerText.trim() || '';
                        
                        const hasVideo = !isDoc && !hasPPT && !!video;
                        
                        const hasExercise = !isExam && !isDoc && !hasPPT && !hasVideo && (
                            !!document.querySelector('.CloseBtn, [class*="exercise"]') || 
                            Array.from(document.querySelectorAll('button, .el-button')).some(b => b.innerText.includes('练习') || b.innerText.includes('选完了'))
                        );

                        return {
                            curChapter,
                            curName,
                            isExam,
                            isDoc,
                            hasPPT,
                            pptPage,
                            hasExercise,
                            items,
                            totalItems: items.length,
                            activeIdx: activeIdx >= 0 ? activeIdx : 0,
                            hasVideo: hasVideo,
                            videoInfo: video ? {
                                currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
                                duration: Number.isFinite(video.duration) ? video.duration : 0,
                                paused: video.paused,
                                ended: video.ended
                            } : null
                        };
                    })()
                    """)

                    if not ch_info:
                        await asyncio.sleep(2)
                        continue

                    cur_chapter = ch_info.get('curChapter', '')
                    cur_name = ch_info.get('curName', '')
                    total_items = ch_info.get('totalItems', 0)
                    active_idx = ch_info.get('activeIdx', 0)
                    items = ch_info.get('items', [])

                    # 若切换了小节，重置本次访问的处理集合
                    if cur_chapter != self.current_chapter_name:
                        self.current_chapter_name = cur_chapter
                        self.processed_in_visit.clear()

                    # 1. 检查是否在用户跳过黑名单
                    if any(kw in cur_chapter for kw in self.skip_sections):
                        print(f"[用户指定跳过] 章节【{cur_chapter}】在跳过列表中，返回首页切入下一小节...", flush=True)
                        await self.return_to_index()
                        continue

                    # 2. 单元检测跳过
                    if ch_info.get('isExam'):
                        print(f"[单元检测跳过] 【{cur_chapter} / {cur_name}】为单元检测，按规则跳过...", flush=True)
                        await self.return_to_index()
                        continue

                    # 3. 课件列表为空检查
                    if total_items == 0:
                        print(f"[*] 页面课件列表为空，返回首页刷新...", flush=True)
                        await self.return_to_index()
                        continue

                    # 4. 检查是否本节所有课件已打勾完成
                    all_finished = total_items > 0 and all(item.get('isFinish') for item in items)
                    if all_finished:
                        print(f"[★本节全部完成★] 【{cur_chapter}】所有 {total_items} 个课件均已打勾完成！返回首页切换下一节...", flush=True)
                        self.completed_sections.add(cur_chapter)
                        await self.return_to_index()
                        continue

                    # 5. 查找本节中尚未打勾的课件索引
                    unfinished_indices = [i for i, it in enumerate(items) if not it.get('isFinish')]
                    # 在未打勾课件中，过滤出本次访问尚未刷过的候选课件
                    candidates = [i for i in unfinished_indices if i not in self.processed_in_visit]

                    # 如果未打勾课件在本次访问中全部都已经执行过一遍了，但平台仍未打勾：
                    # 说明该小节存在平台端记录 Bug（例如 8-1-6 那样 PDF 滚到底却不勾）
                    if len(candidates) == 0 and len(unfinished_indices) > 0:
                        print(f"[!] 平台记录异常: 小节【{cur_chapter}】所有未打勾课件在本次访问中均已完成操作，但平台未更新打勾状态！", flush=True)
                        print(f"[!] 触发自动跳过保护，将小节【{cur_chapter}】加入跳过列表，避免死循环！", flush=True)
                        self.skip_sections.add(cur_chapter)
                        await self.return_to_index()
                        continue

                    # 6. 如果当前停留在已完成课件或已被处理过的课件上，主动切换至下一个候选课件
                    target_unfinished_idx = candidates[0]
                    if active_idx != target_unfinished_idx:
                        target_item_name = items[target_unfinished_idx]['name']
                        print(f"[定位未完成课件] 当前处于课件 [{active_idx+1}]，正在切换至待刷课件 [{target_unfinished_idx+1}/{total_items}]: 【{target_item_name}】...", flush=True)
                        await self.eval(f"""
                        (() => {{
                            const items = Array.from(document.querySelectorAll('.activity-list-item'));
                            if (items.length > {target_unfinished_idx}) {{
                                const el = items[{target_unfinished_idx}].querySelector('.activity-name') || items[{target_unfinished_idx}];
                                el.click();
                            }}
                        }})()
                        """)
                        await asyncio.sleep(3.5)
                        continue

                    print(f"--- [学习中] 章节: 【{cur_chapter}】 | 课件 [{active_idx+1}/{total_items}]: {cur_name} ---", flush=True)

                    # ========================================================
                    # 课件类型 1: 视频 (.mp4 / xgplayer / HTML5 Video)
                    # ========================================================
                    if ch_info.get('hasVideo'):
                        print(f"[视频] 正在处理视频课件: {cur_name}", flush=True)
                        # 确保开始播放
                        await self.eval("""
                        (() => {
                            const v = document.querySelector('video');
                            if (v) v.play().catch(e => {});
                            const playBtn = document.querySelector('.xgplayer-start, .xgplayer-play, .xg-icon-play');
                            if (playBtn) playBtn.click();
                            const p = document.querySelector('.xgplayer') || v;
                            if (p) p.focus();
                        })()
                        """)
                        await asyncio.sleep(1.0)

                        # 在独立的循环中快速快进至视频末尾，不受外部循环次数限制
                        ff_steps = 0
                        while ff_steps < 150:
                            v_status = await self.eval("""
                            (() => {
                                const v = document.querySelector('video');
                                if (!v) return null;
                                return {
                                    currentTime: Number.isFinite(v.currentTime) ? v.currentTime : 0.0,
                                    duration: Number.isFinite(v.duration) ? v.duration : 0.0,
                                    paused: v.paused,
                                    ended: v.ended
                                };
                            })()
                            """)
                            if not v_status:
                                break

                            cur = float(v_status.get('currentTime') or 0.0)
                            dur = float(v_status.get('duration') or 0.0)
                            ended = bool(v_status.get('ended', False))

                            if dur == 0.0:
                                await self.eval("document.querySelector('video')?.play()?.catch(e => {})")
                                await asyncio.sleep(1.0)
                                ff_steps += 1
                                continue

                            if ended or (dur > 0 and cur >= dur - 2.5):
                                print(f"[视频] 视频已播放至 100% ({cur:.1f}/{dur:.1f}s)！", flush=True)
                                break

                            if v_status.get('paused'):
                                await self.eval("document.querySelector('video')?.play()?.catch(e => {})")

                            pct = (cur / dur * 100) if dur > 0 else 0
                            if ff_steps % 5 == 0:
                                print(f"  [视频快进] 进度: {cur:.1f}/{dur:.1f}s ({pct:.1f}%)", flush=True)

                            # 连续发送 6 次快进按键
                            for _ in range(6):
                                await self.press_arrow_right()
                                await self.eval("""
                                (() => {
                                    const p = document.querySelector('.xgplayer') || document.querySelector('video') || window;
                                    p.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39, bubbles: true }));
                                })()
                                """)
                                await asyncio.sleep(0.04)

                            ff_steps += 1
                            await asyncio.sleep(0.15)

                        print(f"[+] 视频课件【{cur_name}】处理完成，等待 3 秒同步进度...", flush=True)
                        await asyncio.sleep(3)
                        self.processed_in_visit.add(active_idx)
                        continue

                    # ========================================================
                    # 课件类型 2: PPT (ow365.cn / iframe / 翻页)
                    # ========================================================
                    elif ch_info.get('hasPPT'):
                        print(f"[PPT] 正在处理课件 [{active_idx+1}/{total_items}]: {cur_name}", flush=True)
                        ppt_done = False
                        
                        # 尝试通过 ow365.cn iframe 目标直接翻页
                        targets = await self.send("Target.getTargets")
                        ow_target = next((t for t in targets.get("targetInfos", []) if "ow365.cn" in t.get("url", "")), None)
                        
                        if ow_target:
                            try:
                                attach_res = await self.send("Target.attachToTarget", {"targetId": ow_target["targetId"], "flatten": True})
                                ow_session = attach_res.get("sessionId")
                                
                                async def ow_eval(code):
                                    self.msg_id += 1
                                    mid = self.msg_id
                                    fut = asyncio.get_running_loop().create_future()
                                    self.pending_responses[mid] = fut
                                    await self.ws.send(json.dumps({
                                        "id": mid,
                                        "sessionId": ow_session,
                                        "method": "Runtime.evaluate",
                                        "params": {"expression": code, "returnByValue": True}
                                    }))
                                    try:
                                        res = await asyncio.wait_for(fut, timeout=5.0)
                                        return res.get("result", {}).get("result", {}).get("value")
                                    except Exception:
                                        if mid in self.pending_responses:
                                            del self.pending_responses[mid]
                                        return None

                                for step in range(1, 80):
                                    page_text = await ow_eval("""(() => {
                                        const all = Array.from(document.querySelectorAll('*'));
                                        return all.find(e => /^\\d+\\s*\\/\\s*\\d+$/.test(e.innerText?.trim()))?.innerText.trim();
                                    })()""")
                                    if page_text and "/" in page_text:
                                        parts = [p.strip() for p in page_text.split("/")]
                                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                            cur_p, tot_p = int(parts[0]), int(parts[1])
                                            if step % 5 == 1 or cur_p >= tot_p:
                                                print(f"  [PPT进度] 当前页码: {cur_p}/{tot_p}", flush=True)
                                            if cur_p >= tot_p:
                                                print(f"[+] PPT 已翻至末页 ({cur_p}/{tot_p})！", flush=True)
                                                ppt_done = True
                                                break
                                    await ow_eval("document.querySelector('#pageNext')?.click()")
                                    await asyncio.sleep(0.35)
                                    
                                await asyncio.sleep(2)
                                try:
                                    await self.send("Target.detachFromTarget", {"sessionId": ow_session})
                                except Exception:
                                    pass
                            except Exception as ow_e:
                                print(f"[!] ow365 会话处理异常: {ow_e}", flush=True)

                        # 如果未成功，降级通过点击按钮或键盘翻页
                        if not ppt_done:
                            center = await self.eval("""
                            (() => {
                                const iframe = document.querySelector('.officeweb365-iframe, .pptIframe, iframe');
                                if (!iframe) return null;
                                const r = iframe.getBoundingClientRect();
                                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                            })()
                            """)
                            if center:
                                await self.click_at(center['x'], center['y'])
                                await asyncio.sleep(0.1)
                                for _ in range(20):
                                    await self.press_page_down()
                                    await asyncio.sleep(0.3)
                            else:
                                await self.eval("""
                                (() => {
                                    const btn = document.querySelector('.btnWrap .arrow-right') || document.querySelector('.btnWrap .pptBtn:last-child');
                                    if (btn) btn.click();
                                })()
                                """)

                        print(f"[+] PPT 课件处理完成: {cur_name}", flush=True)
                        await asyncio.sleep(3)
                        self.processed_in_visit.add(active_idx)
                        continue

                    # ========================================================
                    # 课件类型 3: 文档与 PDF (.doc / .docx / .pdf)
                    # ========================================================
                    elif ch_info.get('isDoc'):
                        ext = "PDF" if ('.pdf' in cur_name.lower()) else "文档"
                        print(f"[{ext}] 正在拉动进度条到底部: {cur_name}", flush=True)
                        
                        center = await self.eval("""
                        (() => {
                            const f = document.querySelector('iframe[src*="pdf"], .pdfContainer, iframe, .pdfWrap, .docWrap, .main');
                            if (f) {
                                const r = f.getBoundingClientRect();
                                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                            }
                            return { x: window.innerWidth / 2, y: window.innerHeight / 2 };
                        })()
                        """)
                        if center:
                            await self.click_at(center['x'], center['y'])
                            await asyncio.sleep(0.1)

                        # 派发 PageDown 和 End 键滚动到底部
                        for _ in range(12):
                            await self.press_page_down()
                            await asyncio.sleep(0.08)
                            
                        await self.press_end()
                        await asyncio.sleep(0.2)

                        print(f"[+] [{ext}] 已完全拉到底部，静置 6 秒同步阅读记录...", flush=True)
                        await asyncio.sleep(6)
                        self.processed_in_visit.add(active_idx)
                        continue

                    # ========================================================
                    # 课件类型 4: 自适应练习
                    # ========================================================
                    elif ch_info.get('hasExercise'):
                        print(f"[自适应练习] 正在处理: {cur_name}", flush=True)

                        # 检查开始/继续练习
                        start_clicked = await self.eval("""
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
                        if start_clicked:
                            print("[+] 已点击【开始/继续练习】，等待题目加载...", flush=True)
                            await asyncio.sleep(2.5)

                        # 循环检查并点击交卷（最多重试 6 次，共等待 9 秒）
                        for _ in range(6):
                            submit_clicked = await self.eval("""
                            (() => {
                                const closeBtn = document.querySelector('.CloseBtn') || Array.from(document.querySelectorAll('button, .el-button, div, span')).find(e => e.innerText.trim() === '交卷');
                                if (closeBtn) {
                                    closeBtn.click();
                                    return true;
                                }
                                return false;
                            })()
                            """)
                            if submit_clicked:
                                print("[+] 已点击【交卷】", flush=True)
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
                                print("[+] 已确认交卷，等待结算...", flush=True)
                                await asyncio.sleep(3)
                                break
                            await asyncio.sleep(1.5)

                        self.processed_in_visit.add(active_idx)
                        continue

                    # ========================================================
                    # 课件类型 5: 未知或未完全加载
                    # ========================================================
                    else:
                        print(f"[*] 课件正在加载中: {cur_name}，等待 2 秒...", flush=True)
                        await asyncio.sleep(2)
                        consecutive_stuck_cycles += 1
                        if consecutive_stuck_cycles > 10:
                            print("[!] 长时间未响应，返回首页重新对齐...", flush=True)
                            consecutive_stuck_cycles = 0
                            await self.return_to_index()
                        continue

                # ============================================================
                # 状态 C: 其他未知 URL，返回首页
                # ============================================================
                else:
                    print(f"[*] 当前 URL 为其他页面 ({cur_url[:50]}...)，正在重定向回课程首页...", flush=True)
                    await self.return_to_index()
                    await asyncio.sleep(3)

            except Exception as e:
                print(f"[!] 运行异常: {e}", flush=True)
                await asyncio.sleep(3)

if __name__ == "__main__":
    app = FIFMasterAutoStudy()
    asyncio.run(app.run())
