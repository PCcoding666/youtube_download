# CI/CD Pipeline Architecture

## Complete Pipeline Flow

```mermaid
graph TB
    Start[Developer Push Code] --> GitHub[GitHub Repository]
    GitHub --> Trigger{GitHub Actions<br/>Triggered}
    
    Trigger --> FrontendCI[Frontend CI Job]
    Trigger --> BackendCI[Backend CI Job]
    
    FrontendCI --> FrontendSteps[1. Type Check<br/>2. Build<br/>3. Upload Artifacts]
    BackendCI --> BackendSteps[1. Install Deps<br/>2. Linting<br/>3. Run Tests]
    
    FrontendSteps --> BuildJob{Build & Push Job<br/>Needs: Both CI Pass}
    BackendSteps --> BuildJob
    
    BuildJob --> Docker[Docker Buildx Setup]
    Docker --> Login[Login to Aliyun Registry]
    Login --> BuildBackend[Build Backend Image]
    Login --> BuildFrontend[Build Frontend Image]
    
    BuildBackend --> PushBackend[Push to Registry<br/>registry.cn-hangzhou.aliyuncs.com]
    BuildFrontend --> PushFrontend[Push to Registry<br/>registry.cn-hangzhou.aliyuncs.com]
    
    PushBackend --> Deploy{Deploy Job<br/>Needs: Build Success}
    PushFrontend --> Deploy
    
    Deploy --> SSH[SSH to Server<br/>via GitHub Actions]
    SSH --> ServerLogin[Login to Aliyun Registry<br/>on Server]
    ServerLogin --> Pull[Pull Latest Images]
    Pull --> Backup[Create Deployment Backup]
    
    Backup --> UpdateBackend[Rolling Update Backend<br/>docker-compose up -d backend]
    UpdateBackend --> HealthCheck1{Backend<br/>Health Check}
    
    HealthCheck1 -->|Pass| UpdateFrontend[Update Frontend<br/>docker-compose up -d frontend]
    HealthCheck1 -->|Fail| Rollback[Automatic Rollback]
    
    UpdateFrontend --> HealthCheck2{Final<br/>Health Check}
    HealthCheck2 -->|Pass| Cleanup[Clean Old Images]
    HealthCheck2 -->|Fail| Rollback
    
    Cleanup --> Success[Deployment Success]
    Success --> NotifySuccess[Send Success Notification<br/>Telegram/Email]
    
    Rollback --> NotifyFail[Send Failure Notification<br/>Telegram/Email]
    
    NotifySuccess --> End[End - Service Running]
    NotifyFail --> End
    
    style Start fill:#e1f5e1
    style Success fill:#c8e6c9
    style Rollback fill:#ffcdd2
    style HealthCheck1 fill:#fff9c4
    style HealthCheck2 fill:#fff9c4
    style Deploy fill:#b3e5fc
    style BuildJob fill:#b3e5fc
```

## Zero-Downtime Deployment Strategy

```mermaid
graph LR
    subgraph "Current State"
        Old[Old Container<br/>Running]
    end
    
    subgraph "Update Process"
        Pull[Pull New Image] --> Create[Create New Container]
        Create --> Health{Health Check}
        Health -->|Pass| Switch[Switch Traffic]
        Health -->|Fail| Remove[Remove New Container]
        Switch --> Stop[Stop Old Container]
    end
    
    subgraph "New State"
        New[New Container<br/>Running]
    end
    
    Old --> Pull
    Stop --> New
    Remove --> Old
    
    style Health fill:#fff9c4
    style New fill:#c8e6c9
    style Remove fill:#ffcdd2
```

## Service Architecture on Server

```mermaid
graph TB
    subgraph "Internet"
        User[Users/Clients]
    end
    
    subgraph "Server - Docker Network"
        Nginx[Frontend Container<br/>Nginx:80/443]
        Backend[Backend Container<br/>FastAPI:8000]
        
        Nginx --> Backend
    end
    
    subgraph "External Services"
        Registry[Aliyun Container Registry<br/>Image Storage]
        OSS[Aliyun OSS<br/>File Storage]
        Qwen[Qwen API<br/>AI Service]
        AgentGo[AgentGo<br/>Browser Automation]
    end
    
    User --> Nginx
    Backend --> OSS
    Backend --> Qwen
    Backend --> AgentGo
    
    Registry -.Pull Images.-> Nginx
    Registry -.Pull Images.-> Backend
    
    style Nginx fill:#b3e5fc
    style Backend fill:#c8e6c9
    style Registry fill:#fff9c4
```

## GitHub Actions Workflow Jobs

```mermaid
gantt
    title CI/CD Pipeline Timeline
    dateFormat  HH:mm:ss
    axisFormat %M:%S
    
    section CI
    Frontend CI           :a1, 00:00:00, 2m
    Backend CI            :a2, 00:00:00, 3m
    
    section Build
    Docker Build Backend  :a3, after a2, 3m
    Docker Build Frontend :a4, after a2, 2m
    
    section Registry
    Push Backend          :a5, after a3, 1m
    Push Frontend         :a6, after a4, 1m
    
    section Deploy
    SSH Connection        :a7, after a5 a6, 30s
    Pull Images           :a8, after a7, 1m
    Update Backend        :a9, after a8, 1m
    Health Check          :a10, after a9, 1m
    Update Frontend       :a11, after a10, 30s
    Final Check           :a12, after a11, 30s
```

## Environment Configuration Flow

```mermaid
graph LR
    subgraph "GitHub Repository"
        Code[Source Code]
        Actions[GitHub Actions]
        Secrets[GitHub Secrets<br/>API Keys, Credentials]
    end
    
    subgraph "Build Process"
        Build[Docker Build]
        Env1[.env.example<br/>Template Only]
    end
    
    subgraph "Server Runtime"
        Env2[.env.production<br/>Real Values]
        Containers[Docker Containers<br/>Use Real Env]
    end
    
    Code --> Build
    Env1 -.Template.-> Env2
    Secrets -.Secure.-> Env2
    Build --> Containers
    Env2 --> Containers
    
    style Secrets fill:#ffcdd2
    style Env2 fill:#fff9c4
```

## Health Check Process

```mermaid
graph TD
    Start[Start Health Check] --> Attempt{Attempt Counter<br/>< 30?}
    
    Attempt -->|Yes| Check[curl http://localhost:8000/api/v1/health]
    Attempt -->|No| Fail[Health Check Failed]
    
    Check --> Success{Status 200?}
    Success -->|Yes| Pass[Health Check Passed]
    Success -->|No| Wait[Wait 2 seconds]
    
    Wait --> Increment[Counter++]
    Increment --> Attempt
    
    Pass --> Deploy[Continue Deployment]
    Fail --> Rollback[Trigger Rollback]
    
    style Pass fill:#c8e6c9
    style Fail fill:#ffcdd2
    style Success fill:#fff9c4
```

## Backup and Rollback Strategy

```mermaid
graph TB
    Deploy[New Deployment] --> CreateBackup[Create Backup<br/>Timestamp: YYYYMMDD_HHMMSS]
    CreateBackup --> SaveCompose[Save docker-compose.yml]
    CreateBackup --> SaveEnv[Save .env.production]
    CreateBackup --> SaveImages[Save Image Tags]
    
    SaveCompose --> Backups[(Backup Directory<br/>Keep Last 5)]
    SaveEnv --> Backups
    SaveImages --> Backups
    
    Backups --> Attempt{Deployment<br/>Successful?}
    
    Attempt -->|Yes| CleanOld[Clean Old Backups<br/>Keep Only 5]
    Attempt -->|No| GetLatest[Get Latest Backup]
    
    GetLatest --> Restore[Restore Files]
    Restore --> Recreate[Recreate Containers]
    Recreate --> RollbackComplete[Rollback Complete]
    
    CleanOld --> Success[Deployment Complete]
    
    style Attempt fill:#fff9c4
    style Success fill:#c8e6c9
    style RollbackComplete fill:#ffcdd2
```

## Notification Flow

```mermaid
graph LR
    Pipeline[CI/CD Pipeline] --> Status{Deployment<br/>Status}
    
    Status -->|Success| SuccessMsg[Prepare Success Message<br/>✅ Repository<br/>📌 Branch<br/>💬 Commit<br/>👤 Author<br/>🚀 URL]
    Status -->|Failure| FailMsg[Prepare Failure Message<br/>❌ Repository<br/>📌 Branch<br/>💬 Commit<br/>👤 Author<br/>🔗 Logs URL]
    
    SuccessMsg --> Telegram1[Send to Telegram]
    FailMsg --> Telegram2[Send to Telegram]
    
    Telegram1 --> User[Developer Notified]
    Telegram2 --> User
    
    style SuccessMsg fill:#c8e6c9
    style FailMsg fill:#ffcdd2
    style Telegram1 fill:#64b5f6
    style Telegram2 fill:#64b5f6
```

---

## Key Features

### ✅ Automated Testing
- Frontend type checking and build
- Backend linting with ruff
- Unit tests with pytest

### 🏗️ Multi-Stage Build
- Optimized Docker images
- Layer caching for faster builds
- Multi-platform support

### 🔄 Zero Downtime
- Rolling updates
- Health checks before traffic switch
- Automatic rollback on failure

### 💾 Backup System
- Automatic backup before deployment
- Keep last 5 backups
- One-command rollback

### 📊 Monitoring
- Health check endpoints
- Real-time logs
- Deployment notifications

### 🔐 Security
- Secrets management via GitHub
- SSH key authentication
- No credentials in code

---

**Total Pipeline Time**: ~8-12 minutes from push to production
