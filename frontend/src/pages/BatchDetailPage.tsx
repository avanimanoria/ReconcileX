import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { BatchResponse, ExceptionResponse, ReconcileResultResponse } from '../api/types';
import { AlertBanner } from '../components/AlertBanner';
import { PaginationControls } from '../components/PaginationControls';
import { StatusBadge } from '../components/StatusBadge';

export const BatchDetailPage: React.FC = () => {
  const { batchId } = useParams<{ batchId: string }>();
  const [batch, setBatch] = useState<BatchResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'results' | 'exceptions'>('results');

  // Results state
  const [results, setResults] = useState<ReconcileResultResponse[]>([]);
  const [resultsTotal, setResultsTotal] = useState<number>(0);
  const [matchStatusFilter, setMatchStatusFilter] = useState<string>('');
  const [resultsOffset, setResultsOffset] = useState<number>(0);

  // Exceptions state
  const [exceptions, setExceptions] = useState<ExceptionResponse[]>([]);
  const [exceptionsTotal, setExceptionsTotal] = useState<number>(0);
  const [excStatusFilter, setExcStatusFilter] = useState<string>('');
  const [excPriorityFilter, setExcPriorityFilter] = useState<string>('');
  const [excCategoryFilter, setExcCategoryFilter] = useState<string>('');
  const [excOffset, setExcOffset] = useState<number>(0);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const limit = 10;

  useEffect(() => {
    if (!batchId) return;
    const fetchBatchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const b = await api.getBatch(batchId);
        setBatch(b);
      } catch (err: any) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError('Failed to fetch batch details.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchBatchDetail();
  }, [batchId]);

  useEffect(() => {
    if (!batchId) return;
    if (activeTab === 'results') {
      const fetchResults = async () => {
        try {
          const res = await api.listBatchResults(batchId, {
            match_status: matchStatusFilter || undefined,
            limit,
            offset: resultsOffset,
          });
          setResults(res.items);
          setResultsTotal(res.total);
        } catch (err: any) {
          setError(err.message || 'Failed to fetch batch results.');
        }
      };
      fetchResults();
    } else {
      const fetchExceptions = async () => {
        try {
          const res = await api.listBatchExceptions(batchId, {
            status: excStatusFilter || undefined,
            priority: excPriorityFilter || undefined,
            category: excCategoryFilter || undefined,
            limit,
            offset: excOffset,
          });
          setExceptions(res.items);
          setExceptionsTotal(res.total);
        } catch (err: any) {
          setError(err.message || 'Failed to fetch batch exceptions.');
        }
      };
      fetchExceptions();
    }
  }, [batchId, activeTab, matchStatusFilter, resultsOffset, excStatusFilter, excPriorityFilter, excCategoryFilter, excOffset]);

  if (loading) {
    return <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading batch detail...</div>;
  }

  if (error || !batch) {
    return (
      <div>
        <AlertBanner type="danger">{error || 'Batch not found.'}</AlertBanner>
        <Link to="/batches" className="btn btn-outline">&larr; Back to Batches</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Batch #{batch.batch_number}</h1>
          <p className="subtext">Engine Version: {batch.engine_version} | ID: {batch.id}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link to={`/audit-events?batch_id=${batch.id}`} className="btn btn-outline">
            Audit Trail
          </Link>
          <Link to="/batches" className="btn btn-outline">
            &larr; Back to Batches
          </Link>
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <div className="subtext">Status</div>
            <StatusBadge type="status" value={batch.status} />
          </div>
          <div>
            <div className="subtext">Disposition</div>
            <div style={{ fontWeight: 600 }}>{batch.disposition || 'N/A'}</div>
          </div>
          <div>
            <div className="subtext">Auto Matches</div>
            <div style={{ fontWeight: 700, fontSize: '1.25rem', color: '#166534' }}>{batch.auto_match_count}</div>
          </div>
          <div>
            <div className="subtext">Exceptions</div>
            <div style={{ fontWeight: 700, fontSize: '1.25rem', color: '#991b1b' }}>{batch.exception_count}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem' }}>
          <div><span className="subtext">Payments:</span> <strong>{batch.total_payments}</strong></div>
          <div><span className="subtext">Settlements:</span> <strong>{batch.total_settlements}</strong></div>
          <div><span className="subtext">Bank Credits:</span> <strong>{batch.total_bank_credits}</strong></div>
          <div><span className="subtext">Refunds:</span> <strong>{batch.total_refunds}</strong></div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        <button
          className={`btn ${activeTab === 'results' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveTab('results')}
        >
          Reconciliation Results ({resultsTotal})
        </button>
        <button
          className={`btn ${activeTab === 'exceptions' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveTab('exceptions')}
        >
          Reconciliation Exceptions ({exceptionsTotal})
        </button>
      </div>

      {activeTab === 'results' ? (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ fontWeight: 600 }}>Results List</div>
            <div style={{ width: '200px' }}>
              <select
                value={matchStatusFilter}
                onChange={(e) => { setMatchStatusFilter(e.target.value); setResultsOffset(0); }}
              >
                <option value="">All Match Statuses</option>
                <option value="AUTO_MATCH">AUTO_MATCH</option>
                <option value="EXCEPTION">EXCEPTION</option>
              </select>
            </div>
          </div>

          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Payment ID</th>
                  <th>Settlement ID</th>
                  <th>Bank Txn ID</th>
                  <th>Refund ID</th>
                  <th>Match Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.payment_id || '-'}</td>
                    <td>{r.settlement_id || '-'}</td>
                    <td>{r.bank_txn_id || '-'}</td>
                    <td>{r.refund_id || '-'}</td>
                    <td><StatusBadge type="match" value={r.match_status} /></td>
                    <td style={{ maxWidth: '300px' }}>{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <PaginationControls
            total={resultsTotal}
            limit={limit}
            offset={resultsOffset}
            onPageChange={(newOffset) => setResultsOffset(newOffset)}
          />
        </div>
      ) : (
        <div className="card">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label>Status Filter</label>
              <select
                value={excStatusFilter}
                onChange={(e) => { setExcStatusFilter(e.target.value); setExcOffset(0); }}
              >
                <option value="">All Statuses</option>
                <option value="OPEN">OPEN</option>
                <option value="IN_REVIEW">IN_REVIEW</option>
                <option value="RESOLVED">RESOLVED</option>
                <option value="DISMISSED">DISMISSED</option>
              </select>
            </div>
            <div>
              <label>Priority Filter</label>
              <select
                value={excPriorityFilter}
                onChange={(e) => { setExcPriorityFilter(e.target.value); setExcOffset(0); }}
              >
                <option value="">All Priorities</option>
                <option value="CRITICAL">CRITICAL</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>
            <div>
              <label>Category Filter</label>
              <input
                type="text"
                placeholder="e.g. SETTLEMENT_DELAY"
                value={excCategoryFilter}
                onChange={(e) => { setExcCategoryFilter(e.target.value); setExcOffset(0); }}
              />
            </div>
          </div>

          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Assigned To</th>
                  <th>Payment / Settlement</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {exceptions.map((exc) => (
                  <tr key={exc.id}>
                    <td style={{ fontWeight: 600 }}>{exc.category}</td>
                    <td><StatusBadge type="priority" value={exc.priority} /></td>
                    <td><StatusBadge type="status" value={exc.status} /></td>
                    <td>{exc.assigned_to || 'Unassigned'}</td>
                    <td>
                      {exc.payment_id ? `PAY: ${exc.payment_id}` : ''}
                      {exc.settlement_id ? ` SET: ${exc.settlement_id}` : ''}
                    </td>
                    <td>
                      <Link to={`/exceptions/${exc.id}`} className="btn btn-primary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                        Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <PaginationControls
            total={exceptionsTotal}
            limit={limit}
            offset={excOffset}
            onPageChange={(newOffset) => setExcOffset(newOffset)}
          />
        </div>
      )}
    </div>
  );
};
