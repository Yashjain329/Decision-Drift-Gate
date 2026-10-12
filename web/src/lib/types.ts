// Shapes of GET /api/state, taken from ddg/web.py and real payloads. Every field the engine may omit is optional:
// the UI must render "not recorded" rather than assume. Do not add fields the engine does not send.

export type Status = 'PASS' | 'FAIL' | 'ERROR';
export type Verdict = 'VIOLATION_INTRODUCED' | 'PRE_EXISTING_FAILURE' | 'RESOLVED' | 'CHECK_PASSED' | 'NOT_CHECKED' | 'HISTORICAL_CHECK_IGNORED';
export type Aggregate = 'PASSED_CHECKS' | 'FAILED' | 'INCOMPLETE';
export type ProposalMode = 'live' | 'recorded' | 'manual';

export interface Decision {
  id: string;
  rule?: string;
  status?: 'active' | 'superseded' | string;
  scope?: string;
  supersedes?: string | null;
  exceptions?: string[];
  schema_version?: number;
}

export interface Assertion { metric?: string; equals?: unknown }
export interface Citation { decision_id: string; quote: string }

export interface Check {
  id: string;
  decision_id?: string;
  supersedes?: string | null;
  adapter?: string;
  scenario?: string;
  rationale?: string;
  assertions?: Assertion[];
  citations?: Citation[];
  schema_version?: number;
}

export interface ServiceEvent {
  event?: 'submit' | 'accepted' | 'response' | 'lookup' | 'deduplicated' | string;
  call?: number;
  job_id?: string;
  operation_id?: string;
  status?: number;
  idempotency_key?: string | null;
}

export interface Observation {
  status?: Status;
  unique_jobs?: number | null;
  submit_calls?: number;
  returned_job_id?: string | null;
  returned_job_exists?: boolean;
  error?: string | null;
  events?: ServiceEvent[];
}

export interface Draft {
  check?: Check;
  decision?: Decision;
  draft_digest?: string;
  input_digest?: string;
  source_sha?: string;
  capture_source_sha?: string;
  captured_at?: string;
  model?: string;
  sdk_version?: string;
  adapter_version?: string;
  proposal_mode?: ProposalMode;
  attempts?: { attempt: number; result: string }[];
  request_metadata?: { provider?: string; model?: string; prompt_version?: string; timeout_seconds?: number; request_count?: number; response_format?: string; input_digest?: string };
  provider_response?: { status?: string; reason?: string };
}

export type FixtureKey = 'bad' | 'good' | 'exception';

export interface Validation {
  eligible?: boolean;
  cases?: Partial<Record<FixtureKey, { sha?: string; observation?: Observation }>>;
  calibration_hashes?: Partial<Record<FixtureKey, string>>;
  check_digest?: string;
  check_id?: string;
  draft_digest?: string;
  validated_at?: string;
  model?: string;
  proposal_mode?: ProposalMode;
}

export interface Approval {
  check_id?: string;
  reviewer?: string;
  reason?: string;
  approved_at?: string;
  bundle_digest?: string;
  validation_digest?: string;
  calibration_hashes?: Partial<Record<FixtureKey, string>>;
  schema_version?: number;
}

export interface ApproverCommit { commit?: string; author_email?: string; signature?: string; signer?: string }
export interface Approver { verified?: boolean; require_signed?: boolean; reason?: string; commits?: ApproverCommit[] }

export interface CheckResult {
  check_id: string;
  verdict?: Verdict | string;
  check?: Check;
  check_digest?: string;
  decision?: Decision;
  base?: Observation;
  head?: Observation;
  diff?: string;
  error?: string | null;
  approval?: Approval;
  approver?: Approver;
}

export interface Warning { code?: string; message?: string; detail?: string }

export interface Report {
  aggregate?: Aggregate | string;
  base_ref?: string;
  head_ref?: string;
  base_sha?: string;
  head_sha?: string;
  run_at?: string;
  sandbox?: 'docker' | 'podman' | 'host' | 'unavailable' | string;
  adapter_version?: string;
  checks?: CheckResult[];
  warnings?: Warning[];
  active_decisions?: Decision[];
  ordinary_tests?: { base?: Observation; head?: Observation };
}

export interface Scenario { id: string; label?: string }

export interface DdgState {
  lifecycle?: string;
  mode?: ProposalMode;
  old_decision?: Decision | null;
  new_decision?: Decision | null;
  draft?: Draft | null;
  validation?: Validation | null;
  approval?: Approval | null;
  report?: Report | null;
  report_stale?: boolean;
  scenarios?: Scenario[];
  busy?: boolean;
}

export type Route = 'propose' | 'validate' | 'approve' | 'run';
export type ViewId = 'overview' | 'decisions' | 'checks' | 'runs' | 'approvals' | 'reports' | 'settings';
