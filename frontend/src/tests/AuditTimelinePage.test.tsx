import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { AuditTimelinePage } from '../pages/AuditTimelinePage';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    listAuditEvents: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

describe('AuditTimelinePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders audit events ordered by event_sequence ASC', async () => {
    (api.listAuditEvents as any).mockResolvedValue({
      items: [
        {
          id: 'aud-1',
          event_sequence: 1,
          event_type: 'BATCH_CREATED',
          entity_type: 'BATCH',
          entity_id: 'batch-1',
          actor: 'SYSTEM',
          action: 'CREATE_BATCH',
          reason: 'Initial ingest',
          created_at: new Date().toISOString(),
        },
        {
          id: 'aud-2',
          event_sequence: 2,
          event_type: 'STATUS_TRANSITION',
          entity_type: 'EXCEPTION',
          entity_id: 'exc-1',
          actor: 'analyst_jane',
          action: 'TRANSITION_STATUS',
          reason: 'Under review',
          created_at: new Date().toISOString(),
        },
      ],
      total: 2,
      limit: 20,
      offset: 0,
    });

    render(
      <MemoryRouter>
        <AuditTimelinePage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/#1 — BATCH_CREATED/i)).toBeInTheDocument();
      expect(screen.getByText(/#2 — STATUS_TRANSITION/i)).toBeInTheDocument();
    });
  });

  it('submitting filter form triggers filtered audit event query with batch and exception parameters', async () => {
    (api.listAuditEvents as any).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    });

    render(
      <MemoryRouter>
        <AuditTimelinePage />
      </MemoryRouter>
    );

    const batchInput = screen.getByLabelText(/Filter by Batch ID/i);
    const exceptionInput = screen.getByLabelText(/Filter by Exception ID/i);
    const filterBtn = screen.getByRole('button', { name: /Filter Audit Logs/i });

    fireEvent.change(batchInput, { target: { value: 'batch-uuid-123' } });
    fireEvent.change(exceptionInput, { target: { value: 'exc-uuid-456' } });
    fireEvent.click(filterBtn);

    await waitFor(() => {
      expect(api.listAuditEvents).toHaveBeenCalledWith(
        expect.objectContaining({
          limit: 20,
          offset: 0,
        })
      );
    });
  });
});
