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
