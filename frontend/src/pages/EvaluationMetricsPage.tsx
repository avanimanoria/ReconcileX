import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { EvaluationReportResponse } from '../api/types';
import { AlertBanner } from '../components/AlertBanner';

export const EvaluationMetricsPage: React.FC = () => {
  const [report, setReport] = useState<EvaluationReportResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const fetchReport = async (forceRefresh: boolean = false) => {
    if (forceRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await api.getEvaluationReport(forceRefresh);
      setReport(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load evaluation metrics report.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchReport(false);
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
        Loading truthful evaluation metrics from held-out benchmark...
      </div>
    );
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>
            System Evaluation & Truthful Metrics Report
          </h1>
          <p className="subtext" style={{ margin: '0.25rem 0 0 0', color: '#64748b', fontSize: '0.875rem' }}>
            Reproducible benchmark metrics derived from held-out truth ledgers and evaluation corpora.
            {report?.generated_at && ` (Last computed: ${new Date(report.generated_at).toLocaleString()})`}
          </p>
        </div>
        <button
          className="btn btn-outline"
          onClick={() => fetchReport(true)}
          disabled={refreshing}
          type="button"
        >
          {refreshing ? 'Recomputing Live...' : 'Recompute Metrics Live'}
        </button>
      </div>

      {error && <AlertBanner type="danger">{error}</AlertBanner>}

      {report && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* SECTION 1: Deterministic Reconciliation Metrics */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>
                1. Deterministic Reconciliation Metrics
              </h2>
              <span className="badge" style={{ background: '#e2e8f0', color: '#334155' }}>
                Dataset: {report.deterministic_reconciliation.dataset_name} (N = {report.deterministic_reconciliation.sample_size})
              </span>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0 0 1rem 0' }}>
              Evaluated strictly against the seeded held-out truth ledger. The deterministic engine is the sole source of financial matching truth.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>AUTO-MATCH PRECISION</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent, #0f172a)' }}>
                  {(report.deterministic_reconciliation.auto_match_precision * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>TP / (TP + FP)</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>AUTO-MATCH RECALL</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent, #0f172a)' }}>
                  {(report.deterministic_reconciliation.auto_match_recall * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>TP / (TP + FN)</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>AUTO-MATCH F1 SCORE</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent, #0f172a)' }}>
                  {(report.deterministic_reconciliation.auto_match_f1 * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Harmonic mean of P & R</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>INCORRECT AUTO-MATCHES (FP)</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: report.deterministic_reconciliation.incorrect_auto_match_count === 0 ? '#16a34a' : '#dc2626' }}>
                  {report.deterministic_reconciliation.incorrect_auto_match_count}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Sourced from truth labels</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>PROCESSING LATENCY</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                  {report.deterministic_reconciliation.latency_ms.toFixed(1)} ms
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Elapsed 500-scenario run</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>THROUGHPUT</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
                  {report.deterministic_reconciliation.throughput_records_per_minute.toLocaleString()}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Records / minute</div>
              </div>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Exception Category Breakdown & Rates
              </h3>
              <div style={{ fontSize: '0.825rem', color: '#64748b', marginBottom: '0.5rem' }}>
                Total Exception Rate: <strong>{(report.deterministic_reconciliation.total_exception_rate * 100).toFixed(1)}%</strong> ({report.deterministic_reconciliation.exceptions_emitted} / {report.deterministic_reconciliation.total_scenarios_evaluated} total scenarios)
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="table" style={{ width: '100%', fontSize: '0.85rem' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Exception Category</th>
                      <th style={{ textAlign: 'right' }}>Occurrences</th>
                      <th style={{ textAlign: 'right' }}>Category Exception Rate (Count / Total Scenarios)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(report.deterministic_reconciliation.exception_rates_by_category).map(([cat, rate]) => (
                      <tr key={cat}>
                        <td style={{ fontWeight: 600 }}>{cat}</td>
                        <td style={{ textAlign: 'right' }}>{report.deterministic_reconciliation.exception_breakdown_actual[cat] || 0}</td>
                        <td style={{ textAlign: 'right' }}>{(rate * 100).toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#f1f5f9', borderRadius: '4px', fontSize: '0.78rem', color: '#475569' }}>
              <strong>Disclaimer:</strong> {report.deterministic_reconciliation.disclaimer}
            </div>
          </div>

          {/* SECTION 2: AI Advisory Extraction Metrics */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>
                2. AI Advisory Extraction Metrics
              </h2>
              <span className="badge" style={{ background: '#e2e8f0', color: '#334155' }}>
                Dataset: {report.ai_advisory_extraction.dataset_name} (N = {report.ai_advisory_extraction.sample_size})
              </span>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0 0 1rem 0' }}>
              Measures candidate reference extraction and deterministic candidate ranking. Advisory only — does not determine financial matching.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>SETTLEMENT ID P / R / F1</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  {(report.ai_advisory_extraction.settlement_id_f1 * 100).toFixed(1)}% F1
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  P: {(report.ai_advisory_extraction.settlement_id_precision * 100).toFixed(1)}% | R: {(report.ai_advisory_extraction.settlement_id_recall * 100).toFixed(1)}%
                </div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>UTR TRACKING P / R / F1</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  {(report.ai_advisory_extraction.utr_f1 * 100).toFixed(1)}% F1
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  P: {(report.ai_advisory_extraction.utr_precision * 100).toFixed(1)}% | R: {(report.ai_advisory_extraction.utr_recall * 100).toFixed(1)}%
                </div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>CANDIDATE RANKING P@1</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  {(report.ai_advisory_extraction.candidate_ranking_precision_at_1 * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Top rank matches expected</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>CANDIDATE RANKING R@3</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  {(report.ai_advisory_extraction.candidate_ranking_recall_at_3 * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Expected in top 3 candidates</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>FALLBACK RATE</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  {(report.ai_advisory_extraction.malformed_output_fallback_rate * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Fallback triggered on faults</div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>UNSAFE BLOCKED RATE</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#16a34a' }}>
                  {(report.ai_advisory_extraction.unsafe_output_blocked_rate * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Directives safely blocked</div>
              </div>
            </div>

            <div style={{ padding: '0.75rem', background: '#fffbeb', borderRadius: '4px', border: '1px solid #fef3c7', fontSize: '0.8rem', color: '#92400e', marginBottom: '0.75rem' }}>
              <strong>Benchmark Scope Limitation:</strong> The 30-case narration corpus is a small synthetic regression and demo benchmark. It is designed to verify regex/model reference parsing and defense catch behavior, and is not a statistically reliable estimate of third-party production accuracy.
            </div>

            <div style={{ padding: '0.75rem', background: '#f1f5f9', borderRadius: '4px', fontSize: '0.78rem', color: '#475569' }}>
              <strong>Disclaimer:</strong> {report.ai_advisory_extraction.disclaimer}
            </div>
          </div>

          {/* SECTION 3: Human Workflow Metrics */}
          <div className="card">
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              3. Human Workflow Metrics
            </h2>

            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0 0 1rem 0' }}>
              ReconcileX enforces human-in-the-loop review for all exception lifecycle state transitions.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>SIMULATED MEAN TIME TO RESOLUTION</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#64748b', marginTop: '0.25rem' }}>
                  {report.human_workflow.simulated_mean_time_to_resolution}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                  No simulated analyst session timestamps in prototype
                </div>
              </div>

              <div className="card" style={{ background: '#f8fafc', padding: '1rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>AUTO-RESOLUTION RATE</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#64748b', marginTop: '0.25rem' }}>
                  {report.human_workflow.auto_resolution_rate}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                  Autonomous resolution is strictly forbidden by policy
                </div>
              </div>
            </div>

            <div style={{ padding: '0.75rem', background: '#f1f5f9', borderRadius: '4px', fontSize: '0.78rem', color: '#475569' }}>
              <strong>Policy Guarantee:</strong> {report.human_workflow.disclaimer}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
