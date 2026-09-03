export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface HealthResponse {
  status: string;
  engine_version: string;
  database: string;
}

export interface BatchResponse {
  id: string;
  batch_number: string;
  content_hash: string;
  status: 'CREATED' | 'INGESTING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | string;
  engine_version: string;
  total_payments: number;
  total_settlements: number;
  total_bank_credits: number;
  total_refunds: number;
  auto_match_count: number;
  exception_count: number;
  disposition?: 'PROCESSED_NEW' | 'ALREADY_COMPLETED' | 'PREVIOUSLY_FAILED' | string | null;
  error_message?: string | null;
  metadata?: Record<string, any>;
  created_at: string;
  started_at?: string | null;
  processing_started_at?: string | null;
  completed_at?: string | null;
}

export interface ReconcileResultResponse {
  id: string;
  batch_id: string;
  rule_version: string;
  payment_id?: string | null;
  settlement_id?: string | null;
  bank_txn_id?: string | null;
  refund_id?: string | null;
  match_status: 'AUTO_MATCH' | 'EXCEPTION' | string;
  exception_type?: string | null;
  reason: string;
  financial_evidence?: Record<string, any>;
  created_at: string;
}

export interface ExceptionResponse {
  id: string;
  batch_id: string;
  reconciliation_result_id: string;
  category: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string;
  status: 'OPEN' | 'IN_REVIEW' | 'RESOLVED' | 'DISMISSED' | string;
  assigned_to?: string | null;
  resolution_reason?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
  payment_id?: string | null;
  settlement_id?: string | null;
}

export interface ExceptionDetailResponse extends ExceptionResponse {
  bank_txn_id?: string | null;
  engine_reason?: string | null;
  financial_evidence?: Record<string, any>;
}

export interface ExceptionPatchRequest {
  actor: string;
  status?: 'IN_REVIEW' | 'RESOLVED' | 'DISMISSED' | string | null;
  assigned_to?: string | null;
  resolution_reason?: string | null;
}

export interface AuditEventResponse {
  id: string;
  event_sequence: number;
  batch_id?: string | null;
  exception_id?: string | null;
  event_type: string;
  entity_type: string;
  entity_id: string;
  actor: string;
  action: string;
  before_state?: Record<string, any> | null;
  after_state?: Record<string, any> | null;
  reason: string;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface ApiErrorDetail {
  message?: string;
  batch?: BatchResponse;
  [key: string]: any;
}

export interface EvidenceItem {
  source_type: string;
  source_id: string;
  claim: string;
}

export interface CalculationSummary {
  captured_amount?: string | null;
  refund_amount?: string | null;
  fee_amount?: string | null;
  gst_amount?: string | null;
  expected_net?: string | null;
  settlement_net_amount?: string | null;
  bank_credit_amount?: string | null;
  variance_amount?: string | null;
  currency: string;
}

export interface ModelMetadata {
  provider: string;
  model_id: string;
  model_version: string;
  prompt_version: string;
}

export interface ValidationMetadata {
  schema_valid: boolean;
  evidence_ids_valid: boolean;
  grounding_valid: boolean;
  fallback_used: boolean;
  fallback_reason?: string | null;
}

export interface AIExplanationResponse {
  exception_id: string;
  status: string;
  advisory_only: boolean;
  model: ModelMetadata;
  summary: string;
  evidence: EvidenceItem[];
  calculation_summary: CalculationSummary;
  suggested_next_step: string;
  unknowns: string[];
  confidence: number;
  validation: ValidationMetadata;
}

export interface AIExplanationRequest {
  actor?: string;
}

export interface NarrationCandidateEvidence {
  extracted_reference_equals_settlement_id: boolean;
  amount_relation: string;
  date_relation: string;
  uniqueness: string;
}

export interface RankedCandidate {
  rank: number;
  settlement_id: string;
  payment_id?: string | null;
  deterministic_eligibility: string;
  evidence: NarrationCandidateEvidence;
  reasons: string[];
}

export interface NarrationExtractionResult {
  settlement_id_candidate?: string | null;
  utr_candidate?: string | null;
  confidence: number;
  unknowns: string[];
}

export interface ExtractionValidationMetadata {
  schema_valid: boolean;
  candidate_reference_valid: boolean;
  fallback_used: boolean;
  fallback_reason?: string | null;
}

export interface AINarrationCandidatesResponse {
  exception_id: string;
  advisory_only: boolean;
  financial_match_decision: string;
  extraction: NarrationExtractionResult;
  validation: ExtractionValidationMetadata;
  ranked_candidates: RankedCandidate[];
  safe_next_step: string;
}

export interface DeterministicReconciliationMetrics {
  dataset_name: string;
  sample_size: number;
  generator_version: string;
  seed?: number | null;
  auto_match_precision: number;
  auto_match_recall: number;
  auto_match_f1: number;
  incorrect_auto_match_count: number;
  total_scenarios_evaluated: number;
  auto_matches_emitted: number;
  exceptions_emitted: number;
  total_exception_rate: number;
  exception_rates_by_category: Record<string, number>;
  exception_breakdown_actual: Record<string, number>;
  latency_ms: number;
  throughput_records_per_minute: number;
  definitions: Record<string, string>;
  disclaimer: string;
}

export interface AIAdvisoryExtractionMetrics {
  dataset_name: string;
  sample_size: number;
  generator_version: string;
  settlement_id_precision: number;
  settlement_id_recall: number;
  settlement_id_f1: number;
  utr_precision: number;
  utr_recall: number;
  utr_f1: number;
  false_extraction_count: number;
  candidate_ranking_precision_at_1: number;
  candidate_ranking_recall_at_3: number;
  malformed_output_fallback_rate: number;
  unsafe_output_blocked_rate: number;
  disclaimer: string;
}

export interface HumanWorkflowMetrics {
  simulated_mean_time_to_resolution: string;
  auto_resolution_rate: string;
  disclaimer: string;
}

export interface EvaluationReportResponse {
  generated_at: string;
  deterministic_reconciliation: DeterministicReconciliationMetrics;
  ai_advisory_extraction: AIAdvisoryExtractionMetrics;
  human_workflow: HumanWorkflowMetrics;
}


