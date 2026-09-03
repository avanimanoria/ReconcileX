import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { EvaluationMetricsPage } from '../pages/EvaluationMetricsPage';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    getEvaluationReport: vi.fn(),
  },
}));

describe('EvaluationMetricsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders truthful evaluation metrics across deterministic, AI advisory, and human workflow sections', async () => {
    (api.getEvaluationReport as any).mockResolvedValue({
      generated_at: '2026-09-04T00:00:00Z',
      deterministic_reconciliation: {
        dataset_name: 'ReconcileX Synthetic Held-Out Benchmark',
        sample_size: 500,
        generator_version: '1.0.0',
        seed: 20260902,
        auto_match_precision: 1.0,
        auto_match_recall: 1.0,
        auto_match_f1: 1.0,
        incorrect_auto_match_count: 0,
        total_scenarios_evaluated: 500,
        auto_matches_emitted: 225,
        exceptions_emitted: 275,
        total_exception_rate: 0.55,
        exception_rates_by_category: {
          SETTLEMENT_DELAY: 0.08,
          AMOUNT_VARIANCE: 0.08,
          MISSING_REFERENCE: 0.07,
        },
        exception_breakdown_actual: {
          SETTLEMENT_DELAY: 40,
          AMOUNT_VARIANCE: 40,
          MISSING_REFERENCE: 35,
        },
        latency_ms: 38.5,
        throughput_records_per_minute: 2850.0,
        definitions: {
          precision: 'TP / (TP + FP)',
          recall: 'TP / (TP + FN)',
        },
        disclaimer: 'Evaluated against seeded synthetic held-out truth ledger.',
      },
      ai_advisory_extraction: {
        dataset_name: 'Synthetic Held-Out Bank Narration Benchmark',
        sample_size: 30,
        generator_version: '1.0.0',
        settlement_id_precision: 1.0,
        settlement_id_recall: 1.0,
        settlement_id_f1: 1.0,
        utr_precision: 1.0,
        utr_recall: 1.0,
        utr_f1: 1.0,
        false_extraction_count: 0,
        candidate_ranking_precision_at_1: 1.0,
        candidate_ranking_recall_at_3: 1.0,
        malformed_output_fallback_rate: 0.1,
        unsafe_output_blocked_rate: 1.0,
        disclaimer: 'Measures advisory text extraction and candidate ranking only; not financial reconciliation accuracy.',
      },
      human_workflow: {
        simulated_mean_time_to_resolution: 'Not measured / Unavailable',
        auto_resolution_rate: 'Not applicable — human approval required',
        disclaimer: 'ReconcileX prototype strictly requires human operator review.',
      },
    });

    render(<EvaluationMetricsPage />);

    // Check loading transition to rendered report
    await waitFor(() => {
      expect(screen.getByText(/System Evaluation & Truthful Metrics Report/i)).toBeInTheDocument();
    });

    // 1. Deterministic section assertions
    expect(screen.getByText(/1. Deterministic Reconciliation Metrics/i)).toBeInTheDocument();
    expect(screen.getByText(/Dataset: ReconcileX Synthetic Held-Out Benchmark \(N = 500\)/i)).toBeInTheDocument();
    expect(screen.getAllByText('100.0%').length).toBeGreaterThan(0); // Auto-match precision / recall / F1
    expect(screen.getByText('38.5 ms')).toBeInTheDocument(); // Processing latency
    expect(screen.getByText('2,850')).toBeInTheDocument(); // Throughput formatted
    expect(screen.getAllByText(/SETTLEMENT_DELAY/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/8.00%/i).length).toBeGreaterThan(0); // Category rate



    // 2. AI Advisory section assertions
    expect(screen.getByText(/2. AI Advisory Extraction Metrics/i)).toBeInTheDocument();
    expect(screen.getByText(/Dataset: Synthetic Held-Out Bank Narration Benchmark \(N = 30\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Benchmark Scope Limitation:/i)).toBeInTheDocument();
    expect(screen.getByText(/small synthetic regression and demo benchmark/i)).toBeInTheDocument();

    // 3. Human workflow section assertions
    expect(screen.getByText(/3. Human Workflow Metrics/i)).toBeInTheDocument();
    expect(screen.getByText('Not measured / Unavailable')).toBeInTheDocument();
    expect(screen.getByText('Not applicable — human approval required')).toBeInTheDocument();

    // 4. Test recompute live button
    const refreshBtn = screen.getByRole('button', { name: /Recompute Metrics Live/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(api.getEvaluationReport).toHaveBeenCalledWith(true);
    });
  });
});
