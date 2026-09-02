import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { ExceptionDetailPage } from '../pages/ExceptionDetailPage';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getException: vi.fn(),
    patchException: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

describe('ExceptionDetailPage', () => {
  const LOCAL_STORAGE_ACTOR_KEY = 'reconcilex.operator_draft_actor';

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('submit remains disabled without required actor or without required resolution reason for terminal status', async () => {
    (api.getException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'SETTLEMENT_DELAY',
      priority: 'HIGH',
      status: 'OPEN',
      assigned_to: null,
      financial_evidence: { gross_amount: '100.00' },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(
      <MemoryRouter initialEntries={['/exceptions/exc-123']}>
        <Routes>
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Category: SETTLEMENT_DELAY/i)).toBeInTheDocument();
    });

    const submitBtn = screen.getByRole('button', { name: /Execute Human Action/i });
    
    // 1. Without actor and without target status -> submit is disabled
    expect(submitBtn).toBeDisabled();

    // 2. Add actor only, without status change or assignee change -> submit is disabled
    const actorInput = screen.getByLabelText(/Actor Identifier/i);
    fireEvent.change(actorInput, { target: { value: 'analyst_bob' } });
    expect(submitBtn).toBeDisabled();

    // 3. Select RESOLVED transition without resolution reason -> submit is disabled
    const statusSelect = screen.getByLabelText(/Target Status Transition/i);
    fireEvent.change(statusSelect, { target: { value: 'RESOLVED' } });
    expect(submitBtn).toBeDisabled();

    // 4. Fill resolution reason -> submit becomes enabled
    const reasonInput = screen.getByLabelText(/Resolution \/ Dismissal Reason/i);
    fireEvent.change(reasonInput, { target: { value: 'Settlement confirmed in bank statement' } });
    expect(submitBtn).not.toBeDisabled();

    // Confirm no PATCH request was triggered during validation checks
    expect(api.patchException).not.toHaveBeenCalled();
  });

  it('localStorage draft actor visibly pre-fills the field but makes no PATCH until explicit human click; then valid submit performs exactly one PATCH', async () => {
    localStorage.setItem(LOCAL_STORAGE_ACTOR_KEY, 'draft_analyst_jane');

    (api.getException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'SETTLEMENT_DELAY',
      priority: 'MEDIUM',
      status: 'OPEN',
      assigned_to: null,
      financial_evidence: { gross_amount: '100.00' },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(
      <MemoryRouter initialEntries={['/exceptions/exc-123']}>
        <Routes>
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Category: SETTLEMENT_DELAY/i)).toBeInTheDocument();
    });

    // 1. Assert actor field is visibly prefilled from localStorage
    const actorInput = screen.getByLabelText(/Actor Identifier/i) as HTMLInputElement;
    expect(actorInput).toBeInTheDocument();
    expect(actorInput.value).toBe('draft_analyst_jane');

    // 2. Assert no PATCH request occurs merely from rendering or loading localStorage
    expect(api.patchException).not.toHaveBeenCalled();

    // Select status transition to IN_REVIEW
    const statusSelect = screen.getByLabelText(/Target Status Transition/i);
    fireEvent.change(statusSelect, { target: { value: 'IN_REVIEW' } });

    // Confirm still no PATCH request before explicit submit click
    expect(api.patchException).not.toHaveBeenCalled();

    // 3. Explicit human submit click
    const submitBtn = screen.getByRole('button', { name: /Execute Human Action/i });
    expect(submitBtn).not.toBeDisabled();

    (api.patchException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'SETTLEMENT_DELAY',
      priority: 'MEDIUM',
      status: 'IN_REVIEW',
      assigned_to: null,
      financial_evidence: { gross_amount: '100.00' },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    fireEvent.click(submitBtn);

    // 4. Assert exactly one PATCH call executed
    await waitFor(() => {
      expect(api.patchException).toHaveBeenCalledTimes(1);
      expect(api.patchException).toHaveBeenCalledWith('exc-123', {
        actor: 'draft_analyst_jane',
        status: 'IN_REVIEW',
        assigned_to: undefined,
        resolution_reason: undefined,
      });
    });
  });
});
