-- Insert the comprehensive requirements document for the MAS Dashboard project (project_id = 2)
INSERT INTO main.project_document (
  project_id,
  document_name,
  document_type,
  raw_text_content,
  file_extension,
  file_mime_type,
  version_number,
  is_active_version,
  created_by,
  serialization_status
) VALUES (
  2,
  'MAS Dashboard - Full Requirements Specification',
  'requirements',
  $DOC$
# Midnight Agent Space (MAS) Dashboard — Full Requirements & Implementation Specification

## 1. Project Overview

Build a modern, minimal web dashboard for the Midnight Agent Space platform. The dashboard connects directly to the existing PostgreSQL database (pgvector-postgres on port 5434, database: midnight_agent_space_dev, schema: main) and communicates with the Temporal workflow engine to provide:

- Project listing and management
- Workflow execution with configurable options
- File upload for document serialization (alternative to raw DB text)
- Real-time workflow activity visualization with animated UI
- Detailed activity run inspection

The dashboard lives inside the existing MidnightAgentSpace repository at `c:\Users\tipod\Documents\Midnight\MidnightAgentSpace\dashboard\` and must NOT alter the existing `temporal/` folder structure.

Technology stack:
- **Backend**: Python FastAPI (async, lightweight, connects to same PostgreSQL)
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS
- **Real-time**: WebSocket via FastAPI for live workflow status
- **Database**: Direct connection to existing `midnight_agent_space_dev` PostgreSQL on localhost:5434
- **Temporal Client**: Python temporalio SDK to start/query workflows

## 2. Architecture

```
dashboard/
├── backend/                   # FastAPI backend
│   ├── main.py                # FastAPI app entry (CORS, routes, WebSocket)
│   ├── config.py              # DB connection config (reads from temporal/.env)
│   ├── database.py            # asyncpg pool, query helpers
│   ├── routes/
│   │   ├── projects.py        # CRUD for main.project
│   │   ├── workflows.py       # Start/query/list workflows via Temporal
│   │   ├── documents.py       # Upload files, list project documents
│   │   └── tasks.py           # Read-only task list and details
│   ├── services/
│   │   ├── temporal_client.py # Temporal SDK client wrapper
│   │   └── file_service.py    # File upload processing
│   ├── ws/
│   │   └── workflow_monitor.py # WebSocket endpoint for live activity updates
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/               # API client hooks (fetch + WebSocket)
│   │   ├── components/
│   │   │   ├── layout/        # Sidebar, Header, MainLayout
│   │   │   ├── projects/      # ProjectList, ProjectDetail, ProjectForm
│   │   │   ├── workflows/     # WorkflowLauncher, WorkflowOptions
│   │   │   ├── documents/     # FileUpload, DocumentList
│   │   │   ├── tasks/         # TaskList, TaskDetail (read-only)
│   │   │   └── visualization/ # ActivityDots, ActivityDetail, WorkflowTimeline
│   │   ├── pages/
│   │   │   ├── DashboardHome.tsx
│   │   │   ├── ProjectsPage.tsx
│   │   │   ├── ProjectDetailPage.tsx
│   │   │   ├── WorkflowRunPage.tsx
│   │   │   └── WorkflowDetailPage.tsx
│   │   ├── hooks/
│   │   │   ├── useProjects.ts
│   │   │   ├── useWorkflow.ts
│   │   │   └── useWebSocket.ts
│   │   ├── types/
│   │   │   └── index.ts       # TypeScript interfaces matching DB schema
│   │   └── styles/
│   │       └── globals.css    # Tailwind base + custom animations
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
├── docker-compose.dashboard.yml  # Optional: containerize dashboard
└── README.md
```

## 3. Database Connection Details

The dashboard backend connects to the SAME PostgreSQL instance as the temporal system:

```
Host: localhost
Port: 5434
Database: midnight_agent_space_dev
User: postgres
Password: 7714
Schema: main
```

Read these from `temporal/.env` or define a shared `.env` at project root.

## 4. Detailed Feature Specifications

### 4.1 Project List & Management

**Endpoint: GET /api/projects**
- Query: `SELECT project_id, project_name, project_type, description, status, created_at, updated_at FROM main.project ORDER BY project_id DESC`
- Response: Array of project objects
- The project list is the main landing page of the dashboard

**Endpoint: GET /api/projects/:id**
- Returns full project details including associated documents count, task count, recent workflow runs

**Endpoint: PUT /api/projects/:id**
- Updates project_name, project_type, description, status
- Does NOT allow editing workflow results or tasks (those are read-only)

**Endpoint: POST /api/projects**
- Creates a new project in main.project

**UI Requirements:**
- Card-based grid layout for project list
- Each card shows: project_name, project_type badge, status indicator (color dot), description preview, created_at
- Each card has a "Run Workflow" button that opens workflow execution options
- Clicking a card navigates to project detail page
- Search/filter bar at top

### 4.2 Project Detail Page

Shows:
- Editable project info (name, type, description, status) with save button
- Tabs: Documents | Tasks | Workflow Runs
- Documents tab: list of project_document rows with upload button
- Tasks tab: read-only list of tasks with status badges (from main.task)
- Workflow Runs tab: list of workflow_run rows with status, timestamps

### 4.3 Document Upload & Management

**Endpoint: POST /api/projects/:id/documents/upload**
- Accepts multipart file upload
- Reads file content and stores in main.project_document:
  - document_name = original filename
  - document_type = 'uploaded'
  - raw_text_content = file text content (for .txt, .md, .json, .csv, .xml)
  - file_extension = detected extension
  - file_mime_type = detected MIME type
  - file_size_bytes = file size
  - file_content = raw bytes (bytea) for binary files
  - serialization_status = 'PENDING'
- This allows document_serialization_workflow to read actual uploaded files instead of only raw text from DB

**Endpoint: GET /api/projects/:id/documents**
- Lists all documents for a project from main.project_document
- Shows: document_name, document_type, file_extension, file_size_bytes, serialization_status, created_at

**Endpoint: DELETE /api/projects/:id/documents/:doc_id**
- Deletes a document (only if serialization_status = 'PENDING')

**UI Requirements:**
- Drag-and-drop file upload zone with visual feedback
- File type icons
- Upload progress indicator
- Document list table with columns: Name, Type, Size, Status, Actions

### 4.4 Workflow Execution from Dashboard

**Endpoint: POST /api/workflows/start**
- Request body:
  ```json
  {
    "project_id": 2,
    "agent_id": 2,
    "agent_provider": "claude-code",
    "execute_mode": "complex",
    "concurrent_tasks": false,
    "batch_tasks": true
  }
  ```
- Backend uses temporalio Python SDK to start DocumentSerializationWorkflow
- Returns workflow_id for tracking

**Endpoint: GET /api/workflows/:workflow_id/status**
- Queries Temporal for workflow status, history events
- Returns current status, pending activities, completed activities

**Endpoint: GET /api/workflows/runs?project_id=2**
- Lists workflow_run rows from main.workflow_run for a project

**UI Requirements:**
- Workflow launcher modal/panel with dropdowns for:
  - Agent Provider: cursor | codex | claude-code
  - Execute Mode: fast | complex
  - Checkboxes: Concurrent Tasks, Batch Tasks (mutually exclusive)
  - Agent ID selector (from main.agent table)
- "Run Workflow" button per project card AND on project detail page
- After starting: redirect to workflow run visualization page

### 4.5 Real-Time Workflow Activity Visualization (KEY FEATURE)

This is the signature UI feature. When a workflow is running in Temporal:

**Backend: WebSocket endpoint ws://localhost:8001/ws/workflow/:workflow_id**
- Polls Temporal for workflow history events every 2 seconds
- Sends structured activity events to connected frontend clients
- Each event includes:
  - activity_type (e.g., "spin_up_agent_activity", "chunk_document_activity")
  - status (SCHEDULED, STARTED, COMPLETED, FAILED)
  - input_summary (human-readable summary of activity input)
  - output_summary (brief result when completed)
  - started_at, completed_at, duration
  - activity_id

**Frontend Visualization: Floating Dots Animation**

Design specification for the animated visualization:
- Dark background canvas (charcoal/dark slate)
- Each activity run is represented by an animated floating dot/orb
- Dot states and colors:
  - SCHEDULED: small gray dot, gently pulsing
  - STARTED/RUNNING: medium blue-cyan dot, orbiting slowly with a glow trail
  - COMPLETED: green dot, brief burst animation then settles to a resting position
  - FAILED: red dot, shake animation then settles
- Dots float in a physics-like space with gentle drift and subtle particle effects
- Each dot has a label showing: activity name (shortened, friendly) + brief input summary
  - Example: "Chunking Document 1" or "Executing Task: Create API routes"
- Dots are positioned in a loose timeline flow (left to right)
- Smooth CSS/canvas animations (use framer-motion or react-spring or pure CSS)
- A small summary text below each dot (only visible on hover or when few dots)
- Overall aesthetic: like watching stars/particles in a constellation map

**Click-to-Detail Interaction:**
- Clicking any dot opens a slide-in panel or modal showing:
  - Full activity name
  - Activity type
  - Status with colored badge
  - Started at / Completed at / Duration
  - Full input data (formatted JSON, collapsible)
  - Full output/result data (formatted JSON, collapsible)
  - Error details if FAILED
- Panel is scrollable and has human-friendly formatting (not raw JSON dumps)
- Key-value pairs displayed in a clean table
- Long text fields (like prompts or descriptions) shown in expandable sections

### 4.6 Workflow Run Detail Page

**Route: /workflows/:workflow_id**
- Top section: workflow metadata (workflow_id, type, status, project_name, started_at, duration)
- Main section: the animated activity dots visualization (described above)
- Bottom section: scrollable activity timeline (chronological list view as fallback)
  - Each row: activity name | status badge | duration | brief summary
  - Expandable rows for full details

### 4.7 Tasks View (Read-Only)

**Endpoint: GET /api/projects/:id/tasks**
- Query: `SELECT * FROM main.task WHERE project_id = :id ORDER BY priority ASC, created_at ASC`
- Returns task list with all fields

**Endpoint: GET /api/tasks/:task_id**
- Returns full task detail including task_data JSON

**UI Requirements:**
- Table view with columns: Priority, Name, Type, Status, Description (truncated)
- Click row to expand and see full task details
- task_data displayed as formatted, collapsible JSON
- Status badges: PENDING (gray), IN_PROGRESS (blue), COMPLETED (green), FAILED (red)
- No edit capability (read-only as specified)

### 4.8 Dashboard Home

**Route: /**
- Quick stats cards:
  - Total Projects (count from main.project)
  - Active Workflows (count RUNNING from main.workflow_run)
  - Total Tasks (count from main.task)
  - Recent Activity (last 5 workflow_runs)
- Quick-access project grid (top 6 recent projects)
- "New Project" button

## 5. Design System

### Colors
- Background: slate-950 (#020617) to slate-900 (#0f172a)
- Cards: slate-800/50 with backdrop-blur
- Primary accent: cyan-500 (#06b6d4)
- Success: emerald-500 (#10b981)
- Error: rose-500 (#f43f5e)
- Warning: amber-500 (#f59e0b)
- Text primary: slate-100
- Text secondary: slate-400

### Typography
- Font: Inter (or system UI stack)
- Headings: font-semibold
- Body: font-normal, text-sm for most content

### Components
- Rounded corners (rounded-xl for cards, rounded-lg for buttons)
- Subtle borders (border-slate-700/50)
- Glass-morphism effect on cards (backdrop-blur-sm, bg-opacity)
- Smooth transitions on all interactive elements (transition-all duration-200)
- Focus rings in cyan for accessibility

## 6. API Base URL & CORS

- Backend runs on: http://localhost:8001
- Frontend runs on: http://localhost:5173 (Vite default)
- CORS: Allow origin http://localhost:5173
- WebSocket: ws://localhost:8001/ws/*

## 7. Implementation Priority & Task Breakdown

### Phase 1: Foundation (Priority 1)
1. Set up backend FastAPI project with database connection (asyncpg to existing PostgreSQL)
2. Set up frontend React+Vite+Tailwind project
3. Implement project CRUD endpoints and project list page
4. Implement basic navigation layout (sidebar + header)

### Phase 2: Core Features (Priority 2)
5. Implement document upload endpoint and file processing
6. Implement document list and file upload UI with drag-and-drop
7. Implement workflow start endpoint (Temporal client integration)
8. Implement workflow launcher UI with option selectors
9. Implement tasks read-only endpoints and tasks table UI

### Phase 3: Visualization (Priority 3)
10. Implement WebSocket endpoint for workflow monitoring
11. Implement floating dots animation component
12. Implement click-to-detail activity panel
13. Implement workflow run detail page with timeline
14. Implement dashboard home page with stats

### Phase 4: Polish (Priority 4)
15. Add search/filter to project list
16. Add error handling and loading states throughout
17. Responsive design adjustments
18. Integration testing with live Temporal workflows

## 8. Key Implementation Notes

- The backend MUST read database credentials from the existing `temporal/.env` file or environment variables (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
- Use asyncpg for async PostgreSQL access (not psycopg2 which is sync)
- The Temporal client in the backend should connect to localhost:7233 (same as the worker)
- File uploads should support: .txt, .md, .json, .csv, .xml, .pdf, .docx
- For text-based files, extract raw_text_content for the document_serialization_workflow
- The WebSocket monitor queries Temporal's GetWorkflowExecutionHistory API to get activity events
- Use CSS animations (keyframes) or framer-motion for the floating dots — avoid heavy canvas/WebGL
- All timestamps should be displayed in a human-friendly relative format ("2 minutes ago")
- The sidebar should show: Dashboard, Projects, (future: Agents, Settings)
- Project status values: ACTIVE, COMPLETED, ARCHIVED, PAUSED

## 9. Database Tables Referenced

The dashboard reads/writes these existing tables in schema `main`:
- **main.project** — CRUD (create, read, update; no delete)
- **main.project_document** — Read + Insert (file upload)
- **main.task** — Read only
- **main.workflow_run** — Read only
- **main.agent** — Read only (for agent selector in workflow launcher)
- **main.activity_run** — Read only (for visualization)
- **main.task_execution** — Read only (for task detail)
- **main.event_log** — Read only (for activity details)

## 10. Environment & Running

```bash
# Backend
cd dashboard/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd dashboard/frontend
npm install
npm run dev
```

The dashboard should work immediately after setup since it connects to the same PostgreSQL and Temporal instances already running via Docker.
$DOC$,
  '.md',
  'text/markdown',
  0,
  TRUE,
  'system',
  'PENDING'
);
