import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { BatchResponse } from '../api/types';
import { AlertBanner } from '../components/AlertBanner';
import { PaginationControls } from '../components/PaginationControls';
import { StatusBadge } from '../components/StatusBadge';

export const BatchListPage: React.FC = () => {
  const [batches, setBatches] = useState<BatchResponse[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [limit] = useState<number>(10);
  const [offset, setOffset] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBatches = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listBatches({
        status: statusFilter || undefined,
        limit,
        offset,
      });
      setBatches(res.items);
      setTotal(res.total);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to fetch batches from server.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBatches();
  }, [statusFilter, offset, limit]);

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
    setOffset(0);
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Reconciliation Batches</h1>
          <p className="subtext">Overview of ingested payment reconciliation batches</p>
        </div>
        <Link to="/batches/upload" className="btn btn-primary">
          + Upload New Batch
        </Link>
      </div>

      {error && <AlertBanner type="danger">{error}</AlertBanner>}

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
            Filter Batches (Total Registered: {total})
          </div>
          <div style={{ width: '220px' }}>
            <select value={statusFilter} onChange={handleStatusChange}>
              <option value="">All Statuses</option>
              <option value="CREATED">CREATED</option>
              <option value="INGESTING">INGESTING</option>
              <option value="PROCESSING">PROCESSING</option>
              <option value="COMPLETED">COMPLETED</option>
              <option value="FAILED">FAILED</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading batches...</div>
        ) : batches.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
            No reconciliation batches found for the selected filter.
          </div>
        ) : (
          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Batch Number</th>
                  <th>Status</th>
                  <th>Disposition</th>
                  <th>Payments</th>
                  <th>Settlements</th>
                  <th>Auto Matches</th>
                  <th>Exceptions</th>
                  <th>Created At</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <Link to={`/batches/${b.id}`} style={{ fontWeight: 600 }}>
                        {b.batch_number}
                      </Link>
                    </td>
                    <td>
                      <StatusBadge type="status" value={b.status} />
                    </td>
                    <td>{b.disposition || 'N/A'}</td>
                    <td>{b.total_payments}</td>
                    <td>{b.total_settlements}</td>
                    <td>{b.auto_match_count}</td>
                    <td>{b.exception_count}</td>
                    <td>{new Date(b.created_at).toLocaleString()}</td>
                    <td>
                      <Link to={`/batches/${b.id}`} className="btn btn-outline" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                        View Details
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <PaginationControls total={total} limit={limit} offset={offset} onPageChange={(newOffset) => setOffset(newOffset)} />
      </div>
    </div>
  );
};
