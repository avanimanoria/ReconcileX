import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { AuditEventResponse } from '../api/types';
import { AlertBanner } from '../components/AlertBanner';
import { PaginationControls } from '../components/PaginationControls';

export const AuditTimelinePage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialBatchId = searchParams.get('batch_id') || '';
  const initialExceptionId = searchParams.get('exception_id') || '';

  const [batchIdInput, setBatchIdInput] = useState<string>(initialBatchId);
  const [exceptionIdInput, setExceptionIdInput] = useState<string>(initialExceptionId);

  const [events, setEvents] = useState<AuditEventResponse[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [limit] = useState<number>(20);
  const [offset, setOffset] = useState<number>(0);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAuditEvents = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAuditEvents({
        batch_id: initialBatchId || undefined,
        exception_id: initialExceptionId || undefined,
        limit,
        offset,
      });
      setEvents(res.items);
      setTotal(res.total);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to fetch audit timeline.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditEvents();
  }, [initialBatchId, initialExceptionId, limit, offset]);

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    const newParams: Record<string, string> = {};
    if (batchIdInput.trim()) newParams.batch_id = batchIdInput.trim();
    if (exceptionIdInput.trim()) newParams.exception_id = exceptionIdInput.trim();
    setSearchParams(newParams);
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Immutable Audit Timeline</h1>
          <p className="subtext">
            Audit history ordered strictly by <strong>event_sequence ASC</strong> (PostgreSQL append-only triggers enforce immutability)
          </p>
        </div>
      </div>

      <div className="card">
        <form onSubmit={handleFilterSubmit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '1rem', alignItems: 'end' }}>
          <div>
            <label htmlFor="filter_batch_id">Filter by Batch ID (UUID)</label>
            <input
              id="filter_batch_id"
              type="text"
              placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000"
              value={batchIdInput}
              onChange={(e) => setBatchIdInput(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="filter_exception_id">Filter by Exception ID (UUID)</label>
            <input
              id="filter_exception_id"
              type="text"
              placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000"
              value={exceptionIdInput}
              onChange={(e) => setExceptionIdInput(e.target.value)}
            />
          </div>

          <div>
            <button type="submit" className="btn btn-primary">
              Filter Audit Logs
            </button>
          </div>
        </form>
      </div>

      {error && <AlertBanner type="danger">{error}</AlertBanner>}

      <div className="card">
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading audit timeline...</div>
        ) : events.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
            No audit events found for the specified filters.
          </div>
        ) : (
          <div className="timeline">
            {events.map((evt) => (
              <div className="timeline-item" key={evt.id}>
                <div className="timeline-marker"></div>
                <div style={{ background: '#f8fafc', padding: '0.85rem', borderRadius: '0.375rem', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#1e3a8a' }}>
                      #{evt.event_sequence} — {evt.event_type} ({evt.action})
                    </span>
                    <span className="subtext">{new Date(evt.created_at).toLocaleString()}</span>
                  </div>

                  <div style={{ fontSize: '0.85rem', color: '#334155', marginBottom: '0.35rem' }}>
                    <strong>Actor:</strong> {evt.actor} | <strong>Entity:</strong> {evt.entity_type} ({evt.entity_id})
                  </div>

                  <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                    <strong>Reason:</strong> {evt.reason}
                  </div>

                  {(evt.before_state || evt.after_state) && (
                    <div style={{ display: 'grid', gridTemplateColumns: evt.before_state && evt.after_state ? '1fr 1fr' : '1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
                      {evt.before_state && (
                        <div>
                          <div className="subtext">Before State:</div>
                          <div className="json-block">
                            <pre>{JSON.stringify(evt.before_state, null, 2)}</pre>
                          </div>
                        </div>
                      )}
                      {evt.after_state && (
                        <div>
                          <div className="subtext">After State:</div>
                          <div className="json-block">
                            <pre>{JSON.stringify(evt.after_state, null, 2)}</pre>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <PaginationControls
          total={total}
          limit={limit}
          offset={offset}
          onPageChange={(newOffset) => setOffset(newOffset)}
        />
      </div>
    </div>
  );
};
