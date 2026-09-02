import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { ExceptionDetailResponse } from '../api/types';
import { AlertBanner } from '../components/AlertBanner';
import { StatusBadge } from '../components/StatusBadge';

const LOCAL_STORAGE_ACTOR_KEY = 'reconcilex.operator_draft_actor';

export const ExceptionDetailPage: React.FC = () => {
  const { exceptionId } = useParams<{ exceptionId: string }>();
  const [exception, setException] = useState<ExceptionDetailResponse | null>(null);

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
      <div>
        <AlertBanner type="danger">{error}</AlertBanner>
        <Link to="/batches" className="btn btn-outline">&larr; Back to Batches</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Exception Review</h1>
          <p className="subtext">Category: {exception?.category} | ID: {exception?.id}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link to={`/audit-events?exception_id=${exception?.id}`} className="btn btn-outline">
            View Exception Audit Logs
          </Link>
          <Link to={`/batches/${exception?.batch_id}`} className="btn btn-outline">
            &larr; Back to Batch
          </Link>
        </div>
      </div>

      {error && <AlertBanner type="danger">{error}</AlertBanner>}
      {successMsg && <AlertBanner type="info">{successMsg}</AlertBanner>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
        {/* Left Column: Context & Evidence */}
        <div>
          <div className="card">
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Operational Metadata
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div>
                <span className="subtext">Category:</span>
                <div style={{ fontWeight: 600 }}>{exception?.category}</div>
              </div>
              <div>
                <span className="subtext">Priority:</span>
                <div>{exception && <StatusBadge type="priority" value={exception.priority} />}</div>
              </div>
              <div>
                <span className="subtext">Current Status:</span>
                <div>{exception && <StatusBadge type="status" value={exception.status} />}</div>
              </div>
              <div>
                <span className="subtext">Assigned To:</span>
                <div style={{ fontWeight: 600 }}>{exception?.assigned_to || 'Unassigned'}</div>
              </div>
            </div>

            {exception?.resolved_by && (
              <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid #e2e8f0' }}>
                <span className="subtext">Resolution Info:</span>
                <div>Resolved by <strong>{exception.resolved_by}</strong> at {exception.resolved_at ? new Date(exception.resolved_at).toLocaleString() : ''}</div>
                {exception.resolution_reason && (
                  <div style={{ fontStyle: 'italic', marginTop: '0.25rem' }}>"{exception.resolution_reason}"</div>
                )}
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
