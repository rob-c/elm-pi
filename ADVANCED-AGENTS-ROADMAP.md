# Advanced Agents Roadmap: Autonomous Agents, Multi-Model Orchestration & Conflict Resolution

## Executive Summary

This roadmap outlines the implementation of three advanced capabilities for elm-pi:

1. **Autonomous Agents** - Semi-autonomous execution with goal-oriented behavior
2. **Multi-Model Orchestration** - Intelligent routing and cost optimization across models
3. **Conflict Resolution** - Detection and resolution of concurrent modifications

These features transform elm-pi from a reactive coding assistant into a proactive development partner capable of handling complex, multi-step tasks with minimal supervision while optimizing costs and maintaining code integrity.

---

## Phase 1: Multi-Model Orchestration (Weeks 1-4)

### Why Start Here?

Multi-model orchestration is foundational - it enables cost optimization for autonomous agents and provides the routing infrastructure needed for intelligent task delegation. It's also the lowest-risk feature with immediate ROI.

### 1.1 Model Capability Profiling

**Objective**: Build a dynamic model capability database

**Implementation**:
```typescript
// agent/extensions/model-orchestrator.ts

interface ModelProfile {
  id: string;
  provider: string;
  capabilities: {
    reasoning: boolean;
    codeGeneration: number;      // 0-10 score
    codeReview: number;          // 0-10 score
    documentation: number;       // 0-10 score
    simpleQueries: number;       // 0-10 score
    contextWindow: number;
    maxTokens: number;
    speed: 'fast' | 'medium' | 'slow';
    costPerToken: number;
  };
  performance: {
    avgLatency: number;          // ms
    successRate: number;         // 0-1
    tokenEfficiency: number;     // tokens per task
  };
}

// Pre-configured profiles for ELM models
const MODEL_PROFILES: ModelProfile[] = [
  {
    id: 'Qwen/Qwen3.5-397B-A17B-FP8',
    provider: 'elm',
    capabilities: {
      reasoning: true,
      codeGeneration: 9,
      codeReview: 9,
      documentation: 8,
      simpleQueries: 7,
      contextWindow: 262144,
      maxTokens: 32768,
      speed: 'medium',
      costPerToken: 2.0,  // ELM guidanceCost units
    },
    performance: {
      avgLatency: 3000,
      successRate: 0.95,
      tokenEfficiency: 0.8,
    }
  },
  {
    id: 'meta-llama/Llama-3.3-70B-Instruct',
    provider: 'elm-shim',
    capabilities: {
      reasoning: false,
      codeGeneration: 6,
      codeReview: 5,
      documentation: 7,
      simpleQueries: 8,
      contextWindow: 128000,
      maxTokens: 16384,
      speed: 'fast',
      costPerToken: 0.5,  // Estimated lower cost
    },
    performance: {
      avgLatency: 1500,
      successRate: 0.85,
      tokenEfficiency: 0.6,
    }
  }
];
```

**Deliverables**:
- [ ] Model profile schema and storage
- [ ] Pre-configured profiles for ELM models
- [ ] Performance tracking system (latency, success rate)
- [ ] Extension API for updating profiles

### 1.2 Task Classification System

**Objective**: Automatically categorize tasks by complexity and requirements

**Implementation**:
```typescript
enum TaskType {
  SIMPLE_QUERY = 'simple_query',           // Fact lookup, summarization
  CODE_READ = 'code_read',                 // Read and explain code
  CODE_WRITE = 'code_write',               // Generate new code
  CODE_REVIEW = 'code_review',             // Review existing code
  DEBUGGING = 'debugging',                 // Fix bugs
  REFACTORING = 'refactoring',             // Restructure code
  DOCUMENTATION = 'documentation',         // Write docs
  TESTING = 'testing',                     // Generate/run tests
  ARCHITECTURE = 'architecture',           // Design decisions
  MULTI_STEP = 'multi_step',               // Complex workflows
}

interface TaskProfile {
  type: TaskType;
  complexity: 'trivial' | 'simple' | 'moderate' | 'complex' | 'critical';
  requiresReasoning: boolean;
  requiresLongContext: boolean;
  estimatedTokens: number;
  toleranceForError: 'low' | 'medium' | 'high';
}

// Classification based on prompt analysis
function classifyTask(prompt: string, context: SessionContext): TaskProfile {
  // Use lightweight heuristics + small model call
  const keywords = {
    [TaskType.SIMPLE_QUERY]: ['what is', 'explain', 'summarize', 'list'],
    [TaskType.CODE_READ]: ['read', 'analyze', 'understand', 'how does'],
    [TaskType.CODE_WRITE]: ['create', 'implement', 'write', 'add function'],
    [TaskType.CODE_REVIEW]: ['review', 'check for', 'improve', 'issues in'],
    [TaskType.DEBUGGING]: ['fix', 'bug', 'error', 'not working', 'why fails'],
    [TaskType.REFACTORING]: ['refactor', 'restructure', 'optimize', 'clean up'],
    [TaskType.DOCUMENTATION]: ['document', 'comment', 'readme', 'api docs'],
    [TaskType.TESTING]: ['test', 'spec', 'coverage', 'unit test'],
    [TaskType.ARCHITECTURE]: ['design', 'architecture', 'pattern', 'strategy'],
    [TaskType.MULTI_STEP]: ['build', 'complete', 'implement feature'],
  };
  
  // Match keywords and analyze context
  // Return task profile with confidence score
}
```

**Deliverables**:
- [ ] Task classification algorithm
- [ ] Keyword-based heuristics
- [ ] Confidence scoring system
- [ ] Integration with sub-agent prompts

### 1.3 Intelligent Routing Engine

**Objective**: Route tasks to optimal model based on classification and profiles

**Implementation**:
```typescript
interface RoutingDecision {
  selectedModel: string;
  reason: string;
  alternatives: Array<{model: string; score: number}>;
  estimatedCost: number;
  estimatedLatency: number;
  confidence: number;
}

function selectOptimalModel(
  task: TaskProfile,
  profiles: ModelProfile[],
  constraints: RoutingConstraints
): RoutingDecision {
  const scores = profiles.map(profile => {
    let score = 0;
    
    // Capability matching (40% weight)
    if (task.requiresReasoning && !profile.capabilities.reasoning) {
      score -= 100;  // Hard constraint
    }
    score += profile.capabilities[codeTaskType] * 0.4;
    
    // Cost optimization (30% weight)
    const costScore = 1 / (profile.costPerToken * 0.3);
    score += costScore;
    
    // Performance (20% weight)
    score += profile.performance.successRate * 20;
    score -= (profile.performance.avgLatency / 1000) * 5;
    
    // Token efficiency (10% weight)
    score += profile.performance.tokenEfficiency * 10;
    
    // Apply constraints
    if (task.estimatedTokens > profile.capabilities.contextWindow) {
      score -= 50;
    }
    
    return { model: profile.id, score };
  });
  
  // Select highest scoring model
  // Return decision with explanation
}
```

**Deliverables**:
- [ ] Routing algorithm with weighted scoring
- [ ] Configurable weights (cost vs. speed vs. quality)
- [ ] Decision explanation for transparency
- [ ] Override mechanism for user control

### 1.4 Cost Tracking & Optimization

**Objective**: Monitor and optimize token usage and costs

**Implementation**:
```typescript
interface CostTracker {
  sessionCost: number;
  dailyCost: number;
  monthlyCost: number;
  costByProject: Map<string, number>;
  costByModel: Map<string, number>;
  costByTaskType: Map<TaskType, number>;
  
  budget: {
    daily: number;
    monthly: number;
    perTask: number;
  };
  
  alerts: Array<{
    type: 'budget_warning' | 'budget_exceeded' | 'anomaly';
    message: string;
    threshold: number;
    current: number;
  }>;
}

// Track every API call
function trackUsage(
  model: string,
  tokensIn: number,
  tokensOut: number,
  taskType: TaskType,
  project?: string
): void {
  const cost = calculateCost(model, tokensIn, tokensOut);
  updateCostTracker(cost, taskType, project);
  checkBudgetAlerts();
}

// Optimization suggestions
function generateOptimizationReport(): OptimizationReport {
  return {
    potentialSavings: identifySavingsOpportunities(),
    recommendations: [
      'Use Llama for simple queries (save ~60%)',
      'Enable caching for repeated lookups',
      'Batch sub-agent tasks during off-peak',
    ],
    projectedMonthlySavings: number,
  };
}
```

**Deliverables**:
- [ ] Real-time cost tracking
- [ ] Budget alerts and throttling
- [ ] Cost breakdown by project/model/task
- [ ] Optimization recommendations
- [ ] `/cost` command to view usage

### 1.5 User Interface & Controls

**Objective**: Provide transparency and user control

**Implementation**:
```typescript
// New commands
pi.registerCommand('model', {
  description: 'View or set model preferences',
  handler: async (args) => {
    // Show current routing rules
    // Allow manual override
    // Display model capabilities
  }
});

pi.registerCommand('cost', {
  description: 'View cost breakdown and budget',
  handler: async () => {
    // Show usage dashboard
    // Display optimization tips
  }
});

// Settings
interface OrchestratorSettings {
  mode: 'auto' | 'manual' | 'cost_optimized' | 'quality_first';
  maxCostPerTask: number;
  preferredModels: string[];
  enableCaching: boolean;
  budgetAlerts: boolean;
}
```

**Deliverables**:
- [ ] `/model` command enhancements
- [ ] `/cost` dashboard command
- [ ] Settings UI for routing preferences
- [ ] Real-time model selection indicators

---

## Phase 2: Autonomous Agents (Weeks 5-10)

### 2.1 Goal-Oriented Task Specification

**Objective**: Allow users to specify high-level goals rather than step-by-step instructions

**Implementation**:
```typescript
interface AutonomousTask {
  id: string;
  goal: string;                    // High-level objective
  constraints: string[];           // Boundaries and restrictions
  successCriteria: string[];       // Measurable outcomes
  priority: 'low' | 'medium' | 'high' | 'critical';
  deadline?: Date;
  budget?: {
    maxTokens: number;
    maxCost: number;
    maxTimeMs: number;
  };
  allowedTools?: string[];         // Restrict available tools
  forbiddenPaths?: string[];       // Off-limits files/directories
}

// Example usage:
// /autonomous "Add user authentication to the app"
//   --constraint "Use existing session management"
//   --constraint "No external dependencies"
//   --success "Login works with valid credentials"
//   --success "Invalid credentials show error"
//   --success "Password not stored in plaintext"
//   --budget-tokens 50000
//   --priority high
```

**Deliverables**:
- [ ] Autonomous task schema
- [ ] Natural language goal parser
- [ ] Constraint extraction from prompts
- [ ] Success criteria validation framework

### 2.2 Planning & Decomposition Engine

**Objective**: Break high-level goals into executable sub-tasks

**Implementation**:
```typescript
interface Plan {
  taskId: string;
  goal: string;
  steps: PlanStep[];
  dependencies: Map<string, string[]>;  // stepId -> prerequisite stepIds
  criticalPath: string[];
  estimatedCost: number;
  estimatedTime: number;
  risks: PlanRisk[];
}

interface PlanStep {
  id: string;
  description: string;
  type: 'research' | 'design' | 'implement' | 'test' | 'review';
  model: string;                    // Routed by orchestrator
  inputDependencies: string[];      // Outputs from other steps
  outputArtifacts: string[];        // Files/results produced
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked';
  retries: number;
}

interface PlanRisk {
  stepId: string;
  risk: string;
  probability: 'low' | 'medium' | 'high';
  impact: 'low' | 'medium' | 'high';
  mitigation: string;
}

// Planning algorithm
async function createPlan(task: AutonomousTask): Promise<Plan> {
  // Use Qwen to decompose goal into steps
  const planningPrompt = `
    Break down this goal into concrete, executable steps:
    Goal: ${task.goal}
    Constraints: ${task.constraints.join(', ')}
    Success criteria: ${task.successCriteria.join(', ')}
    
    For each step, specify:
    1. What needs to be done
    2. What files will be read/modified
    3. What model is best suited (Qwen for complex, Llama for simple)
    4. Dependencies on other steps
    5. Potential risks
  `;
  
  // Parse response into structured plan
  // Validate plan feasibility
  // Estimate costs and time
  // Identify critical path
}
```

**Deliverables**:
- [ ] Goal decomposition algorithm
- [ ] Step dependency graph
- [ ] Risk assessment framework
- [ ] Cost and time estimation
- [ ] Plan validation (check for circular deps, impossible steps)

### 2.3 Execution Engine with Checkpoints

**Objective**: Execute plans with progress tracking and recovery

**Implementation**:
```typescript
class AutonomousExecutor {
  private plan: Plan;
  private state: ExecutionState;
  private checkpoints: Checkpoint[];
  
  async execute(): Promise<ExecutionResult> {
    while (!this.isComplete()) {
      const nextStep = this.getNextExecutableStep();
      
      if (!nextStep) {
        if (this.hasBlockedSteps()) {
          await this.resolveBlockingIssue();
          continue;
        }
        break;  // All steps complete
      }
      
      // Create checkpoint before execution
      const checkpoint = await this.createCheckpoint(nextStep);
      
      try {
        const result = await this.executeStep(nextStep);
        
        // Validate result against success criteria
        const validated = await this.validateStepResult(nextStep, result);
        
        if (!validated.success) {
          throw new StepValidationError(validated.issues);
        }
        
        nextStep.status = 'completed';
        this.saveCheckpoint(checkpoint, 'success');
        
      } catch (error) {
        nextStep.retries++;
        
        if (nextStep.retries > MAX_RETRIES) {
          nextStep.status = 'failed';
          this.saveCheckpoint(checkpoint, 'failed', error);
          
          // Attempt recovery
          const recovery = await this.attemptRecovery(nextStep, error);
          if (!recovery.success) {
            await this.requestHumanIntervention(nextStep, error);
          }
        } else {
          // Retry with backoff
          await this.delayWithBackoff(nextStep.retries);
        }
      }
      
      // Report progress
      this.reportProgress();
    }
    
    return this.generateResult();
  }
  
  private async executeStep(step: PlanStep): Promise<StepResult> {
    // Route to appropriate model via orchestrator
    const model = this.orchestrator.selectModel(step);
    
    // Create sub-agent with specific instructions
    const subagent = await pi.subagent({
      model,
      task: step.description,
      context: this.getStepContext(step),
      tools: step.allowedTools,
    });
    
    return await subagent.output;
  }
}
```

**Deliverables**:
- [ ] Step execution engine
- [ ] Checkpoint system (save state after each step)
- [ ] Retry logic with exponential backoff
- [ ] Error recovery strategies
- [ ] Human intervention protocol

### 2.4 Progress Monitoring & Reporting

**Objective**: Keep users informed without overwhelming them

**Implementation**:
```typescript
interface ProgressReport {
  taskId: string;
  goal: string;
  overallProgress: number;        // 0-100%
  currentStep: PlanStep | null;
  completedSteps: number;
  totalSteps: number;
  status: 'running' | 'paused' | 'blocked' | 'completed' | 'failed';
  elapsed: number;                // ms
  estimatedRemaining: number;     // ms
  costSoFar: number;
  issues: Issue[];
  nextCheckpoint: Date;
}

interface Issue {
  severity: 'info' | 'warning' | 'error' | 'critical';
  stepId: string;
  message: string;
  requiresAction: boolean;
  suggestedAction?: string;
}

// Notification levels
enum NotificationLevel {
  SILENT = 'silent',              // No notifications
  MILESTONES_ONLY = 'milestones', // Only step completion
  ISSUES = 'issues',              // Problems + milestones
  VERBOSE = 'verbose',            // Every step
}

// Commands
pi.registerCommand('status', {
  description: 'Show autonomous task progress',
  handler: async () => {
    // Display progress dashboard
    // Show current step, completed steps, issues
  }
});

pi.registerCommand('pause', {
  description: 'Pause autonomous execution',
  handler: async () => {
    // Save checkpoint and pause
  }
});

pi.registerCommand('resume', {
  description: 'Resume paused execution',
  handler: async () => {
    // Restore from checkpoint and continue
  }
});
```

**Deliverables**:
- [ ] Progress dashboard (`/status` command)
- [ ] Configurable notification levels
- [ ] Real-time progress updates
- [ ] Estimated completion time
- [ ] Cost tracking during execution

### 2.5 Human Intervention Protocol

**Objective**: Know when to ask for help and how to ask effectively

**Implementation**:
```typescript
interface InterventionRequest {
  taskId: string;
  stepId: string;
  reason: 'blocked' | 'ambiguous' | 'high_risk' | 'budget_exceeded' | 'ethical_concern';
  context: {
    whatWasAttempted: string;
    whatWentWrong: string;
    optionsConsidered: string[];
    recommendation?: string;
  };
  urgency: 'low' | 'medium' | 'high' | 'critical';
  deadline?: Date;  // When intervention is needed by
}

// Intervention scenarios
const INTERVENTION_TRIGGERS = {
  BLOCKED: {
    condition: (step) => step.retries >= MAX_RETRIES,
    message: 'Step blocked after multiple retries',
    requiredInfo: ['error_details', 'attempted_solutions', 'blocking_factor'],
  },
  AMBIGUOUS: {
    condition: (step) => step.requiresClarification,
    message: 'Multiple valid approaches detected',
    requiredInfo: ['options', 'trade_offs', 'recommendation'],
  },
  HIGH_RISK: {
    condition: (step) => step.modifiesCriticalFiles,
    message: 'Step modifies critical system files',
    requiredInfo: ['files_affected', 'backup_status', 'rollback_plan'],
  },
  BUDGET_EXCEEDED: {
    condition: (task) => task.costSoFar > task.budget.maxCost * 0.8,
    message: 'Approaching budget limit',
    requiredInfo: ['current_cost', 'estimated_total', 'options'],
  },
};

// Request format
function formatInterventionRequest(request: InterventionRequest): string {
  return `
🚨 **Human Intervention Required**

**Task**: ${request.taskId}
**Step**: ${request.stepId}
**Reason**: ${request.reason}
**Urgency**: ${request.urgency}

**Context**:
${request.context.whatWasAttempted}

**Problem**:
${request.context.whatWentWrong}

**Options Considered**:
${request.context.optionsConsidered.map(o => `- ${o}`).join('\n')}

**Recommendation**:
${request.context.recommendation || 'No recommendation available'}

**To respond**:
- Reply with your decision
- Use /approve to continue
- Use /abort to cancel task
- Use /modify to suggest alternative
  `.trim();
}
```

**Deliverables**:
- [ ] Intervention trigger detection
- [ ] Request formatting system
- [ ] Response handling (`/approve`, `/abort`, `/modify`)
- [ ] Escalation protocol for critical issues
- [ ] Intervention logging for learning

### 2.6 Learning from Interventions

**Objective**: Improve autonomous behavior based on human feedback

**Implementation**:
```typescript
interface InterventionLearning {
  taskId: string;
  interventionType: string;
  rootCause: string;
  resolution: string;
  lessonLearned: string;
  applicableTo: string[];  // Task types this applies to
  confidence: number;
}

// Update planning heuristics based on interventions
function learnFromIntervention(intervention: InterventionLearning): void {
  // Update risk assessments
  updateRiskModels(intervention);
  
  // Adjust planning patterns
  if (intervention.rootCause === 'insufficient_research') {
    addPlanningRule({
      condition: (task) => task.involvesUnknownTechnology,
      action: 'add_research_step',
    });
  }
  
  // Update model selection
  if (intervention.rootCause === 'model_limitation') {
    adjustModelWeights(intervention);
  }
  
  // Store lesson for future reference
  saveLesson(intervention);
}
```

**Deliverables**:
- [ ] Intervention logging
- [ ] Pattern recognition in failures
- [ ] Heuristic adjustment system
- [ ] Lesson storage and retrieval

---

## Phase 3: Conflict Resolution (Weeks 11-14)

### 3.1 Conflict Detection System

**Objective**: Detect concurrent modifications before they cause problems

**Implementation**:
```typescript
interface FileState {
  path: string;
  lastReadHash: string;
  lastWriteHash: string;
  lastReadTime: Date;
  lastWriteTime: Date;
  readBySession?: string;
  writtenBySession?: string;
}

interface Conflict {
  id: string;
  file: string;
  type: 'concurrent_edit' | 'stale_read' | 'overlapping_change';
  severity: 'warning' | 'error' | 'critical';
  detectedAt: Date;
  sessions: string[];
  descriptions: {
    sessionId: string;
    changeDescription: string;
    timestamp: Date;
  }[];
  resolution?: ConflictResolution;
}

class ConflictDetector {
  private fileStates: Map<string, FileState>;
  private activeSessions: Set<string>;
  
  async checkForConflicts(
    sessionId: string,
    operation: 'read' | 'write',
    filePath: string
  ): Promise<Conflict | null> {
    const currentState = await this.getFileState(filePath);
    const currentHash = await this.hashFile(filePath);
    
    if (operation === 'write') {
      // Check if file changed since last read
      if (currentState.lastReadHash !== currentHash) {
        const conflict: Conflict = {
          id: generateId(),
          file: filePath,
          type: 'stale_read',
          severity: 'error',
          detectedAt: new Date(),
          sessions: [sessionId, currentState.writtenBySession!],
          descriptions: [
            {
              sessionId,
              changeDescription: 'Attempting to write based on stale read',
              timestamp: new Date(),
            },
            {
              sessionId: currentState.writtenBySession!,
              changeDescription: 'File was modified by another session',
              timestamp: currentState.lastWriteTime,
            },
          ],
        };
        
        await this.logConflict(conflict);
        return conflict;
      }
      
      // Check for concurrent writes
      if (this.isBeingWrittenByAnother(sessionId, filePath)) {
        // Handle concurrent write conflict
      }
    }
    
    return null;
  }
}
```

**Deliverables**:
- [ ] File state tracking system
- [ ] Hash-based change detection
- [ ] Concurrent write detection
- [ ] Stale read detection
- [ ] Conflict logging

### 3.2 Three-Way Merge Engine

**Objective**: Automatically resolve non-overlapping changes

**Implementation**:
```typescript
interface MergeResult {
  success: boolean;
  mergedContent?: string;
  conflicts?: MergeConflict[];
  statistics: {
    linesAdded: number;
    linesDeleted: number;
    linesModified: number;
    conflictRegions: number;
  };
}

interface MergeConflict {
  startLine: number;
  endLine: number;
  originalContent: string;
  change1: string;
  change2: string;
  suggestion?: string;
  confidence: number;
}

async function threeWayMerge(
  base: string,
  change1: string,
  change2: string,
  filePath: string
): Promise<MergeResult> {
  // Use ast-grep for syntax-aware merging
  const baseAst = await parseToAST(base, filePath);
  const change1Ast = await parseToAST(change1, filePath);
  const change2Ast = await parseToAST(change2, filePath);
  
  // Find differences
  const diffs1 = findDiffs(baseAst, change1Ast);
  const diffs2 = findDiffs(baseAst, change2Ast);
  
  // Check for overlaps
  const overlaps = findOverlaps(diffs1, diffs2);
  
  if (overlaps.length === 0) {
    // Non-overlapping changes - auto-merge
    const merged = applyChanges(base, [...diffs1, ...diffs2]);
    return {
      success: true,
      mergedContent: merged,
      statistics: calculateStatistics(diffs1, diffs2),
    };
  }
  
  // Overlapping changes - attempt intelligent resolution
  const conflicts: MergeConflict[] = [];
  for (const overlap of overlaps) {
    const conflict = await analyzeConflict(overlap, base, change1, change2);
    
    // Try to auto-resolve with AI
    const resolution = await attemptAutoResolution(conflict);
    
    if (resolution.confidence > 0.9) {
      // High confidence - auto-resolve
      applyResolution(conflict, resolution);
    } else {
      // Low confidence - mark for manual resolution
      conflicts.push({
        ...conflict,
        suggestion: resolution.suggestion,
        confidence: resolution.confidence,
      });
    }
  }
  
  if (conflicts.length === 0) {
    return {
      success: true,
      mergedContent: applyAllResolutions(base, overlaps),
      statistics: calculateStatistics(diffs1, diffs2),
    };
  }
  
  return {
    success: false,
    conflicts,
    statistics: calculateStatistics(diffs1, diffs2),
  };
}
```

**Deliverables**:
- [ ] AST-based diff detection
- [ ] Overlap identification algorithm
- [ ] Auto-merge for non-overlapping changes
- [ ] AI-powered conflict resolution
- [ ] Confidence scoring for resolutions

### 3.3 User-Guided Resolution UI

**Objective**: Help users resolve conflicts quickly and correctly

**Implementation**:
```typescript
// New command for conflict resolution
pi.registerCommand('resolve', {
  description: 'Resolve file conflicts',
  handler: async (args) => {
    const conflicts = await getUnresolvedConflicts();
    
    if (conflicts.length === 0) {
      ui.notify('No conflicts to resolve', 'info');
      return;
    }
    
    // Display conflict resolution UI
    await ui.custom((tui, theme) => {
      return new ConflictResolutionUI(conflicts, theme);
    });
  }
});

class ConflictResolutionUI {
  renderConflict(conflict: MergeConflict): string[] {
    return [
      '',
      `⚠️  Conflict at lines ${conflict.startLine}-${conflict.endLine}`,
      '',
      'Original:',
      ...this.syntaxHighlight(conflict.originalContent),
      '',
      'Change 1:',
      ...this.syntaxHighlight(conflict.change1),
      '',
      'Change 2:',
      ...this.syntaxHighlight(conflict.change2),
      '',
      'Suggested resolution:',
      ...this.syntaxHighlight(conflict.suggestion || 'No suggestion available'),
      '',
      'Options:',
      '  [1] Accept Change 1',
      '  [2] Accept Change 2',
      '  [3] Accept suggestion',
      '  [4] Manual edit',
      '  [5] Keep original',
      '  [q] Skip for now',
      '',
    ];
  }
  
  async handleInput(key: string): Promise<void> {
    switch (key) {
      case '1':
        await this.acceptChange(1);
        break;
      case '2':
        await this.acceptChange(2);
        break;
      case '3':
        await this.acceptSuggestion();
        break;
      case '4':
        await this.openManualEditor();
        break;
      case '5':
        await this.keepOriginal();
        break;
    }
  }
}
```

**Deliverables**:
- [ ] Interactive conflict resolution UI
- [ ] Side-by-side diff view
- [ ] Syntax highlighting
- [ ] Quick-select options
- [ ] Manual edit fallback

### 3.4 Version History & Rollback

**Objective**: Track changes and enable safe rollback

**Implementation**:
```typescript
interface VersionEntry {
  id: string;
  filePath: string;
  timestamp: Date;
  sessionId: string;
  taskId?: string;
  changeType: 'create' | 'modify' | 'delete';
  beforeHash?: string;
  afterHash: string;
  changeDescription: string;
  beforeContent?: string;  // For recent versions
  afterContent: string;
}

class VersionTracker {
  private history: Map<string, VersionEntry[]>;  // filePath -> versions
  
  async recordChange(
    filePath: string,
    before: string,
    after: string,
    sessionId: string,
    taskId?: string
  ): Promise<void> {
    const entry: VersionEntry = {
      id: generateId(),
      filePath,
      timestamp: new Date(),
      sessionId,
      taskId,
      changeType: before ? 'modify' : 'create',
      beforeHash: await this.hash(before),
      afterHash: await this.hash(after),
      changeDescription: await this.generateChangeDescription(before, after),
      beforeContent: before,
      afterContent: after,
    };
    
    await this.saveVersion(entry);
    
    // Prune old versions (keep last 50 per file)
    await this.pruneOldVersions(filePath, 50);
  }
  
  async rollback(filePath: string, toVersion: string): Promise<void> {
    const versions = this.history.get(filePath) || [];
    const targetVersion = versions.find(v => v.id === toVersion);
    
    if (!targetVersion) {
      throw new Error('Version not found');
    }
    
    // Create rollback version
    await this.recordChange(
      filePath,
      await this.readFile(filePath),
      targetVersion.afterContent,
      'rollback',
      undefined
    );
    
    // Apply rollback
    await this.writeFile(filePath, targetVersion.afterContent);
  }
  
  async showHistory(filePath: string): Promise<void> {
    const versions = this.getRecentVersions(filePath, 20);
    
    // Display version history
    const history = versions.map((v, i) => ({
      index: i + 1,
      id: v.id,
      timestamp: v.timestamp,
      changeType: v.changeType,
      description: v.changeDescription,
      sessionId: v.sessionId,
    }));
    
    await ui.displayHistory(history);
  }
}

// Commands
pi.registerCommand('history', {
  description: 'Show file version history',
  handler: async (args) => {
    await versionTracker.showHistory(args.file);
  }
});

pi.registerCommand('rollback', {
  description: 'Rollback file to previous version',
  handler: async (args) => {
    await versionTracker.rollback(args.file, args.version);
  }
});
```

**Deliverables**:
- [ ] Version tracking system
- [ ] Automatic change recording
- [ ] Version history display (`/history`)
- [ ] Rollback functionality (`/rollback`)
- [ ] Storage optimization (pruning, compression)

### 3.5 Prevention Strategies

**Objective**: Prevent conflicts before they occur

**Implementation**:
```typescript
interface PreventionStrategy {
  name: string;
  description: string;
  enabled: boolean;
  apply: (context: OperationContext) => PreventionResult;
}

const PREVENTION_STRATEGIES = {
  FILE_LOCKING: {
    name: 'File Locking',
    description: 'Lock files during editing to prevent concurrent modifications',
    enabled: true,
    apply: async (context) => {
      const isLocked = await this.isFileLocked(context.filePath);
      
      if (isLocked && isLocked.by !== context.sessionId) {
        return {
          prevent: true,
          reason: `File is locked by session ${isLocked.by}`,
          suggestion: 'Wait for other session to complete or use /force-edit',
        };
      }
      
      await this.lockFile(context.filePath, context.sessionId);
      return { prevent: false };
    },
  },
  
  READ_BEFORE_WRITE: {
    name: 'Read Before Write',
    description: 'Re-read file immediately before writing to detect changes',
    enabled: true,
    apply: async (context) => {
      const currentHash = await hashFile(context.filePath);
      
      if (currentHash !== context.expectedHash) {
        return {
          prevent: true,
          reason: 'File has changed since last read',
          suggestion: 'Re-read file and re-apply changes',
        };
      }
      
      return { prevent: false };
    },
  },
  
  STAGING_AREA: {
    name: 'Staging Area',
    description: 'Write to temporary file first, then atomic rename',
    enabled: true,
    apply: async (context) => {
      // Write to .filename.tmp
      // Verify write succeeded
      // Atomic rename to filename
      return { prevent: false };
    },
  },
  
  SESSION_AWARENESS: {
    name: 'Session Awareness',
    description: 'Notify when multiple sessions are editing same file',
    enabled: true,
    apply: async (context) => {
      const otherSessions = this.getOtherSessionsEditing(context.filePath);
      
      if (otherSessions.length > 0) {
        return {
          prevent: false,
          warning: `Other sessions editing this file: ${otherSessions.join(', ')}`,
          suggestion: 'Consider coordinating with other sessions',
        };
      }
      
      return { prevent: false };
    },
  },
};
```

**Deliverables**:
- [ ] File locking mechanism
- [ ] Read-before-write verification
- [ ] Atomic write operations
- [ ] Multi-session awareness
- [ ] Configurable prevention strategies

---

## Phase 4: Integration & Polish (Weeks 15-16)

### 4.1 Feature Integration

**Objective**: Ensure all three features work together seamlessly

**Integration Points**:

1. **Autonomous Agents + Multi-Model Orchestration**
   - Autonomous tasks use orchestrator for model selection
   - Cost tracking includes autonomous task execution
   - Planning considers model capabilities and costs

2. **Autonomous Agents + Conflict Resolution**
   - Autonomous agents check for conflicts before writing
   - Conflicts trigger human intervention
   - Version history tracks autonomous changes

3. **Multi-Model Orchestration + Conflict Resolution**
   - Conflict resolution uses best model for merge quality
   - Cost tracking includes merge operations
   - Model selection considers conflict complexity

### 4.2 Documentation & Examples

**Deliverables**:
- [ ] User guide for each feature
- [ ] Tutorial: "Your First Autonomous Task"
- [ ] Tutorial: "Optimizing Costs with Multi-Model Routing"
- [ ] Tutorial: "Resolving Conflicts Like a Pro"
- [ ] API reference for extension developers
- [ ] Best practices guide
- [ ] Troubleshooting guide

### 4.3 Testing & Validation

**Deliverables**:
- [ ] Unit tests for all components
- [ ] Integration tests for feature combinations
- [ ] Performance benchmarks
- [ ] Cost analysis validation
- [ ] User acceptance testing
- [ ] Edge case coverage

### 4.4 Performance Optimization

**Focus Areas**:
- [ ] Reduce planning overhead
- [ ] Optimize conflict detection algorithms
- [ ] Cache model performance data
- [ ] Minimize version tracking storage
- [ ] Parallelize independent operations

---

## Success Metrics

### Multi-Model Orchestration
- **Cost Reduction**: 30-50% reduction in token costs for mixed workloads
- **Latency**: <100ms routing decision overhead
- **Accuracy**: >90% correct model selection (user-validated)
- **Adoption**: >80% of tasks use automatic routing

### Autonomous Agents
- **Completion Rate**: >70% of autonomous tasks complete without intervention
- **Intervention Frequency**: <1 intervention per 10 steps
- **Time Savings**: 50% reduction in user time for complex tasks
- **User Satisfaction**: >4/5 rating in user surveys

### Conflict Resolution
- **Detection Rate**: 100% of concurrent edits detected
- **Auto-Resolution**: >60% of conflicts resolved automatically
- **Resolution Time**: <2 minutes for manual resolutions
- **Data Loss**: Zero unreported conflicts resulting in data loss

---

## Risks & Mitigations

### Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Model routing makes poor choices | High | Medium | Human override, continuous learning from feedback |
| Autonomous agents make costly mistakes | High | Medium | Budget limits, human intervention triggers, checkpoints |
| Conflict detection has false negatives | Critical | Low | Conservative detection, multiple detection strategies |
| Performance overhead too high | Medium | Medium | Aggressive optimization, caching, lazy evaluation |

### User Adoption Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Users don't trust autonomous agents | High | High | Gradual rollout, transparency, user control |
| Cost tracking causes anxiety | Medium | Medium | Clear communication, optimization tips, budget controls |
| Conflict resolution UI too complex | Medium | Medium | Intuitive design, tutorials, sensible defaults |

---

## Implementation Timeline

```
Week 1-4:   Multi-Model Orchestration
  Week 1:   Model profiling & capability database
  Week 2:   Task classification system
  Week 3:   Routing engine & cost tracking
  Week 4:   UI controls & documentation

Week 5-10:  Autonomous Agents
  Week 5:   Goal specification & parsing
  Week 6:   Planning & decomposition
  Week 7:   Execution engine
  Week 8:   Checkpoints & recovery
  Week 9:   Progress monitoring & reporting
  Week 10:  Human intervention protocol

Week 11-14: Conflict Resolution
  Week 11:  Conflict detection system
  Week 12:  Three-way merge engine
  Week 13:  Resolution UI & version history
  Week 14:  Prevention strategies

Week 15-16: Integration & Polish
  Week 15:  Feature integration & testing
  Week 16:  Documentation, examples, release
```

---

## Resource Requirements

### Development Team
- 2-3 full-stack developers (TypeScript, Node.js)
- 1 ML engineer (model orchestration, planning algorithms)
- 1 UX designer (conflict resolution UI, progress dashboards)
- 1 technical writer (documentation, tutorials)

### Infrastructure
- Development ELM API budget for testing
- Test environments for concurrent session testing
- Performance testing infrastructure
- User testing recruitment and coordination

### External Dependencies
- ELM API stability and feature availability
- ast-grep for AST-based merging
- pi extension API capabilities
- Community feedback and adoption

---

## Next Steps

### Immediate (Week 0)
1. **Stakeholder Review**: Present this roadmap for feedback and prioritization
2. **Resource Allocation**: Secure development team and budget
3. **Technical Spikes**: Validate key assumptions (model routing accuracy, merge quality)
4. **User Research**: Interview potential users about autonomous agent comfort levels

### Short-term (Month 1)
1. Begin Phase 1 implementation (Multi-Model Orchestration)
2. Set up development infrastructure
3. Create detailed technical specifications
4. Establish metrics collection framework

### Medium-term (Months 2-4)
1. Complete Phases 2-3 (Autonomous Agents, Conflict Resolution)
2. Begin user testing with early adopters
3. Iterate based on feedback
4. Prepare documentation and examples

### Long-term (Months 5-6)
1. Complete Phase 4 (Integration & Polish)
2. Public release with marketing
3. Community engagement and feedback collection
4. Plan next iteration based on usage patterns

---

## Appendix A: Example Workflows

### A.1 Autonomous Task Example

```bash
# User initiates autonomous task
$ pi /autonomous "Add user registration to the app"
  --constraint "Use existing PostgreSQL database"
  --constraint "Follow existing code style"
  --success "User can register with email and password"
  --success "Password is hashed before storage"
  --success "Duplicate emails are rejected"
  --success "Confirmation email is sent"
  --budget-cost 50
  --priority high

# System responds with plan
📋 **Autonomous Task Plan Created**

**Goal**: Add user registration to the app
**Estimated Cost**: 35 ELM units
**Estimated Time**: 25 minutes
**Steps**: 8

1. [Research] Read existing user model and database schema (Llama)
2. [Design] Plan registration flow and API endpoints (Qwen)
3. [Implement] Create registration endpoint (Qwen)
4. [Implement] Add password hashing utility (Qwen)
5. [Implement] Add email validation (Llama)
6. [Implement] Add duplicate email check (Llama)
7. [Test] Write integration tests (Qwen)
8. [Review] Code review and security check (Qwen)

**Risks**:
- Step 3: Modifies API routes (medium risk)
- Step 4: Handles sensitive data (high risk)

Start execution? [y/n] y

# Progress updates
✓ Step 1/8 completed (Research) - 2 min, 1.2 units
✓ Step 2/8 completed (Design) - 3 min, 2.5 units
⚠ Step 3/8 requires intervention: Multiple routing options found
  Option 1: Express.js router (matches existing pattern)
  Option 2: Fastify router (better performance)
  Option 3: Next.js API routes (if migrating)
  Recommendation: Option 1 (lowest risk)
  
  Select option [1-3] or /abort: 1

✓ Step 3/8 completed (Implement) - 5 min, 4.1 units
...

✅ **Task Completed Successfully**
Total time: 23 minutes
Total cost: 32.4 ELM units
Files modified: 5
Tests added: 12
```

### A.2 Multi-Model Routing Example

```bash
# User queries model selection
$ pi /model

**Current Routing Mode**: Auto (Cost-Optimized)

**Active Models**:
1. Qwen 3.5 397B (elm)
   - Best for: Complex reasoning, code generation, reviews
   - Cost: 2.0 units/1K tokens
   - Avg latency: 3.0s
   
2. Llama 3.3 70B (elm-shim)
   - Best for: Simple queries, summarization, documentation
   - Cost: 0.5 units/1K tokens
   - Avg latency: 1.5s

**Recent Routing Decisions**:
- "Fix null pointer in user service" → Qwen (code debugging)
- "Summarize this PR" → Llama (summarization)
- "Add unit tests for auth module" → Qwen (test generation)
- "What's the weather?" → Llama (simple query)

**Cost Savings This Week**: 18.5 units (37% vs. Qwen-only)

# Change routing mode
$ pi /model --mode quality-first
✓ Routing mode set to "Quality First"
  All tasks will use highest-capability model regardless of cost

# Set budget
$ pi /model --budget-daily 100
✓ Daily budget set to 100 ELM units
  You will be notified at 80% usage
```

### A.3 Conflict Resolution Example

```bash
# User encounters conflict
$ pi /resolve

⚠️  **2 Conflicts Detected**

**Conflict 1**: src/auth/login.ts
  Type: Concurrent edit (stale read)
  Sessions: session-abc (you), session-xyz (another)
  
  Your changes:
  + Added rate limiting
  
  Other changes:
  + Added logging
  + Fixed typo in error message
  
  🤖 Suggestion: Auto-merge (non-overlapping changes)
  Confidence: 95%
  
  Options:
  [1] Accept auto-merge
  [2] View detailed diff
  [3] Manual resolution
  [s] Skip for now

# User accepts auto-merge
> 1

✓ Conflict resolved: src/auth/login.ts
  Applied auto-merge (95% confidence)
  
**Conflict 2**: src/utils/helpers.ts
  Type: Overlapping changes
  Sessions: session-abc (you), session-def (another)
  
  Your changes:
  - function formatDate(date) {
  + function formatDate(date, format = 'YYYY-MM-DD') {
  
  Other changes:
  - function formatDate(date) {
  + function formatDate(date: Date): string {
  
  🤖 Suggestion: Combine both changes
  function formatDate(date: Date, format = 'YYYY-MM-DD'): string {
  
  Confidence: 78%
  
  Options:
  [1] Accept suggestion
  [2] View detailed diff
  [3] Manual resolution
  [4] Keep your version
  [5] Keep their version
  [s] Skip for now

# User views detailed diff
> 2

[Displays side-by-side diff with syntax highlighting]

# User accepts suggestion
> 1

✓ Conflict resolved: src/utils/helpers.ts
  Applied suggested merge (78% confidence)

✅ **All conflicts resolved**
```

---

## Appendix B: Technical Specifications

### B.1 Model Profile Schema

```typescript
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ModelProfile",
  "type": "object",
  "required": ["id", "provider", "capabilities", "performance"],
  "properties": {
    "id": { "type": "string" },
    "provider": { "type": "string" },
    "capabilities": {
      "type": "object",
      "properties": {
        "reasoning": { "type": "boolean" },
        "codeGeneration": { "type": "integer", "minimum": 0, "maximum": 10 },
        "codeReview": { "type": "integer", "minimum": 0, "maximum": 10 },
        "documentation": { "type": "integer", "minimum": 0, "maximum": 10 },
        "simpleQueries": { "type": "integer", "minimum": 0, "maximum": 10 },
        "contextWindow": { "type": "integer" },
        "maxTokens": { "type": "integer" },
        "speed": { "type": "string", "enum": ["fast", "medium", "slow"] },
        "costPerToken": { "type": "number" }
      }
    },
    "performance": {
      "type": "object",
      "properties": {
        "avgLatency": { "type": "number" },
        "successRate": { "type": "number", "minimum": 0, "maximum": 1 },
        "tokenEfficiency": { "type": "number" }
      }
    }
  }
}
```

### B.2 Autonomous Task Schema

```typescript
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AutonomousTask",
  "type": "object",
  "required": ["id", "goal", "successCriteria"],
  "properties": {
    "id": { "type": "string" },
    "goal": { "type": "string" },
    "constraints": { "type": "array", "items": { "type": "string" } },
    "successCriteria": { "type": "array", "items": { "type": "string" } },
    "priority": { "type": "string", "enum": ["low", "medium", "high", "critical"] },
    "deadline": { "type": "string", "format": "date-time" },
    "budget": {
      "type": "object",
      "properties": {
        "maxTokens": { "type": "integer" },
        "maxCost": { "type": "number" },
        "maxTimeMs": { "type": "integer" }
      }
    },
    "allowedTools": { "type": "array", "items": { "type": "string" } },
    "forbiddenPaths": { "type": "array", "items": { "type": "string" } }
  }
}
```

---

**Document Version**: 1.0  
**Created**: $(date)  
**Status**: Draft for Review  
**Next Review**: Stakeholder feedback session
