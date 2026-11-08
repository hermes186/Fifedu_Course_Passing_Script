// ==UserScript==
// @name         FIF智慧教学平台全自动刷课助手 (icourse.fifedu.com)
// @name:zh-CN   FIF智慧教学平台全自动刷课助手 (icourse.fifedu.com)
// @name:en      FIF Smart Teaching Platform Auto Study Helper
// @namespace    https://github.com/fifedu-auto-study/userscript
// @version      1.2.0
// @description  适用于 FIF 智慧教学平台 (icourse.fifedu.com) 全站课程自动学习：支持学习空间首页课程识别、全自动巡航章节、视频自动倍速/秒过（含损坏视频容错）、PPT自动翻页完成、Word/PDF文档自动置底完成、自适应练习自动交卷、自动跳过单元检测及防死循环保护。
// @description:zh-CN 适用于 FIF 智慧教学平台 (icourse.fifedu.com) 全站课程自动学习：支持学习空间首页课程识别、全自动巡航章节、视频自动倍速/秒过（含损坏视频容错）、PPT自动翻页完成、Word/PDF文档自动置底完成、自适应练习自动交卷、自动跳过单元检测及防死循环保护。
// @description:en Automated course study helper for FIF Smart Teaching Platform (icourse.fifedu.com). Supports dashboard course detection, video, PPT, PDF/Word, and adaptive practice auto-completion.
// @author       Antigravity
// @match        https://icourse.fifedu.com/*
// @match        https://resc.fifedu.com/iplat-resc/pdfv-resource/web/viewer.html*
// @match        https://*.ow365.cn/*
// @icon         https://icourse.fifedu.com/favicon.ico
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_addStyle
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @run-at       document-idle
// @license      MIT
// ==/UserScript==

(function () {
    'use strict';

    const pageWindow = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
    const host = location.hostname;

    // =========================================================================
    // 1. 子框架辅助模块：跨域 PDF.js 阅读器 & ow365 PPT 预览器自动置底/翻页
    // =========================================================================
    if (host.includes('resc.fifedu.com')) {
        // PDF.js / Word 预览器子页面自动翻至末页并通知父窗口
        const runPdfHelper = () => {
            const interval = setInterval(() => {
                try {
                    const app = pageWindow.PDFViewerApplication;
                    if (app && app.pagesCount && app.pagesCount > 0) {
                        const total = app.pagesCount;
                        if (app.page < total) {
                            app.page = total;
                        }
                        const lastBtn = document.querySelector('#lastPage');
                        if (lastBtn) lastBtn.click();

                        const vc = document.querySelector('#viewerContainer');
                        if (vc) {
                            vc.scrollTop = vc.scrollHeight;
                            vc.dispatchEvent(new Event('scroll'));
                        }
                        pageWindow.parent.postMessage({
                            eventName: 'ready',
                            totalPage: total,
                            loading: false
                        }, '*');
                        pageWindow.parent.postMessage({
                            eventName: 'currentPage',
                            currentPage: total,
                            totalPage: total
                        }, '*');
                    }
                } catch (e) {
                    // ignore cross-frame errors
                }
            }, 2000);
            setTimeout(() => clearInterval(interval), 120000);
        };
        runPdfHelper();
        return;
    }

    if (host.includes('ow365.cn')) {
        // ow365 PPT 跨域预览器自动翻页至末页
        const runOw365Helper = () => {
            const interval = setInterval(() => {
                try {
                    const allEls = Array.from(document.querySelectorAll('*'));
                    const pageEl = allEls.find(el => /^\d+\s*\/\s*\d+$/.test((el.innerText || '').trim()));
                    if (pageEl) {
                        const parts = pageEl.innerText.trim().split('/').map(s => parseInt(s.trim(), 10));
                        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
                            const [cur, total] = parts;
                            pageWindow.parent.postMessage({
                                currentPageNum: cur,
                                totalPageNum: total,
                                data: { currentPageNum: cur, totalPageNum: total }
                            }, '*');
                            if (cur >= total) {
                                clearInterval(interval);
                                return;
                            }
                        }
                    }
                    const nextBtn = document.querySelector('#pageNext, .pageNext, [title*="下一页"], [title*="下一张"]');
                    if (nextBtn) nextBtn.click();
                } catch (e) {
                    // ignore
                }
            }, 450);
            setTimeout(() => clearInterval(interval), 120000);
        };
        runOw365Helper();
        return;
    }

    // 仅在顶层窗口运行主控面板与状态机
    if ( window.top !== window.self ) return;

    // =========================================================================
    // 2. 存储与全局配置管理 (兼容无 GM_* 环境的降级存储)
    // =========================================================================
    const Storage = {
        get(key, defaultVal) {
            try {
                if (typeof GM_getValue === 'function') {
                    const val = GM_getValue(key, undefined);
                    return val !== undefined ? val : defaultVal;
                }
                const raw = localStorage.getItem('fif_helper_' + key);
                return raw !== null ? JSON.parse(raw) : defaultVal;
            } catch (e) {
                return defaultVal;
            }
        },
        set(key, val) {
            try {
                if (typeof GM_setValue === 'function') {
                    GM_setValue(key, val);
                }
                localStorage.setItem('fif_helper_' + key, JSON.stringify(val));
            } catch (e) {
                // ignore
            }
        }
    };

    const DEFAULT_CONFIG = {
        running: false,            // 是否开启自动刷课
        fastMode: true,            // 极速完成模式 (结合 Vue 进度上报与快进)
        videoRate: 4.0,            // 视频播放倍速 (1 ~ 16)
        autoExercise: true,        // 自动完成自适应练习
        skipExams: true,           // 自动跳过单元检测/测验
        autoNextCourse: false,     // 课程刷完后是否自动返回首页切换下一门课
        minimized: false           // 面板是否最小化
    };

    const state = {
        config: {
            running: Storage.get('running', DEFAULT_CONFIG.running),
            fastMode: Storage.get('fastMode', DEFAULT_CONFIG.fastMode),
            videoRate: Number(Storage.get('videoRate', DEFAULT_CONFIG.videoRate)) || 4.0,
            autoExercise: Storage.get('autoExercise', DEFAULT_CONFIG.autoExercise),
            skipExams: Storage.get('skipExams', DEFAULT_CONFIG.skipExams),
            autoNextCourse: Storage.get('autoNextCourse', DEFAULT_CONFIG.autoNextCourse),
            minimized: Storage.get('minimized', DEFAULT_CONFIG.minimized)
        },
        skipSections: new Set(Storage.get('skipSections', [])),
        completedCourses: new Set(Storage.get('completedCourses', [])),
        currentChapterKey: '',
        processedInVisit: new Set(),
        lastIndexUrl: Storage.get('lastIndexUrl', ''),
        busy: false,
        stuckCounter: 0,
        statusText: '就绪，点击「开始刷课」启动自动化',
        logs: []
    };

    function saveConfig() {
        Object.keys(DEFAULT_CONFIG).forEach(k => Storage.set(k, state.config[k]));
    }

    function saveSkipSections() {
        Storage.set('skipSections', Array.from(state.skipSections));
    }

    function saveCompletedCourses() {
        Storage.set('completedCourses', Array.from(state.completedCourses));
    }

    function log(msg, level = 'info') {
        const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        const line = `[${time}] ${msg}`;
        console.log(`[FIF助手] ${line}`);
        state.logs.unshift({ time, msg, level });
        if (state.logs.length > 60) state.logs.pop();
        state.statusText = msg;
        updatePanelUI();
    }

    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    // =========================================================================
    // 3. Vue 3 实例与底层组件探测工具
    // =========================================================================
    function getVueApp() {
        const root = document.querySelector('#app, #microApp');
        return root ? root.__vue_app__ : null;
    }

    function getVueRouter() {
        const app = getVueApp();
        return app?.config?.globalProperties?.$router || null;
    }

    function findVueComponent(selector, predicate) {
        const els = Array.from(document.querySelectorAll(selector));
        const visited = new Set();
        for (const el of els) {
            let curEl = el;
            while (curEl) {
                let comp = curEl.__vueParentComponent;
                while (comp && !visited.has(comp)) {
                    visited.add(comp);
                    if (!predicate || predicate(comp)) {
                        return comp;
                    }
                    comp = comp.parent;
                }
                curEl = curEl.parentElement;
            }
        }
        return null;
    }

    function hasEmitOption(comp, eventName) {
        const opts = comp?.emitsOptions || comp?.type?.emits;
        if (!opts) return false;
        if (Array.isArray(opts)) return opts.includes(eventName);
        if (typeof opts === 'object') return eventName in opts;
        return false;
    }

    /**
     * 通过 Vue 组件直接上报 100% 进度 (解决跨域 PDF / 单页文档 / 损坏视频无法打勾问题)
     */
    function triggerVueStudyProcess({ total = 100, end = 100, type = '275003' } = {}) {
        try {
            let triggered = false;

            // 方式 1: 直接调用 child preview 组件 (Pdf / Ppt / AudioVideo 等) 的 emit('studyProcess', ...)
            const childComp = findVueComponent('.wrapBox, .videoWrap, .pdfContainer, .pptWrap, .previewContainer', c => {
                return hasEmitOption(c, 'studyProcess') && !(c.props && c.props.resourceInfo && c.subTree?.el?.classList?.contains('previewContainer'));
            });
            if (childComp && typeof childComp.emit === 'function') {
                childComp.emit('studyProcess', { total, end, type });
                triggered = true;
            }

            // 方式 2: 通过 .previewContainer 向上 emit('studyProcess', payload)
            const previewComp = findVueComponent('.previewContainer', c => {
                return c.props && c.props.resourceInfo && typeof c.emit === 'function';
            });
            if (previewComp && previewComp.props?.resourceInfo) {
                const info = previewComp.props.resourceInfo;
                const courseId = new URLSearchParams(location.search).get('courseId') ||
                                 sessionStorage.getItem('courseId') || '';
                const payload = {
                    courseId: String(courseId).replace(/^"|"$/g, ''),
                    chapterId: info.chapterId,
                    activityId: info.activityId,
                    activityType: info.activityType || 1,
                    resourceId: info.resourceId,
                    resourceName: info.activityName,
                    resourceType: type,
                    videoTotalTime: total,
                    videoStudyTime: end
                };
                previewComp.emit('studyProcess', payload);
                triggered = true;
            }

            // 方式 3: 直接调用 .activity-list-warp 暴露的 upDateStudyProgress
            const actListComp = findVueComponent('.activity-list-warp, .chapter-info-right', c => {
                return c.exposed && typeof c.exposed.upDateStudyProgress === 'function';
            });
            if (actListComp && actListComp.exposed) {
                const list = actListComp.exposed.resoureList?.value || actListComp.exposed.resoureList || [];
                const activeItem = Array.isArray(list)
                    ? list.find(item => item.learnStatus !== 271003) || list[0]
                    : null;
                if (activeItem) {
                    actListComp.exposed.upDateStudyProgress({
                        activityId: activeItem.activityId,
                        resourceType: type,
                        videoTotalTime: total,
                        videoStudyTime: end
                    });
                    triggered = true;
                }
            }
            return triggered;
        } catch (e) {
            console.warn('[FIF助手] Vue 进度同步调用异常:', e);
        }
        return false;
    }

    // =========================================================================
    // 4. 通用弹窗与模态框处理
    // =========================================================================
    async function handleModals() {
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return el.offsetWidth > 0 && el.offsetHeight > 0 &&
                   style.display !== 'none' && style.visibility !== 'hidden';
        };
        const btns = Array.from(document.querySelectorAll(
            '.el-message-box__btns button, .el-dialog button, .elMessageBox button, [class*="dialog"] button'
        )).filter(isVisible);

        const targetBtn = btns.find(b => {
            const t = (b.innerText || '').trim();
            return t === '确定' || t === '确认' || t === '我知道了' || t === '仍要学习' || t === '下一步';
        });

        if (targetBtn) {
            const text = targetBtn.innerText.trim();
            targetBtn.click();
            log(`自动点击弹窗按钮：【${text}】`, 'success');
            await sleep(1200);
            return true;
        }
        return false;
    }

    // =========================================================================
    // 5. 页面 A: 教学/学习空间首页 (/istp-manage/work/home)
    // =========================================================================
    function decorateWorkHomeCards() {
        const cards = Array.from(document.querySelectorAll('.learningCourses .cardToLearn'));
        cards.forEach((card) => {
            if (card.querySelector('.fif-helper-card-btn')) return;
            const nameEl = card.querySelector('.courseName');
            const courseName = nameEl ? nameEl.innerText.trim() : '未命名课程';

            const btn = document.createElement('button');
            btn.className = 'fif-helper-card-btn';
            btn.innerHTML = '🚀 自动刷此课';
            btn.title = `启动全自动刷课：${courseName}`;
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                state.config.running = true;
                saveConfig();
                log(`准备进入课程：【${courseName}】`, 'info');
                enterCourseCardInSameTab(card);
            });

            const infoBox = card.querySelector('.courseInfo') || card;
            infoBox.style.position = 'relative';
            infoBox.appendChild(btn);
        });
    }

    function enterCourseCardInSameTab(cardEl) {
        // 拦截 window.open 使其在当前标签页或新标签页平滑跳转并保持运行状态
        const origOpen = pageWindow.open;
        pageWindow.open = function (url) {
            if (url && typeof url === 'string' && url.includes('/istp-learning-center/')) {
                Storage.set('lastIndexUrl', url);
                location.href = url;
                return null;
            }
            return origOpen.apply(this, arguments);
        };
        try {
            cardEl.click();
        } finally {
            setTimeout(() => {
                pageWindow.open = origOpen;
            }, 1500);
        }
    }

    async function handleWorkHomePage() {
        decorateWorkHomeCards();
        if (!state.config.running) return;

        const cards = Array.from(document.querySelectorAll('.learningCourses .cardToLearn'));
        if (cards.length === 0) {
            log('正在等待「我学的课」列表加载...', 'info');
            return;
        }

        // 查找尚未 100% 完成且不在已完成列表中的课程卡片
        for (const card of cards) {
            const name = (card.querySelector('.courseName')?.innerText || '').trim();
            const pctText = (card.querySelector('.SelfProgress .percent')?.innerText || '').trim();
            const pctMatch = pctText.match(/(\d+)/);
            const pct = pctMatch ? parseInt(pctMatch[1], 10) : null;

            if (name && state.completedCourses.has(name)) continue;
            if (pct !== null && pct >= 100) {
                state.completedCourses.add(name);
                saveCompletedCourses();
                continue;
            }

            if (state.config.autoNextCourse) {
                log(`自动进入待完成课程：【${name || '课程'}】`, 'info');
                enterCourseCardInSameTab(card);
                await sleep(3000);
                return;
            }
        }

        // 若当前页课程全部完成且存在「展开」更多按钮，自动展开下一页课程
        const expandBtn = document.querySelector('.learningCourses .expand .expand-btn');
        if (state.config.autoNextCourse && expandBtn && expandBtn.offsetWidth > 0 && (expandBtn.innerText || '').includes('展开')) {
            log('正在展开更多课程列表...', 'info');
            expandBtn.click();
            await sleep(2000);
            return;
        }

        log('请在课程卡片上点击「🚀 自动刷此课」，或开启「多课程连刷」自动进入课程。', 'info');
    }

    // =========================================================================
    // 6. 页面 B: 课程章节目录页 (/istp-learning-center/index)
    // =========================================================================
    function isExamTitle(title) {
        return /单元检测|单元测验|阶段检测|阶段测验|期中检测|期末检测|期末考试/i.test(title || '');
    }

    async function handleCourseIndexPage() {
        // 记录当前课程目录页 URL，便于从章节页精准返回
        if (location.href.includes('/istp-learning-center/index')) {
            state.lastIndexUrl = location.href;
            Storage.set('lastIndexUrl', location.href);
        }

        if (!state.config.running) return;

        state.currentChapterKey = '';
        state.processedInVisit.clear();

        // 1. 展开所有折叠的章节树节点
        const expandIcons = Array.from(document.querySelectorAll(
            '.index-tree-node .left-arrow:not(.is-open), .el-tree-node__expand-icon:not(.is-leaf):not(.expanded)'
        ));
        if (expandIcons.length > 0) {
            expandIcons.forEach(ic => ic.click());
            await sleep(1000);
        }

        // 2. 扫描所有小节行 (.aside-row)
        const rows = Array.from(document.querySelectorAll('.aside-row'));
        if (rows.length === 0) {
            log('正在等待课程章节树加载...', 'info');
            return;
        }

        const progEl = document.querySelector('.study-progress-top-left') ||
                       Array.from(document.querySelectorAll('*')).find(e => e.innerText && e.innerText.includes('学习总进度'));
        const totalProgress = progEl ? progEl.innerText.trim().replace(/\s+/g, ' ') : '';

        const todoList = [];
        rows.forEach((row, idx) => {
            const nameEl = row.querySelector('.tree-node-name');
            const resEl = row.querySelector('.right-content');
            if (!nameEl || !resEl) return;

            const isLeaf = nameEl.classList.contains('no-child') || !row.querySelector('.left-arrow');
            const resText = resEl.innerText.trim();
            const m = resText.match(/(\d+)\s*个(资源|学习)活动/);
            const count = m ? parseInt(m[1], 10) : 0;

            const hasCheck = !!row.querySelector('.icon-isfinished, [class*="isfinish"]');
            const isLocked = !!row.querySelector('.icon-locked, .icon-becomedue, [class*="locked"]');
            const name = nameEl.innerText.split('\n')[0].trim();
            const isExam = isExamTitle(name);

            if (isLeaf && count > 0 && !hasCheck && !isLocked) {
                if (state.config.skipExams && isExam) return;
                if (state.skipSections.has(name)) return;
                todoList.push({ idx, name, count, row });
            }
        });

        if (todoList.length === 0) {
            const courseTitle = (document.querySelector('.course-name-warp .name')?.innerText || '').trim();
            if (courseTitle) {
                state.completedCourses.add(courseTitle);
                saveCompletedCourses();
            }
            log(`🎉 当前课程可学小节已全部刷完！(${totalProgress || '100%'})`, 'success');

            if (state.config.autoNextCourse) {
                log('3 秒后自动返回「学习空间」切换下一门未完成课程...', 'info');
                await sleep(3000);
                location.href = 'https://icourse.fifedu.com/istp-manage/work/home';
            } else {
                state.config.running = false;
                saveConfig();
                updatePanelUI();
            }
            return;
        }

        const target = todoList[0];
        log(`准备进入小节：【${target.name}】(剩余 ${todoList.length} 节未完成)`, 'info');
        const clickTarget = target.row.querySelector('.tree-node-name') || target.row;
        clickTarget.click();
        await sleep(3000);
    }

    // =========================================================================
    // 7. 页面 C: 章节学习详情页 (/istp-learning-center/pattern/chapter)
    // =========================================================================
    async function returnToCourseIndex() {
        state.processedInVisit.clear();
        state.currentChapterKey = '';

        // 优先点击页面左上角返回按钮 (保留 Vue Router 状态)
        const backBtn = document.querySelector('.study-header .return-icon, .page-return-p .return-icon, .back-btn');
        if (backBtn) {
            backBtn.click();
            await sleep(2500);
            if (location.pathname.includes('/istp-learning-center/index')) return;
        }

        // 其次使用 Vue Router 导航回 /index
        const router = getVueRouter();
        const params = new URLSearchParams(location.search);
        const courseId = params.get('courseId') || (sessionStorage.getItem('courseId') || '').replace(/^"|"$/g, '');
        const classId = params.get('classId') || (sessionStorage.getItem('classId') || '').replace(/^"|"$/g, '');
        const termId = params.get('termId') || (sessionStorage.getItem('termId') || '').replace(/^"|"$/g, '');

        if (router && courseId) {
            router.push({
                path: '/index',
                query: { courseId, classId, termId }
            });
            await sleep(2500);
            return;
        }

        if (state.lastIndexUrl) {
            location.href = state.lastIndexUrl;
        } else {
            location.href = `https://icourse.fifedu.com/istp-learning-center/index?courseId=${courseId}&classId=${classId}&termId=${termId}`;
        }
        await sleep(3000);
    }

    function inspectCurrentChapterDOM() {
        const curChapter = (document.querySelector('.current-chapter-name, .chapter-name-title')?.innerText || '')
            .split('\n')[0].trim();

        const itemEls = Array.from(document.querySelectorAll('.activity-list-item'));
        const items = itemEls.map((el, i) => {
            const nameEl = el.querySelector('.activity-name');
            const name = (nameEl?.innerText || '').replace(/选学/g, '').trim();
            const statusText = (el.querySelector('.status-flex')?.innerText || el.innerText || '')
                .replace(/\s+/g, ' ').trim();
            const isActive = el.classList.contains('is-active') || !!el.querySelector('.is-current');
            const isFinish = !!el.querySelector('.is-finish, .is-finished, [class*="isfinish"]') ||
                             statusText.includes('已完成') || statusText.includes('100%');
            return { i, name, statusText, isActive, isFinish, el };
        });

        const activeIdx = items.findIndex(x => x.isActive);
        const curItem = activeIdx >= 0 ? items[activeIdx] : items[0] || null;
        const curName = curItem ? curItem.name : (document.querySelector('.chapter-activity-title, h3')?.innerText || '').trim();
        const statusStr = curItem ? curItem.statusText : '';

        const isExam = isExamTitle(curChapter) || isExamTitle(curName);
        const video = document.querySelector('video, audio');

        const isPPT = /\.(ppt|pptx)($|\s)/i.test(curName) ||
                      statusStr.includes('PPT') ||
                      !!document.querySelector('.pptWrap, .pptContainer, .officeweb365-iframe, .pptIframe');

        const isDoc = !isPPT && (
            /\.(doc|docx|pdf|txt|xls|xlsx)($|\s)/i.test(curName) ||
            /DOC|PDF|Word|文档|表格/i.test(statusStr) ||
            !!document.querySelector('.pdfContainer, .docWrap, .wordWrap, .pdfWrap, iframe[src*="viewer.html"]')
        );

        const isVideo = !isDoc && !isPPT && (!!video || /视频|音频|\.(mp4|webm|mp3|wav)/i.test(curName + ' ' + statusStr));

        const isExercise = !isExam && !isDoc && !isPPT && !isVideo && (
            !!document.querySelector('.SubjectLib, .SubjectCover, .SubjectLayout, .CloseBtn') ||
            /练习|自适应/i.test(statusStr) ||
            Array.from(document.querySelectorAll('button, .el-button')).some(b => {
                const t = (b.innerText || '').trim();
                return t.includes('开始练习') || t.includes('继续练习') || t.includes('选完了');
            })
        );

        const isOtherInstant = !isExam && !isDoc && !isPPT && !isVideo && !isExercise &&
                               !!document.querySelector('.previewContainer, .homework_box');

        return {
            curChapter,
            curName,
            items,
            totalItems: items.length,
            activeIdx: activeIdx >= 0 ? activeIdx : 0,
            isExam,
            isVideo,
            isPPT,
            isDoc,
            isExercise,
            isOtherInstant
        };
    }

    /**
     * 处理视频/音频课件
     */
    async function processVideoActivity(curName) {
        log(`正在处理音视频课件：【${curName}】`, 'info');
        const media = document.querySelector('video, audio');

        if (media) {
            try {
                media.muted = true;
                media.playbackRate = Math.min(Math.max(state.config.videoRate || 4.0, 1.0), 16.0);
                media.play().catch(() => {});
            } catch (e) {}
            const playBtn = document.querySelector('.xgplayer-start, .xgplayer-play, .xg-icon-play');
            if (playBtn) playBtn.click();
        }

        // 等待元数据加载 (最多 8 秒)，同时检测格式错误
        let metadataLoaded = false;
        let hasMediaError = false;
        for (let i = 0; i < 16; i++) {
            if (!state.config.running) return;
            const v = document.querySelector('video, audio');
            const errEl = document.querySelector('.xgplayer-error, .xgplayer-error-text');
            const errVisible = errEl && errEl.offsetWidth > 0 && (errEl.innerText || '').includes('不支持');

            if ((v && v.error) || errVisible) {
                hasMediaError = true;
                break;
            }
            if (v && Number.isFinite(v.duration) && v.duration > 0) {
                metadataLoaded = true;
                break;
            }
            await sleep(500);
        }

        // 情况 1: 视频源损坏或开启了极速模式 -> 直接通过 Vue 进度接口上报 100%
        if (hasMediaError || !metadataLoaded || state.config.fastMode) {
            const v = document.querySelector('video, audio');
            const totalDur = (v && Number.isFinite(v.duration) && v.duration > 0) ? Math.floor(v.duration) : 300;
            if (hasMediaError) {
                log(`检测到平台视频源异常，启用底层进度直报修复：【${curName}】`, 'warn');
            } else {
                log(`正在同步视频完成进度 (时长: ${totalDur}s)...`, 'info');
            }
            triggerVueStudyProcess({ total: totalDur, end: totalDur, type: '275002' });
            if (v && Number.isFinite(v.duration) && v.duration > 2) {
                try {
                    v.currentTime = Math.max(0, v.duration - 1);
                    v.dispatchEvent(new Event('seeked'));
                    v.dispatchEvent(new Event('ended'));
                } catch (e) {}
            }
            await sleep(3000);
            return;
        }

        // 情况 2: 常规倍速 + 步进快进模式
        let steps = 0;
        while (steps < 180 && state.config.running) {
            const v = document.querySelector('video, audio');
            if (!v) break;
            const dur = Number.isFinite(v.duration) ? v.duration : 0;
            const cur = Number.isFinite(v.currentTime) ? v.currentTime : 0;

            if (v.ended || (dur > 0 && cur >= dur - 2)) {
                log(`视频播放完成 (${Math.round(cur)}/${Math.round(dur)}s)`, 'success');
                break;
            }
            if (v.paused) {
                v.muted = true;
                v.play().catch(() => {});
            }
            v.playbackRate = Math.min(Math.max(state.config.videoRate || 4.0, 1.0), 16.0);
            try {
                v.currentTime = Math.min(dur - 0.5, cur + 15);
            } catch (e) {}

            const player = document.querySelector('.xgplayer') || v;
            player.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'ArrowRight', code: 'ArrowRight', keyCode: 39, bubbles: true
            }));

            if (steps % 6 === 0 && dur > 0) {
                log(`视频进度：${Math.round((cur / dur) * 100)}% (${Math.round(cur)}/${Math.round(dur)}s)`);
            }
            steps++;
            await sleep(400);
        }

        const v = document.querySelector('video, audio');
        const finalDur = (v && Number.isFinite(v.duration) && v.duration > 0) ? Math.floor(v.duration) : 300;
        triggerVueStudyProcess({ total: finalDur, end: finalDur, type: '275002' });
        await sleep(2500);
    }

    /**
     * 处理 PPT 课件
     */
    async function processPPTActivity(curName) {
        log(`正在处理 PPT 课件：【${curName}】`, 'info');
        await sleep(1500);

        // 获取总页数 (如果存在页码显示)
        const totalEl = document.querySelector('.pptContainer .page .total, .btnWrap .page');
        let totalPages = 30;
        if (totalEl) {
            const m = (totalEl.innerText || '').match(/(\d+)\s*$/);
            if (m) totalPages = Math.max(parseInt(m[1], 10), 2);
        }

        // 1. 向当前窗口派发 PreviewPpt 监听的 postMessage 事件 (先发第 1 页解锁首屏标记，再发末页)
        pageWindow.postMessage({
            currentPageNum: 1,
            totalPageNum: totalPages,
            data: { currentPageNum: 1, totalPageNum: totalPages }
        }, '*');
        await sleep(300);
        pageWindow.postMessage({
            currentPageNum: totalPages,
            totalPageNum: totalPages,
            data: { currentPageNum: totalPages, totalPageNum: totalPages }
        }, '*');

        // 2. 点击页面上的下一页按钮 (若存在)
        const nextBtn = document.querySelector('.pptContainer .toggle .pptBtn:last-child, .btnWrap .arrow-right, .btnWrap .pptBtn:last-child');
        if (nextBtn) {
            for (let i = 0; i < Math.min(totalPages, 25); i++) {
                nextBtn.click();
                await sleep(80);
            }
        }

        // 3. 调用 Vue 进度上报接口保底
        triggerVueStudyProcess({ total: totalPages, end: totalPages, type: '275003' });
        log(`PPT 课件已完成：【${curName}】`, 'success');
        await sleep(2500);
    }

    /**
     * 处理 Word / PDF / TXT / Excel 文档课件
     */
    async function processDocActivity(curName) {
        log(`正在处理文档/PDF课件：【${curName}】`, 'info');
        await sleep(1500);

        // 1. 向 PDF.js iframe 发送跳转末页消息
        const pdfIframe = document.querySelector('.pdfContainer iframe, iframe[src*="viewer.html"]');
        if (pdfIframe && pdfIframe.contentWindow) {
            for (const p of [5, 15, 30, 60, 100]) {
                pdfIframe.contentWindow.postMessage({ pageNum: p }, '*');
            }
        }

        // 2. 滚动页面内部所有可滚动容器到底部
        const scrollables = Array.from(document.querySelectorAll('.docWrap, .wordWrap, .pdfWrap, .wrapBox, .main-warp .el-scrollbar__wrap'));
        scrollables.forEach(el => {
            if (el.scrollHeight > el.clientHeight) {
                el.scrollTop = el.scrollHeight;
                el.dispatchEvent(new Event('scroll'));
            }
        });

        // 3. 直接触发 Vue 组件 100% 阅读完成上报 (彻底解决单页 PDF 不打勾 Bug)
        triggerVueStudyProcess({ total: 10, end: 10, type: '275003' });
        log(`文档已置底并同步完成状态：【${curName}】`, 'success');
        await sleep(3500);
    }

    /**
     * 处理自适应练习课件
     */
    async function processExerciseActivity(curName) {
        if (!state.config.autoExercise) {
            log(`已跳过自适应练习（配置为不自动作答）：【${curName}】`, 'warn');
            await sleep(1500);
            return;
        }

        log(`正在处理自适应练习：【${curName}】`, 'info');

        // 1. 点击开始练习 / 继续练习
        const startBtn = Array.from(document.querySelectorAll('.SubjectCover button, button, .el-button')).find(b => {
            const t = (b.innerText || '').trim();
            return t === '开始练习' || t === '继续练习';
        });
        if (startBtn) {
            startBtn.click();
            log('已点击【开始/继续练习】，等待题目加载...');
            await sleep(2500);
        }

        // 处理可能弹出的“仍要学习”确认框
        await handleModals();

        // 2. 循环查找并点击「交卷」按钮
        for (let attempt = 0; attempt < 8; attempt++) {
            const closeBtn = document.querySelector('.CloseBtn') ||
                Array.from(document.querySelectorAll('button, .el-button, div, span')).find(el => (el.innerText || '').trim() === '交卷');
            if (closeBtn) {
                closeBtn.click();
                log('已点击【交卷】，等待确认弹窗...');
                await sleep(1200);
                await handleModals();
                log(`自适应练习已完成交卷：【${curName}】`, 'success');
                await sleep(2500);
                return;
            }
            await sleep(1000);
        }
    }

    /**
     * 章节学习页主状态机
     */
    async function handleChapterStudyPage() {
        if (!state.config.running) return;

        // 等待加载遮罩消失
        const loadingEl = document.querySelector('.isLoading');
        if (loadingEl && loadingEl.offsetWidth > 0) {
            await sleep(1000);
            return;
        }

        const ch = inspectCurrentChapterDOM();
        if (!ch.curChapter && ch.totalItems === 0) {
            state.stuckCounter++;
            if (state.stuckCounter > 8) {
                state.stuckCounter = 0;
                await returnToCourseIndex();
            }
            return;
        }
        state.stuckCounter = 0;

        // 切换小节时清空本轮已访问集合
        const chapterKey = `${location.search}__${ch.curChapter}`;
        if (chapterKey !== state.currentChapterKey) {
            state.currentChapterKey = chapterKey;
            state.processedInVisit.clear();
        }

        // 1. 检查跳过名单与单元检测
        if (ch.curChapter && state.skipSections.has(ch.curChapter)) {
            log(`小节【${ch.curChapter}】在异常跳过列表中，返回目录...`, 'warn');
            await returnToCourseIndex();
            return;
        }
        if (state.config.skipExams && ch.isExam) {
            log(`检测到单元检测【${ch.curChapter || ch.curName}】，自动跳过...`, 'warn');
            if (ch.curChapter) {
                state.skipSections.add(ch.curChapter);
                saveSkipSections();
            }
            await returnToCourseIndex();
            return;
        }
        if (ch.totalItems === 0) {
            log('当前小节无活动列表，返回课程目录...', 'warn');
            await returnToCourseIndex();
            return;
        }

        // 2. 检查是否全部课件均已完成
        const allFinished = ch.items.every(it => it.isFinish);
        if (allFinished) {
            log(`★ 小节【${ch.curChapter}】全部 ${ch.totalItems} 个活动已完成！返回目录切换下一节`, 'success');
            await returnToCourseIndex();
            return;
        }

        // 3. 筛选未完成且本轮尚未处理过的课件
        const unfinishedIndices = ch.items.map((it, idx) => (!it.isFinish ? idx : -1)).filter(idx => idx >= 0);
        const candidates = unfinishedIndices.filter(idx => !state.processedInVisit.has(idx));

        if (candidates.length === 0 && unfinishedIndices.length > 0) {
            log(`小节【${ch.curChapter}】所有未完成课件均已尝试处理，触发防死循环保护并跳过本节`, 'warn');
            if (ch.curChapter) {
                state.skipSections.add(ch.curChapter);
                saveSkipSections();
            }
            await returnToCourseIndex();
            return;
        }

        // 4. 若当前激活的不是目标待刷课件，点击切换过去
        const targetIdx = candidates[0];
        if (ch.activeIdx !== targetIdx) {
            const targetItem = ch.items[targetIdx];
            log(`切换至待刷课件 [${targetIdx + 1}/${ch.totalItems}]：【${targetItem.name}】`);
            const clickEl = targetItem.el.querySelector('.activity-name, .activity-content-wrapper') || targetItem.el;
            clickEl.click();
            await sleep(2500);
            return;
        }

        // 5. 执行当前激活课件的自动化处理
        if (ch.isVideo) {
            await processVideoActivity(ch.curName);
        } else if (ch.isPPT) {
            await processPPTActivity(ch.curName);
        } else if (ch.isDoc) {
            await processDocActivity(ch.curName);
        } else if (ch.isExercise) {
            await processExerciseActivity(ch.curName);
        } else if (ch.isOtherInstant) {
            log(`正在同步其他资源完成状态：【${ch.curName}】`);
            triggerVueStudyProcess({ total: 1, end: 1, type: '275004' });
            await sleep(2500);
        } else {
            log(`等待课件内容加载：【${ch.curName}】...`);
            await sleep(2000);
        }

        state.processedInVisit.add(ch.activeIdx);
    }

    /**
     * 页面 D: 职业教育 AI 任务引导页 (/istp-learning-center/pattern/task-detail)
     */
    async function handleTaskDetailPage() {
        if (!state.config.running) return;
        const startBtn = document.querySelector('.cta-fixed .cta-btn, .el-button.cta-btn');
        if (startBtn) {
            const t = (startBtn.innerText || '').trim();
            if (t.includes('已完成')) {
                await returnToCourseIndex();
            } else {
                log(`点击任务详情页按钮：【${t}】`);
                startBtn.click();
                await sleep(2500);
            }
        }
    }

    // =========================================================================
    // 8. 悬浮控制面板 UI 与样式注入
    // =========================================================================
    const PANEL_CSS = `
        #fif-helper-panel {
            position: fixed;
            right: 20px;
            bottom: 24px;
            width: 330px;
            background: #1e293b;
            color: #f8fafc;
            border-radius: 12px;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            font-size: 13px;
            z-index: 999999;
            border: 1px solid rgba(255, 255, 255, 0.12);
            overflow: hidden;
            transition: height 0.2s ease, width 0.2s ease;
            user-select: none;
        }
        #fif-helper-panel.minimized {
            width: 190px;
        }
        #fif-helper-panel.minimized .fif-body {
            display: none;
        }
        .fif-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 14px;
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            cursor: move;
            font-weight: 600;
            font-size: 13.5px;
        }
        .fif-header-title {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .fif-badge {
            font-size: 11px;
            padding: 1px 6px;
            border-radius: 99px;
            background: rgba(255, 255, 255, 0.2);
            font-weight: 500;
        }
        .fif-min-btn {
            background: transparent;
            border: none;
            color: #fff;
            cursor: pointer;
            font-size: 15px;
            line-height: 1;
            padding: 2px 6px;
            border-radius: 4px;
        }
        .fif-min-btn:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        .fif-body {
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .fif-status-box {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 12px;
            line-height: 1.45;
            color: #38bdf8;
            word-break: break-all;
        }
        .fif-controls {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px 10px;
            font-size: 12px;
            color: #cbd5e1;
        }
        .fif-controls label {
            display: flex;
            align-items: center;
            gap: 5px;
            cursor: pointer;
        }
        .fif-rate-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: #cbd5e1;
        }
        .fif-rate-select {
            background: #0f172a;
            color: #f8fafc;
            border: 1px solid #475569;
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 12px;
        }
        .fif-btn-row {
            display: flex;
            gap: 8px;
        }
        .fif-btn {
            flex: 1;
            padding: 7px 10px;
            border: none;
            border-radius: 7px;
            font-weight: 600;
            font-size: 12.5px;
            cursor: pointer;
            transition: opacity 0.15s;
        }
        .fif-btn:hover {
            opacity: 0.92;
        }
        .fif-btn-primary {
            background: #10b981;
            color: #fff;
        }
        .fif-btn-Primary-stop {
            background: #ef4444;
            color: #fff;
        }
        .fif-btn-secondary {
            background: #334155;
            color: #e2e8f0;
            font-size: 11.5px;
            padding: 5px 8px;
        }
        .fif-log-list {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 6px;
            height: 92px;
            overflow-y: auto;
            padding: 6px 8px;
            font-family: Consolas, Monaco, monospace;
            font-size: 11px;
            color: #94a3b8;
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .fif-log-item.success { color: #34d399; }
        .fif-log-item.warn { color: #fbbf24; }
        .fif-helper-card-btn {
            margin-top: 8px;
            width: 100%;
            padding: 6px 10px;
            border: none;
            border-radius: 6px;
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #fff;
            font-size: 12.5px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(37, 99, 235, 0.35);
            transition: transform 0.12s ease;
        }
        .fif-helper-card-btn:hover {
            transform: translateY(-1px);
            background: linear-gradient(135deg, #1d4ed8, #1e40af);
        }
    `;

    function injectStyles() {
        if (typeof GM_addStyle === 'function') {
            GM_addStyle(PANEL_CSS);
        } else {
            const style = document.createElement('style');
            style.textContent = PANEL_CSS;
            document.head.appendChild(style);
        }
    }

    function createPanel() {
        if (document.getElementById('fif-helper-panel')) return;
        injectStyles();

        const panel = document.createElement('div');
        panel.id = 'fif-helper-panel';
        if (state.config.minimized) panel.classList.add('minimized');

        panel.innerHTML = `
            <div class="fif-header" id="fif-drag-handle">
                <div class="fif-header-title">
                    <span>⚡ FIF全自动刷课助手</span>
                    <span class="fif-badge" id="fif-mode-badge">就绪</span>
                </div>
                <button class="fif-min-btn" id="fif-min-toggle" title="折叠/展开面板">${state.config.minimized ? '＋' : '－'}</button>
            </div>
            <div class="fif-body">
                <div class="fif-status-box" id="fif-status-text">${state.statusText}</div>
                <div class="fif-controls">
                    <label title="直接调用 Vue 底层进度接口秒过视频/文档/PPT"><input type="checkbox" id="fif-cfg-fast" ${state.config.fastMode ? 'checked' : ''}> 极速秒刷模式</label>
                    <label title="遇到自适应练习自动开始并交卷"><input type="checkbox" id="fif-cfg-exercise" ${state.config.autoExercise ? 'checked' : ''}> 自动完成练习</label>
                    <label title="自动跳过所有单元检测与期中期末测验"><input type="checkbox" id="fif-cfg-skip-exam" ${state.config.skipExams ? 'checked' : ''}> 跳过单元检测</label>
                    <label title="当前课程全部刷完后自动返回工作台进入下一门课"><input type="checkbox" id="fif-cfg-next-course" ${state.config.autoNextCourse ? 'checked' : ''}> 多课程连刷</label>
                </div>
                <div class="fif-rate-row">
                    <span>视频常规播放倍速：</span>
                    <select class="fif-rate-select" id="fif-cfg-rate">
                        <option value="1">1.0x</option>
                        <option value="2">2.0x</option>
                        <option value="4">4.0x</option>
                        <option value="8">8.0x</option>
                        <option value="16">16.0x</option>
                    </select>
                </div>
                <div class="fif-btn-row">
                    <button class="fif-btn ${state.config.running ? 'fif-btn-Primary-stop' : 'fif-btn-primary'}" id="fif-toggle-run">
                        ${state.config.running ? '⏸ 暂停自动刷课' : '▶ 开始全自动刷课'}
                    </button>
                </div>
                <div class="fif-btn-row">
                    <button class="fif-btn fif-btn-secondary" id="fif-clear-skip" title="清空已标记跳过的异常小节缓存">清空跳过缓存 (<span id="fif-skip-count">${state.skipSections.size}</span>)</button>
                    <button class="fif-btn fif-btn-secondary" id="fif-go-home" title="返回学习空间课程列表首页">返回学习空间</button>
                </div>
                <div class="fif-log-list" id="fif-log-box"></div>
            </div>
        `;

        document.body.appendChild(panel);

        // 设置默认倍速下拉框
        const rateSelect = document.getElementById('fif-cfg-rate');
        if (rateSelect) rateSelect.value = String(state.config.videoRate || 4);

        // 绑定事件
        document.getElementById('fif-min-toggle').addEventListener('click', () => {
            state.config.minimized = !state.config.minimized;
            saveConfig();
            panel.classList.toggle('minimized', state.config.minimized);
            document.getElementById('fif-min-toggle').textContent = state.config.minimized ? '＋' : '－';
        });

        document.getElementById('fif-toggle-run').addEventListener('click', () => {
            state.config.running = !state.config.running;
            saveConfig();
            log(state.config.running ? '已启动全自动刷课引擎！' : '已暂停自动刷课。', state.config.running ? 'success' : 'warn');
            updatePanelUI();
        });

        document.getElementById('fif-cfg-fast').addEventListener('change', (e) => {
            state.config.fastMode = e.target.checked;
            saveConfig();
        });
        document.getElementById('fif-cfg-exercise').addEventListener('change', (e) => {
            state.config.autoExercise = e.target.checked;
            saveConfig();
        });
        document.getElementById('fif-cfg-skip-exam').addEventListener('change', (e) => {
            state.config.skipExams = e.target.checked;
            saveConfig();
        });
        document.getElementById('fif-cfg-next-course').addEventListener('change', (e) => {
            state.config.autoNextCourse = e.target.checked;
            saveConfig();
        });
        document.getElementById('fif-cfg-rate').addEventListener('change', (e) => {
            state.config.videoRate = Number(e.target.value) || 4.0;
            saveConfig();
        });

        document.getElementById('fif-clear-skip').addEventListener('click', () => {
            state.skipSections.clear();
            state.completedCourses.clear();
            saveSkipSections();
            saveCompletedCourses();
            log('已清空异常小节与已完成课程跳过记录！', 'success');
            updatePanelUI();
        });

        document.getElementById('fif-go-home').addEventListener('click', () => {
            location.href = 'https://icourse.fifedu.com/istp-manage/work/home';
        });

        // 拖拽支持
        const handle = document.getElementById('fif-drag-handle');
        let isDragging = false, startX = 0, startY = 0, origRight = 20, origBottom = 24;
        handle.addEventListener('mousedown', (e) => {
            if (e.target.id === 'fif-min-toggle') return;
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;
            const rect = panel.getBoundingClientRect();
            origRight = window.innerWidth - rect.right;
            origBottom = window.innerHeight - rect.bottom;
        });
        window.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            panel.style.right = Math.max(0, origRight - dx) + 'px';
            panel.style.bottom = Math.max(0, origBottom - dy) + 'px';
        });
        window.addEventListener('mouseup', () => { isDragging = false; });

        updatePanelUI();
    }

    function updatePanelUI() {
        const statusEl = document.getElementById('fif-status-text');
        const runBtn = document.getElementById('fif-toggle-run');
        const badgeEl = document.getElementById('fif-mode-badge');
        const skipCountEl = document.getElementById('fif-skip-count');
        const logBox = document.getElementById('fif-log-box');

        if (statusEl) statusEl.textContent = state.statusText;
        if (skipCountEl) skipCountEl.textContent = String(state.skipSections.size);
        if (runBtn) {
            runBtn.className = `fif-btn ${state.config.running ? 'fif-btn-Primary-stop' : 'fif-btn-primary'}`;
            runBtn.textContent = state.config.running ? '⏸ 暂停自动刷课' : '▶ 开始全自动刷课';
        }
        if (badgeEl) {
            const path = location.pathname;
            if (path.includes('/istp-manage/work/home')) badgeEl.textContent = '学习空间';
            else if (path.includes('/istp-learning-center/index')) badgeEl.textContent = '章节目录';
            else if (path.includes('/pattern/chapter')) badgeEl.textContent = '刷课中';
            else badgeEl.textContent = state.config.running ? '运行中' : '待机';
        }
        if (logBox) {
            logBox.innerHTML = state.logs.slice(0, 25).map(item =>
                `<div class="fif-log-item ${item.level}"><span>${item.time}</span> ${item.msg}</div>`
            ).join('');
        }
    }

    // =========================================================================
    // 9. 主循环调度器与油猴菜单注册
    // =========================================================================
    async function mainTick() {
        createPanel();
        if (state.busy) return;
        state.busy = true;

        try {
            if (await handleModals()) {
                state.busy = false;
                return;
            }

            const path = location.pathname;
            if (path.includes('/istp-manage/work/home') || path === '/istp-manage/' || path === '/istp-manage') {
                await handleWorkHomePage();
            } else if (path.includes('/istp-learning-center/index')) {
                await handleCourseIndexPage();
            } else if (path.includes('/istp-learning-center/pattern/chapter')) {
                await handleChapterStudyPage();
            } else if (path.includes('/istp-learning-center/pattern/task-detail')) {
                await handleTaskDetailPage();
            }
        } catch (err) {
            console.error('[FIF助手] 调度循环异常:', err);
        } finally {
            state.busy = false;
            updatePanelUI();
        }
    }

    if (typeof GM_registerMenuCommand === 'function') {
        GM_registerMenuCommand('▶ 启动/暂停自动刷课', () => {
            state.config.running = !state.config.running;
            saveConfig();
            updatePanelUI();
        });
        GM_registerMenuCommand('🗑️ 清空跳过记录缓存', () => {
            state.skipSections.clear();
            state.completedCourses.clear();
            saveSkipSections();
            saveCompletedCourses();
            updatePanelUI();
        });
    }

    // 启动主定时器
    setInterval(mainTick, 2200);
    setTimeout(mainTick, 800);
})();
