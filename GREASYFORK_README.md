# FIF智慧教学平台全自动刷课助手 (GreasyFork 发布说明)

[![GreasyFork 版本](https://img.shields.io/greasyfork/v/604397?style=for-the-badge&logo=greasyfork&logoColor=white&label=GreasyFork&color=670000)](https://greasyfork.org/zh-CN/scripts/604397-fif%E6%99%BA%E6%85%A7%E6%95%99%E5%AD%A6%E5%B9%B3%E5%8F%B0%E5%85%A8%E8%87%AA%E5%8A%A8%E5%88%B7%E8%AF%BE%E5%8A%A9%E6%89%8B-icourse-fifedu-com)
[![GreasyFork 总安装量](https://img.shields.io/greasyfork/dt/604397?style=for-the-badge&logo=greasyfork&logoColor=white&label=%E6%80%BB%E5%AE%89%E8%A3%85%E9%87%8F&color=e05d44)](https://greasyfork.org/zh-CN/scripts/604397-fif%E6%99%BA%E6%85%A7%E6%95%99%E5%AD%A6%E5%B9%B3%E5%8F%B0%E5%85%A8%E8%87%AA%E5%8A%A8%E5%88%B7%E8%AF%BE%E5%8A%A9%E6%89%8B-icourse-fifedu-com)
[![UserScript 兼容引擎](https://img.shields.io/badge/UserScript-Tampermonkey%20%7C%20Violentmonkey-00485B?style=for-the-badge&logo=tampermonkey&logoColor=white)](./fif-auto-study.user.js)
[![适用平台](https://img.shields.io/badge/Platform-icourse.fifedu.com-2563EB?style=for-the-badge&logo=googlechrome&logoColor=white)](https://icourse.fifedu.com/istp-manage/work/home)
[![开源协议](https://img.shields.io/badge/License-MIT-10B981?style=for-the-badge)](https://github.com/hermes186/Fifedu-)

> 适用于 **FIF 智慧教学平台 / 讯飞高教自适应学习系统**（[icourse.fifedu.com](https://icourse.fifedu.com/istp-manage/work/home) 及全站课程页面）的全自动辅助学习油猴脚本（Tampermonkey / Violentmonkey / ScriptCat）。

---

## 核心功能特性

- **全站路由与多课程适配**：
  - 支持从学习空间首页（`/istp-manage/work/home`）自动识别「我学的课」列表，并在每门课程卡片上注入 **「🚀 自动刷此课」** 快捷按钮。
  - 支持开启 **「多课程连刷」**，当前课程全部小节完成后自动返回工作台切入下一门未完成课程。
- **全类型课件自动完成**：
  - **音视频课件（`.mp4` / `.mp3` / `xgplayer`）**：支持自动静音播放、自定义倍速（`1x` ~ `16x`）、极速完成及平台损坏视频源（`MEDIA_ELEMENT_ERROR`）容错直报。
  - **PPT 课件（`.ppt` / `.pptx` / `ow365`）**：支持自动模拟翻页与底层页码进度同步，直达末页完成打勾。
  - **文档与 PDF 课件（`.pdf` / `.doc` / `.docx` / `.txt` / `.xls`）**：支持跨框架 `PDF.js` 自动跳至末页置底，并结合 Vue 3 底层 `studyProcess` 接口直报，解决平台单页 PDF 不打勾的顽疾。
  - **自适应练习**：支持自动点击「开始练习 / 继续练习」、自动交卷并确认弹窗。
- **安全与防死循环保护**：
  - 默认自动跳过所有 **单元检测 / 单元测验 / 期中期末考试**。
  - 内置小节防死锁机制，若遇平台后端异常导致某小节无法打勾，单次遍历后自动记入跳过缓存，绝不无限死循环。
- **可视化悬浮控制面板**：
  - 右下角自带可拖拽、可折叠的现代化暗色控制面板，实时显示运行状态与执行日志。

---

## 安装与使用方法

1. 在浏览器中安装 **Tampermonkey（篡改猴）** 或 **Violentmonkey（暴力猴）** 扩展。
2. 前往 [GreasyFork 脚本发布页 (#604397)](https://greasyfork.org/zh-CN/scripts/604397-fif%E6%99%BA%E6%85%A7%E6%95%99%E5%AD%A6%E5%B9%B3%E5%8F%B0%E5%85%A8%E8%87%AA%E5%8A%A8%E5%88%B7%E8%AF%BE%E5%8A%A9%E6%89%8B-icourse-fifedu-com) 在线安装，或导入本地脚本 [`fif-auto-study.user.js`](./fif-auto-study.user.js)。
3. 打开 [FIF 智慧教学平台学习空间](https://icourse.fifedu.com/istp-manage/work/home) 并登录账号。
4. 点击任意课程卡片下方的 **「🚀 自动刷此课」** 按钮，或在课程目录页点击右下角面板的 **「▶ 开始全自动刷课」** 即可全自动运行。

---

## GreasyFork 上架信息对照表

| 字段项 | 填写内容 |
| :--- | :--- |
| **脚本名称** | `FIF智慧教学平台全自动刷课助手 (icourse.fifedu.com)` |
| **GreasyFork 链接** | [GreasyFork #604397](https://greasyfork.org/zh-CN/scripts/604397-fif%E6%99%BA%E6%85%A7%E6%95%99%E5%AD%A6%E5%B9%B3%E5%8F%B0%E5%85%A8%E8%87%AA%E5%8A%A8%E5%88%B7%E8%AF%BE%E5%8A%A9%E6%89%8B-icourse-fifedu-com) |
| **脚本语言** | JavaScript |
| **开源协议** | `MIT` |
| **适用域名** | `icourse.fifedu.com`、`resc.fifedu.com`、`ow365.cn` |
| **外部依赖** | 无（纯原生 JS，完全符合 GreasyFork 免审查外部依赖规范） |
