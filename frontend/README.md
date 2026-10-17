# AI 教学督导系统（前端）

教学督导系统的前端：登录 → 课程 → 上传课堂录音 → 轮询 AI 处理状态 → 查看评价结果 → 督导保存评语与人工校准。**所有数据来自真实后端接口，前端不包含任何 mock 数据。**

## 技术栈

- Vue 3 + TypeScript + Vite（开发端口 5173）
- Pinia（状态）、Vue Router（路由）
- Element Plus（UI 组件库）、ECharts（雷达图/对比图，按需引入）
- axios（HTTP）、dayjs（时间处理）
- Vitest + @vue/test-utils（测试）

## 快速开始

```powershell
cd frontend
npm install
Copy-Item .env.example .env   # 按需修改 VITE_API_BASE_URL
npm run dev                   # http://localhost:5173
```

后端需先启动（见 `backend/README.md`）：

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

## 完整业务闭环联调

1. 在 `backend/.env` 中设置 `INITIAL_ADMIN_PASSWORD`（≥12 位，首次启动自动创建管理员），并启动后端
2. 管理员登录前端（默认用户名 `admin`），在「用户管理」创建督导与教师账号
3. 督导登录，在「课程」新建课程并指定教师
4. 教师登录，进入课程详情 → 上传课堂录音（WAV/MP3/M4A，需录制时间与隐私授权）
5. 运行模拟 AI 处理进程（仅标准库，无需安装依赖）：

   ```powershell
   $env:AI_SERVICE_TOKEN = "与 backend/.env 中一致的服务令牌"
   python mock_worker.py
   ```

6. 前端自动轮询任务状态（5 秒间隔），处理完成后「查看评价」展示转写、分段、总分、证据、问题与建议
7. 督导登录同一课程的评价页，保存评语与人工校准；刷新后总分与六维雷达图体现校准生效值
8. 「评价对比」Tab 展示最近两次课堂的总分与六维变化

## 项目结构

```text
frontend/
├── mock_worker.py            # 模拟 AI 处理进程（仅标准库，联调用）
├── src/
│   ├── api/                  # axios 实例（http.ts）与按模块拆分的接口
│   ├── types/                # 与后端契约逐字段对齐的 TypeScript 类型
│   ├── stores/               # Pinia：认证状态、本地上传记录
│   ├── router/               # 路由与登录/角色守卫
│   ├── composables/          # usePollingTask（轮询）、useAudioSource（blob 音频）
│   ├── utils/                # 校验、格式化、角色判断、凭证持久化
│   ├── components/           # 上传弹窗、转写时间轴、雷达图、评语/校准等
│   ├── views/                # 登录/课程列表/课程详情/评价详情/用户管理
│   └── styles/               # 设计令牌与基础样式
└── src/__tests__/            # Vitest 测试
```

## 目录规范

- API 地址通过 `.env` 的 `VITE_API_BASE_URL` 配置，组件内不硬编码
- 所有组件统一使用 `src/api/http.ts` 的 axios 实例；拦截器自动附加 Bearer token、解包 `{code,message,data}`，并集中处理 401（清除凭证跳登录）、403、网络错误
- 接口按模块拆分：`auth.ts` / `users.ts` / `courses.ts` / `recordings.ts` / `evaluations.ts`
- 角色判断集中在 `utils/roles.ts` 与 Pinia store，模板中不散落判断
- localStorage 仅通过 `utils/token.ts` 与 stores 读写
- 上传状态轮询统一使用 `usePollingTask`，页面卸载/完成/失败/超时自动清理定时器

## 测试与构建

```powershell
npm test        # vitest：登录恢复、路由权限、401 处理、上传校验、轮询、校准、只读权限、空态/错误态
npm run build   # vue-tsc 类型检查 + 产物构建
```

## 已知约定

- 后端未提供课程录音列表接口：上传后的任务记录由前端存 localStorage 跟踪（刷新页面后仍在）；已完成的评价走「历史评价」分页。建议后端后续补充 `GET /courses/{id}/recordings`。
- 登录凭证有效期 30 分钟且无刷新机制，过期后自动跳转登录页重新登录。
- 上传无服务器端进度，前端进度条基于浏览器上传进度（onUploadProgress）。
- `basic` 模式评价可能不含六维分数，雷达图区域会显示占位提示。
