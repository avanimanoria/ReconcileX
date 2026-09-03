import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import {
  AIExplanationResponse,
  AINarrationCandidatesResponse,
  ExceptionDetailResponse,
} from '../api/types';
import { AlertBanner } from '../components/AlertBanner';
import { StatusBadge } from '../components/StatusBadge';

const LOCAL_STORAGE_ACTOR_KEY = 'reconcilex.operator_draft_actor';

export const ExceptionDetailPage: React.FC = () => {
  const { exceptionId } = useParams<{ exceptionId: string }>();
  const [exception, setException] = useState<ExceptionDetailResponse | null>(null);

  // AI advisory explanation states
  const [aiExplanation, setAiExplanation] = useState<AIExplanationResponse | null>(null);
  const [generatingAi, setGeneratingAi] = useState<boolean>(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // AI narration candidates extraction states
  const [narrationData, setNarrationData] = useState<AINarrationCandidatesResponse | null>(null);
  const [extractingNarration, setExtractingNarration] = useState<boolean>(false);
  const [narrationError, setNarrationError] = useState<string | null>(null);

  // Form states
  const [actor, setActor] = useState<string>(() => {

    return localStorage.getItem(LOCAL_STORAGE_ACTOR_KEY) || '';
  });
  const [assignedTo, setAssignedTo] = useState<string>('');
  const [targetStatus, setTargetStatus] = useState<string>('');
  const [resolutionReason, setResolutionReason] = useState<string>('');

  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);


  useEffect(() => {
    if (!exceptionId) return;
    const fetchException = async () => {
      setLoading(true);
      setError(null);
      try {
        const exc = await api.getException(exceptionId);
        setException(exc);
        setAssignedTo(exc.assigned_to || '');
      } catch (err: any) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError('Failed to fetch exception detail.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchException();
  }, [exceptionId]);

  const handleActorChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setActor(val);
    localStorage.setItem(LOCAL_STORAGE_ACTOR_KEY, val);
  };

  // Submit button is enabled only when actor is typed AND (if targetStatus is RESOLVED or DISMISSED) resolution_reason is typed, AND at least targetStatus or assignedTo is specified.
  const isFormValid = (): boolean => {
    if (!actor.trim()) return false;
    if (!targetStatus && assignedTo === (exception?.assigned_to || '')) return false;
    if (targetStatus === 'RESOLVED' || targetStatus === 'DISMISSED') {
      if (!resolutionReason.trim()) return false;
    }
    return true;
  };

  const handleGenerateAiExplanation = async () => {
    if (!exceptionId) return;
    setGeneratingAi(true);
    setAiError(null);
    try {
      const explanation = await api.getAiExplanation(exceptionId, {
        actor: actor.trim() || undefined,
      });
      setAiExplanation(explanation);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setAiError(err.message);
      } else {
        setAiError('Failed to generate AI explanation.');
      }
    } finally {
      setGeneratingAi(false);
    }
  };

  const handleExtractNarration = async () => {
    if (!exceptionId) return;
    setExtractingNarration(true);
    setNarrationError(null);
    try {
      const res = await api.extractNarrationCandidates(exceptionId, {
        actor: actor.trim() || undefined,
      });
      setNarrationData(res);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setNarrationError(err.message);
      } else {
        setNarrationError('Failed to extract narration candidate references.');
      }
    } finally {
      setExtractingNarration(false);
    }
  };


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!exceptionId || !isFormValid()) return;

    setError(null);
    setSuccessMsg(null);
    setSubmitting(true);

    try {
      const updated = await api.patchException(exceptionId, {
        actor: actor.trim(),
        assigned_to: assignedTo.trim() !== (exception?.assigned_to || '') ? assignedTo.trim() : undefined,
        status: targetStatus || undefined,
        resolution_reason: resolutionReason.trim() || undefined,
      });

      setException(updated);
      setTargetStatus('');
      setResolutionReason('');
      setSuccessMsg('Exception updated successfully.');
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setError(`Invalid State Transition (409 Conflict): ${err.message}`);
        } else {
          setError(err.message);
        }
      } else {
        setError('Failed to update exception.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading exception details...</div>;
  }

  if (error && !exception) {
    return (
      <div style={{ padding: '2rem' }}>
        <AlertBanner type="danger">{error}</AlertBanner>
        <Link to="/batches" className="btn btn-outline" style={{ marginTop: '1rem' }}>
          &larr; Back to Batches
        </Link>
      </div>
    );
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <Link to={exception?.batch_id ? `/batches/${exception.batch_id}` : '/batches'} style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: '0.875rem' }}>
          &larr; Back to Batch
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.5rem' }}>
          <div>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>
              Exception Review: {exception?.id}
            </h1>
            <p className="subtext" style={{ margin: '0.25rem 0 0 0', color: '#64748b', fontSize: '0.85rem' }}>
              Category: {exception?.category} | ID: {exception?.id}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <span className={`badge badge-priority-${exception?.priority}`}>
              {exception?.priority} Priority
            </span>
            <span className={`badge badge-status-${exception?.status}`}>
              {exception?.status}
            </span>
          </div>
        </div>

      </div>

      {error && <AlertBanner type="danger">{error}</AlertBanner>}
      {successMsg && <AlertBanner type="info">{successMsg}</AlertBanner>}


      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '1.5rem' }}>
        {/* Left Column: Exception Evidence & AI Explanation */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="card">
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Exception Overview
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', fontSize: '0.875rem' }}>
              <div><strong>Category:</strong> {exception?.category}</div>
              <div><strong>Priority:</strong> {exception?.priority}</div>
              <div><strong>Lifecycle Status:</strong> <StatusBadge type="status" value={exception?.status || 'OPEN'} /></div>
              <div><strong>Assigned To:</strong> {exception?.assigned_to || 'Unassigned'}</div>

              <div><strong>Resolved By:</strong> {exception?.resolved_by || 'N/A'}</div>
              <div><strong>Resolved At:</strong> {exception?.resolved_at ? new Date(exception.resolved_at).toLocaleString() : 'N/A'}</div>
            </div>
            {exception?.resolution_reason && (
              <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: '#f8fafc', borderLeft: '3px solid #64748b', fontSize: '0.875rem' }}>
                <strong>Resolution Reason:</strong> {exception.resolution_reason}
              </div>
            )}
          </div>

          <div className="card">
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Linked Entities
            </h2>
            <div style={{ fontSize: '0.875rem' }}>
              <div><strong>Payment ID:</strong> {exception?.payment_id || 'N/A'}</div>
              <div><strong>Settlement ID:</strong> {exception?.settlement_id || 'N/A'}</div>
              <div><strong>Bank Txn ID:</strong> {exception?.bank_txn_id || 'N/A'}</div>
            </div>
          </div>

          <div className="card">
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Financial Evidence & Engine Reason
            </h2>
            {exception?.engine_reason && (
              <p style={{ fontSize: '0.875rem', marginBottom: '0.75rem', fontStyle: 'italic', color: '#334155' }}>
                Engine Reason: "{exception.engine_reason}"
              </p>
            )}
            <div className="json-block">
              <pre>{JSON.stringify(exception?.financial_evidence || {}, null, 2)}</pre>
            </div>
          </div>

          {/* AI Grounded Advisory Explanation Section */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0 }}>
                AI Grounded Explanation (Advisory)
              </h2>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleGenerateAiExplanation}
                disabled={generatingAi}
              >
                {generatingAi ? 'Generating AI explanation...' : 'Generate AI explanation'}
              </button>
            </div>

            <p style={{ fontSize: '0.825rem', color: '#64748b', margin: '0 0 0.75rem 0' }}>
              Request an evidence-grounded advisory explanation. Purely advisory — does not mutate reconciliation or exception status.
            </p>

            {aiError && <AlertBanner type="danger">{aiError}</AlertBanner>}

            {aiExplanation && (
              <div className="ai-panel">
                <div className="ai-advisory-banner">
                  <span>⚠️</span>
                  <span>AI advisory only — does not change reconciliation status.</span>
                </div>

                {aiExplanation.validation.fallback_used && (
                  <div>
                    <span className="ai-fallback-badge">
                      Deterministic Fallback Active: {aiExplanation.validation.fallback_reason || 'SAFE_FALLBACK'}
                    </span>
                  </div>
                )}

                <div className="ai-section-title">Summary</div>
                <p style={{ fontSize: '0.875rem', lineHeight: '1.4', margin: '0 0 0.75rem 0' }}>
                  {aiExplanation.summary}
                </p>

                <div className="ai-section-title">Evidence & Source IDs Used</div>
                <div>
                  {aiExplanation.evidence.length === 0 ? (
                    <p style={{ fontSize: '0.825rem', color: '#64748b' }}>No source records cited.</p>
                  ) : (
                    aiExplanation.evidence.map((ev, idx) => (
                      <div key={idx} className="ai-evidence-item">
                        <div className="ai-evidence-header">
                          <span className="badge" style={{ background: '#e2e8f0', color: '#334155' }}>
                            {ev.source_type}
                          </span>
                          <code style={{ fontWeight: 600 }}>{ev.source_id}</code>
                        </div>
                        <div>{ev.claim}</div>
                      </div>
                    ))
                  )}
                </div>

                <div className="ai-section-title">Precomputed Calculation Summary</div>
                <table className="ai-calc-table">
                  <tbody>
                    {aiExplanation.calculation_summary.captured_amount && (
                      <tr><td className="key">Captured Amount:</td><td>INR {aiExplanation.calculation_summary.captured_amount}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.refund_amount && (
                      <tr><td className="key">Refund Amount:</td><td>INR {aiExplanation.calculation_summary.refund_amount}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.fee_amount && (
                      <tr><td className="key">Fee Amount:</td><td>INR {aiExplanation.calculation_summary.fee_amount}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.gst_amount && (
                      <tr><td className="key">GST on Fee:</td><td>INR {aiExplanation.calculation_summary.gst_amount}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.expected_net && (
                      <tr><td className="key">Expected Net:</td><td>INR {aiExplanation.calculation_summary.expected_net}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.settlement_net_amount && (
                      <tr><td className="key">Settlement Net Amount:</td><td>INR {aiExplanation.calculation_summary.settlement_net_amount}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.bank_credit_amount && (
                      <tr><td className="key">Bank Credit Amount:</td><td>INR {aiExplanation.calculation_summary.bank_credit_amount}</td></tr>
                    )}
                    {aiExplanation.calculation_summary.variance_amount && (
                      <tr><td className="key" style={{ color: '#b91c1c' }}>Variance:</td><td style={{ color: '#b91c1c', fontWeight: 600 }}>INR {aiExplanation.calculation_summary.variance_amount}</td></tr>
                    )}
                  </tbody>
                </table>

                <div className="ai-section-title">Suggested Next Step</div>
                <p style={{ fontSize: '0.875rem', lineHeight: '1.4', margin: '0 0 0.75rem 0' }}>
                  {aiExplanation.suggested_next_step}
                </p>

                {aiExplanation.unknowns && aiExplanation.unknowns.length > 0 && (
                  <>
                    <div className="ai-section-title">Unknowns & Limitations</div>
                    <ul className="ai-unknown-list">
                      {aiExplanation.unknowns.map((un, idx) => (
                        <li key={idx}>{un}</li>
                      ))}
                    </ul>
                  </>
                )}

                <div className="ai-meta-footer">
                  <div>
                    <strong>Model:</strong> {aiExplanation.model.provider} / {aiExplanation.model.model_id} ({aiExplanation.model.prompt_version})
                  </div>
                  <div>
                    <strong>Confidence:</strong> {(aiExplanation.confidence * 100).toFixed(0)}% (Advisory score)
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* AI Narration Reference Extractor (Advisory) */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0 }}>
                AI Narration Reference Extractor (Advisory)
              </h2>
              <button
                type="button"
                className="btn btn-outline"
                onClick={handleExtractNarration}
                disabled={extractingNarration}
              >
                {extractingNarration ? 'Extracting references...' : 'Extract narration references'}
              </button>
            </div>

            <p style={{ fontSize: '0.825rem', color: '#64748b', margin: '0 0 0.75rem 0' }}>
              Extracts candidate settlement IDs and UTRs from bank narration. Purely advisory — candidate rankings are computed strictly from stored records and policy rules without mutating state.
            </p>

            {narrationError && <AlertBanner type="danger">{narrationError}</AlertBanner>}

            {narrationData && (
              <div className="ai-panel">
                <div className="ai-advisory-banner">
                  <span>⚠️</span>
                  <span>AI advisory only — no reconciliation decision was made.</span>
                </div>

                {narrationData.validation.fallback_used && (
                  <div>
                    <span className="ai-fallback-badge">
                      Deterministic Fallback Active: {narrationData.validation.fallback_reason || 'UNSPECIFIED'}
                    </span>
                  </div>
                )}

                <div className="ai-section-title">Extracted Candidate References</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
                  <div style={{ background: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Settlement ID Candidate</div>
                    <code style={{ fontSize: '0.9rem', fontWeight: 600 }}>
                      {narrationData.extraction.settlement_id_candidate || 'None detected'}
                    </code>
                  </div>

                  <div style={{ background: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b' }}>UTR Candidate</div>
                    <code style={{ fontSize: '0.9rem', fontWeight: 600 }}>
                      {narrationData.extraction.utr_candidate || 'None detected'}
                    </code>
                  </div>

                  <div style={{ background: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                    <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Extraction Confidence</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>
                      {(narrationData.extraction.confidence * 100).toFixed(0)}% (Advisory score)
                    </div>
                  </div>
                </div>

                {narrationData.extraction.unknowns && narrationData.extraction.unknowns.length > 0 && (
                  <ul className="ai-unknown-list" style={{ marginBottom: '0.75rem' }}>
                    {narrationData.extraction.unknowns.map((un, idx) => (
                      <li key={idx}>{un}</li>
                    ))}
                  </ul>
                )}

                <div className="ai-section-title">Deterministic Candidate Ranking (Batch Scope)</div>
                {narrationData.ranked_candidates.some(c => c.deterministic_eligibility === 'AMBIGUOUS_FOR_HUMAN_REVIEW') && (
                  <div style={{ padding: '0.5rem 0.75rem', background: '#fffbeb', borderRadius: '4px', border: '1px solid #fef3c7', fontSize: '0.8rem', color: '#92400e', marginBottom: '0.75rem' }}>
                    ⚠️ <strong>Ambiguous Candidates:</strong> Multiple reference-matched candidates share identical rank. Human analyst review required.
                  </div>
                )}

                {narrationData.ranked_candidates.length > 0 ? (
                  <div style={{ overflowX: 'auto', marginBottom: '0.75rem' }}>
                    <table className="table" style={{ width: '100%', fontSize: '0.825rem' }}>
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Settlement ID</th>
                          <th>Linked Payment</th>
                          <th>Deterministic Eligibility</th>
                          <th>Evidence & Reasons</th>
                        </tr>
                      </thead>
                      <tbody>
                        {narrationData.ranked_candidates.map((cand) => (
                          <tr key={cand.settlement_id}>
                            <td style={{ fontWeight: 700 }}>#{cand.rank}</td>
                            <td><code>{cand.settlement_id}</code></td>
                            <td>{cand.payment_id ? <code>{cand.payment_id}</code> : 'N/A'}</td>
                            <td>
                              <span className={`badge ${cand.deterministic_eligibility === 'AMBIGUOUS_FOR_HUMAN_REVIEW' ? 'badge-priority-HIGH' : 'badge-priority-LOW'}`}>
                                {cand.deterministic_eligibility}
                              </span>
                            </td>
                            <td>
                              <ul style={{ margin: 0, paddingLeft: '1rem' }}>
                                {cand.reasons.map((r, rIdx) => (
                                  <li key={rIdx}>{r}</li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '4px', color: '#64748b', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                    No reference-matched settlements found in this batch. Human analyst review required.
                  </div>
                )}

                <div className="ai-section-title">Safe Next Step</div>
                <p style={{ fontSize: '0.875rem', lineHeight: '1.4', margin: 0 }}>
                  {narrationData.safe_next_step}
                </p>
              </div>
            )}
          </div>
        </div>



        {/* Right Column: Human Workflow PATCH Form */}
        <div>
          <div className="card">
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Human Operator Action (PATCH)
            </h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="actor">Actor Identifier (Required) *</label>
                <input
                  id="actor"
                  type="text"
                  placeholder="e.g. analyst_sarah"
                  value={actor}
                  onChange={handleActorChange}
                />
                <span className="subtext">Saved in local draft for convenience. Submits only on click.</span>
              </div>

              <div className="form-group">
                <label htmlFor="assigned_to">Assignee (Optional)</label>
                <input
                  id="assigned_to"
                  type="text"
                  placeholder="e.g. analyst_sarah"
                  value={assignedTo}
                  onChange={(e) => setAssignedTo(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="status_select">Target Status Transition</label>
                <select
                  id="status_select"
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                >
                  <option value="">-- No Status Change --</option>
                  <option value="IN_REVIEW">IN_REVIEW (Start Review)</option>
                  <option value="RESOLVED">RESOLVED (Resolve Exception)</option>
                  <option value="DISMISSED">DISMISSED (Dismiss Exception)</option>
                </select>
              </div>

              {(targetStatus === 'RESOLVED' || targetStatus === 'DISMISSED') && (
                <div className="form-group">
                  <label htmlFor="resolution_reason">Resolution / Dismissal Reason (Required for {targetStatus}) *</label>
                  <textarea
                    id="resolution_reason"
                    rows={3}
                    placeholder="Document mandatory human resolution or dismissal reason..."
                    value={resolutionReason}
                    onChange={(e) => setResolutionReason(e.target.value)}
                  />
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '0.5rem' }}
                disabled={submitting || !isFormValid()}
              >
                {submitting ? 'Applying Transition...' : 'Execute Human Action'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
