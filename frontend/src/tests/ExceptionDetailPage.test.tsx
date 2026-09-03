import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { ExceptionDetailPage } from '../pages/ExceptionDetailPage';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getException: vi.fn(),
    patchException: vi.fn(),
    getAiExplanation: vi.fn(),
    extractNarrationCandidates: vi.fn(),
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

  it('invoking Generate AI explanation button calls API and renders advisory explanation and calculation summary', async () => {
    (api.getException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'AMOUNT_VARIANCE',
      priority: 'HIGH',
      status: 'OPEN',
      assigned_to: null,
      financial_evidence: { gross_amount: '1000.00' },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    (api.getAiExplanation as any).mockResolvedValue({
      exception_id: 'exc-123',
      status: 'VALID',
      advisory_only: true,
      model: {
        provider: 'google',
        model_id: 'gemini-1.5-flash',
        model_version: 'gemini-1.5-flash-latest',
        prompt_version: 'ai-explanation-v1',
      },
      summary: 'Expected net INR 976.40 differs from bank credit INR 900.00 by variance INR 76.40.',
      evidence: [
        { source_type: 'payment', source_id: 'PAY-001', claim: 'Captured for INR 1000.00' },
        { source_type: 'bank_credit', source_id: 'BNK-001', claim: 'Credited INR 900.00' },
      ],
      calculation_summary: {
        captured_amount: '1000.00',
        fee_amount: '20.00',
        gst_amount: '3.60',
        expected_net: '976.40',
        bank_credit_amount: '900.00',
        variance_amount: '76.40',
        currency: 'INR',
      },
      suggested_next_step: 'Inquire with partner bank regarding the INR 76.40 variance.',
      unknowns: ['Root cause not present in input dataset.'],
      confidence: 0.88,
      validation: {
        schema_valid: true,
        evidence_ids_valid: true,
        grounding_valid: true,
        fallback_used: false,
      },
    });

    render(
      <MemoryRouter initialEntries={['/exceptions/exc-123']}>
        <Routes>
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Category: AMOUNT_VARIANCE/i)).toBeInTheDocument();
    });

    const aiBtn = screen.getByRole('button', { name: /Generate AI explanation/i });
    expect(aiBtn).toBeInTheDocument();

    // Click button to trigger AI explanation
    fireEvent.click(aiBtn);

    // Verify API called
    await waitFor(() => {
      expect(api.getAiExplanation).toHaveBeenCalledWith('exc-123', { actor: undefined });
    });

    // Assert advisory banner is displayed
    expect(screen.getByText(/AI advisory only — does not change reconciliation status/i)).toBeInTheDocument();

    // Assert summary and evidence are rendered
    expect(screen.getByText(/Expected net INR 976.40 differs from bank credit/i)).toBeInTheDocument();
    expect(screen.getByText('PAY-001')).toBeInTheDocument();
    expect(screen.getByText('BNK-001')).toBeInTheDocument();

    // Assert calculations are rendered
    expect(screen.getByText('Captured Amount:')).toBeInTheDocument();
    expect(screen.getAllByText(/INR 76.40/i).length).toBeGreaterThan(0);

    // Assert suggested next step and unknowns

    expect(screen.getByText(/Inquire with partner bank regarding the INR 76.40 variance/i)).toBeInTheDocument();
    expect(screen.getByText(/Root cause not present in input dataset/i)).toBeInTheDocument();

    // Assert confidence rendered as advisory score
    expect(screen.getByText(/88% \(Advisory score\)/i)).toBeInTheDocument();

    // Confirm no PATCH call was made
    expect(api.patchException).not.toHaveBeenCalled();
  });

  it('renders fallback state safely when model validation fallback is active', async () => {
    (api.getException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'STATUS_CONFLICT',
      priority: 'HIGH',
      status: 'OPEN',
      assigned_to: null,
      financial_evidence: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    (api.getAiExplanation as any).mockResolvedValue({
      exception_id: 'exc-123',
      status: 'VALID',
      advisory_only: true,
      model: {
        provider: 'deterministic_fallback',
        model_id: 'rule-explainer',
        model_version: '1.0.0',
        prompt_version: 'ai-explanation-v1',
      },
      summary: 'Payment status prevents automated settlement reconciliation.',
      evidence: [],
      calculation_summary: { currency: 'INR' },
      suggested_next_step: 'Check gateway logs.',
      unknowns: ['Gateway transaction logs outside the batch are not available.'],
      confidence: 0.95,
      validation: {
        schema_valid: true,
        evidence_ids_valid: true,
        grounding_valid: true,
        fallback_used: true,
        fallback_reason: 'NO_LLM_KEY_CONFIGURED',
      },
    });

    render(
      <MemoryRouter initialEntries={['/exceptions/exc-123']}>
        <Routes>
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Category: STATUS_CONFLICT/i)).toBeInTheDocument();
    });

    const aiBtn = screen.getByRole('button', { name: /Generate AI explanation/i });
    fireEvent.click(aiBtn);

    await waitFor(() => {
      expect(screen.getByText(/Deterministic Fallback Active: NO_LLM_KEY_CONFIGURED/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Payment status prevents automated settlement reconciliation/i)).toBeInTheDocument();
    expect(screen.queryByText(/auto-match/i)).not.toBeInTheDocument();
  });

  it('extract narration references calls API and renders candidate settlement and deterministic ranking', async () => {
    (api.getException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'MISSING_REFERENCE',
      priority: 'HIGH',
      status: 'OPEN',
      assigned_to: null,
      financial_evidence: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    (api.extractNarrationCandidates as any).mockResolvedValue({
      exception_id: 'exc-123',
      advisory_only: true,
      financial_match_decision: 'NOT_MADE',
      extraction: {
        settlement_id_candidate: 'SET-5001',
        utr_candidate: '98124571',
        confidence: 0.96,
        unknowns: [],
      },
      validation: {
        schema_valid: true,
        candidate_reference_valid: true,
        fallback_used: false,
        fallback_reason: null,
      },
      ranked_candidates: [
        {
          rank: 1,
          settlement_id: 'SET-5001',
          payment_id: 'PAY-1001',
          deterministic_eligibility: 'ELIGIBLE_FOR_HUMAN_REVIEW',
          evidence: {
            extracted_reference_equals_settlement_id: true,
            amount_relation: 'BANK_AMOUNT_EQUALS_SETTLEMENT_NET',
            date_relation: 'WITHIN_ALLOWED_WINDOW',
            uniqueness: 'UNIQUE_CANDIDATE',
          },
          reasons: [
            "Extracted candidate 'SET-5001' exactly equals stored settlement ID.",
            'Bank credit amount INR 976.40 equals settlement net INR 976.40.',
          ],
        },
      ],
      safe_next_step: 'Ask an analyst to verify the source evidence before any reconciliation decision.',
    });

    render(
      <MemoryRouter initialEntries={['/exceptions/exc-123']}>
        <Routes>
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Category: MISSING_REFERENCE/i)).toBeInTheDocument();
    });

    const narrBtn = screen.getByRole('button', { name: /Extract narration references/i });
    expect(narrBtn).toBeInTheDocument();

    fireEvent.click(narrBtn);

    await waitFor(() => {
      expect(api.extractNarrationCandidates).toHaveBeenCalledWith('exc-123', { actor: undefined });
    });

    // Verify advisory banner
    expect(screen.getByText(/AI advisory only — no reconciliation decision was made/i)).toBeInTheDocument();

    // Verify candidates rendered
    expect(screen.getAllByText('SET-5001').length).toBeGreaterThan(0);
    expect(screen.getAllByText('98124571').length).toBeGreaterThan(0);
    expect(screen.getByText(/96% \(Advisory score\)/i)).toBeInTheDocument();


    // Verify ranking table
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('PAY-1001')).toBeInTheDocument();
    expect(screen.getByText('ELIGIBLE_FOR_HUMAN_REVIEW')).toBeInTheDocument();
    expect(screen.getByText(/Bank credit amount INR 976.40 equals settlement net/i)).toBeInTheDocument();

    // Safe next step
    expect(screen.getByText(/Ask an analyst to verify the source evidence before any reconciliation decision/i)).toBeInTheDocument();

    // Verify no automated actions/PATCH
    expect(api.patchException).not.toHaveBeenCalled();
    expect(screen.queryByText(/accept match/i)).not.toBeInTheDocument();
  });

  it('renders ambiguity warning state when multiple candidates share top rank', async () => {
    (api.getException as any).mockResolvedValue({
      id: 'exc-123',
      batch_id: 'batch-456',
      category: 'MISSING_REFERENCE',
      priority: 'HIGH',
      status: 'OPEN',
      assigned_to: null,
      financial_evidence: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    (api.extractNarrationCandidates as any).mockResolvedValue({
      exception_id: 'exc-123',
      advisory_only: true,
      financial_match_decision: 'NOT_MADE',
      extraction: {
        settlement_id_candidate: 'SET-001',
        utr_candidate: null,
        confidence: 0.85,
        unknowns: [],
      },
      validation: {
        schema_valid: true,
        candidate_reference_valid: true,
        fallback_used: false,
        fallback_reason: null,
      },
      ranked_candidates: [
        {
          rank: 1,
          settlement_id: 'SET-001',
          payment_id: 'PAY-001',
          deterministic_eligibility: 'AMBIGUOUS_FOR_HUMAN_REVIEW',
          evidence: {
            extracted_reference_equals_settlement_id: true,
            amount_relation: 'BANK_AMOUNT_EQUALS_SETTLEMENT_NET',
            date_relation: 'WITHIN_ALLOWED_WINDOW',
            uniqueness: 'MULTIPLE_CANDIDATES',
          },
          reasons: ['Multiple reference-matched candidates share identical rank; human operator must review.'],
        },
        {
          rank: 2,
          settlement_id: 'SET-001-B',
          payment_id: 'PAY-001',
          deterministic_eligibility: 'AMBIGUOUS_FOR_HUMAN_REVIEW',
          evidence: {
            extracted_reference_equals_settlement_id: true,
            amount_relation: 'BANK_AMOUNT_EQUALS_SETTLEMENT_NET',
            date_relation: 'WITHIN_ALLOWED_WINDOW',
            uniqueness: 'MULTIPLE_CANDIDATES',
          },
          reasons: ['Multiple reference-matched candidates share identical rank; human operator must review.'],
        },
      ],
      safe_next_step: 'Ask an analyst to verify the source evidence before any reconciliation decision.',
    });

    render(
      <MemoryRouter initialEntries={['/exceptions/exc-123']}>
        <Routes>
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Category: MISSING_REFERENCE/i)).toBeInTheDocument();
    });

    const narrBtn = screen.getByRole('button', { name: /Extract narration references/i });
    fireEvent.click(narrBtn);

    await waitFor(() => {
      expect(screen.getByText(/Ambiguous Candidates:/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText('AMBIGUOUS_FOR_HUMAN_REVIEW').length).toBe(2);
    expect(screen.queryByText(/apply candidate/i)).not.toBeInTheDocument();
  });
});


