import {
  AuditEventResponse,
  BatchResponse,
  ExceptionDetailResponse,
  ExceptionPatchRequest,
  ExceptionResponse,
  HealthResponse,
  PaginatedResponse,
  ReconcileResultResponse,
} from './types';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  status: number;
  detail: any;

  constructor(status: number, detail: any, message?: string) {
    const errorMsg =
      typeof detail === 'string'
        ? detail
        : detail?.message || detail?.detail || message || `HTTP Error ${status}`;
    super(errorMsg);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, options);

  let data: any;
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const detail = typeof data === 'object' && data.detail !== undefined ? data.detail : data;
    throw new ApiError(response.status, detail);
  }

  return data as T;
}

export const api = {
  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  async listBatches(params: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaginatedResponse<BatchResponse>> {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.limit !== undefined) query.set('limit', params.limit.toString());
    if (params.offset !== undefined) query.set('offset', params.offset.toString());

    const qs = query.toString();
    return request<PaginatedResponse<BatchResponse>>(`/batches${qs ? `?${qs}` : ''}`);
  },

  async uploadBatch(formData: FormData): Promise<BatchResponse> {
    return request<BatchResponse>('/batches', {
      method: 'POST',
      body: formData,
    });
  },

  async getBatch(id: string): Promise<BatchResponse> {
    return request<BatchResponse>(`/batches/${id}`);
  },

  async listBatchResults(
    batchId: string,
    params: { match_status?: string; limit?: number; offset?: number }
  ): Promise<PaginatedResponse<ReconcileResultResponse>> {
    const query = new URLSearchParams();
    if (params.match_status) query.set('match_status', params.match_status);
    if (params.limit !== undefined) query.set('limit', params.limit.toString());
    if (params.offset !== undefined) query.set('offset', params.offset.toString());

    const qs = query.toString();
    return request<PaginatedResponse<ReconcileResultResponse>>(
      `/batches/${batchId}/results${qs ? `?${qs}` : ''}`
    );
  },

  async listBatchExceptions(
    batchId: string,
    params: { status?: string; priority?: string; category?: string; limit?: number; offset?: number }
  ): Promise<PaginatedResponse<ExceptionResponse>> {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    if (params.priority) query.set('priority', params.priority);
    if (params.category) query.set('category', params.category);
    if (params.limit !== undefined) query.set('limit', params.limit.toString());
    if (params.offset !== undefined) query.set('offset', params.offset.toString());

    const qs = query.toString();
    return request<PaginatedResponse<ExceptionResponse>>(
      `/batches/${batchId}/exceptions${qs ? `?${qs}` : ''}`
    );
  },

  async getException(id: string): Promise<ExceptionDetailResponse> {
    return request<ExceptionDetailResponse>(`/exceptions/${id}`);
  },

  async patchException(id: string, payload: ExceptionPatchRequest): Promise<ExceptionDetailResponse> {
    return request<ExceptionDetailResponse>(`/exceptions/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  },

  async listAuditEvents(params: {
    batch_id?: string;
    exception_id?: string;
    entity_type?: string;
    entity_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaginatedResponse<AuditEventResponse>> {
    const query = new URLSearchParams();
    if (params.batch_id) query.set('batch_id', params.batch_id);
    if (params.exception_id) query.set('exception_id', params.exception_id);
    if (params.entity_type) query.set('entity_type', params.entity_type);
    if (params.entity_id) query.set('entity_id', params.entity_id);
    if (params.limit !== undefined) query.set('limit', params.limit.toString());
    if (params.offset !== undefined) query.set('offset', params.offset.toString());

    const qs = query.toString();
    return request<PaginatedResponse<AuditEventResponse>>(`/audit-events${qs ? `?${qs}` : ''}`);
  },
};
