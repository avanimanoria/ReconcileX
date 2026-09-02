import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { BatchResponse } from '../api/types';
import { AlertBanner } from '../components/AlertBanner';

const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

export const BatchUploadPage: React.FC = () => {
  const navigate = useNavigate();
  const [batchNumber, setBatchNumber] = useState<string>('');
  const [paymentsFile, setPaymentsFile] = useState<File | null>(null);
  const [settlementsFile, setSettlementsFile] = useState<File | null>(null);
  const [bankCreditsFile, setBankCreditsFile] = useState<File | null>(null);
  const [refundsFile, setRefundsFile] = useState<File | null>(null);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [conflictResult, setConflictResult] = useState<{
    message: string;
    batch?: BatchResponse;
  } | null>(null);

  const validateFile = (file: File | null, label: string): string | null => {
    if (!file) {
      return `${label} must be selected.`;
    }
    if (!file.name.toLowerCase().endsWith('.csv')) {
      return `${label} must be a CSV file with .csv extension (selected '${file.name}').`;
    }
    if (file.size === 0) {
      return `${label} cannot be empty (0 bytes).`;
    }
    if (file.size > MAX_SIZE_BYTES) {
      return `${label} exceeds maximum allowed size of 10 MB.`;
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setConflictResult(null);

    // Validate 4 files
    const pErr = validateFile(paymentsFile, 'Payments CSV file');
    if (pErr) { setError(pErr); return; }
    const sErr = validateFile(settlementsFile, 'Settlements CSV file');
    if (sErr) { setError(sErr); return; }
    const bErr = validateFile(bankCreditsFile, 'Bank Credits CSV file');
    if (bErr) { setError(bErr); return; }
    const rErr = validateFile(refundsFile, 'Refunds CSV file');
    if (rErr) { setError(rErr); return; }

    const formData = new FormData();
    formData.append('payments_file', paymentsFile!);
    formData.append('settlements_file', settlementsFile!);
    formData.append('bank_credits_file', bankCreditsFile!);
    formData.append('refunds_file', refundsFile!);
    if (batchNumber.trim()) {
      formData.append('batch_number', batchNumber.trim());
    }

    setLoading(true);

    try {
      const result = await api.uploadBatch(formData);
      if (result.disposition === 'ALREADY_COMPLETED') {
        setConflictResult({
          message: 'A batch with this exact content hash was previously completed.',
          batch: result,
        });
      } else {
        navigate(`/batches/${result.id}`);
      }
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.status === 409 && typeof err.detail === 'object' && err.detail?.batch) {
          setConflictResult({
            message: err.detail.message || 'A batch with this exact content hash previously failed.',
            batch: err.detail.batch,
          });
        } else {
          setError(err.message);
        }
      } else {
        setError('Failed to upload batch CSV files.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Upload Reconciliation CSV Batch</h1>
          <p className="subtext">Upload payments, settlements, bank credits, and refunds CSV files</p>
        </div>
        <Link to="/batches" className="btn btn-outline">
          &larr; Back to Batches
        </Link>
      </div>

      {error && <AlertBanner type="danger">{error}</AlertBanner>}

      {conflictResult && (
        <AlertBanner
          type={conflictResult.batch?.status === 'FAILED' ? 'danger' : 'info'}
          title={conflictResult.batch?.status === 'FAILED' ? 'Batch Processing Conflict (Previously Failed)' : 'Duplicate Batch Ingested'}
        >
          <p>{conflictResult.message}</p>
          {conflictResult.batch && (
            <div style={{ marginTop: '0.75rem' }}>
              <Link to={`/batches/${conflictResult.batch.id}`} className="btn btn-primary">
                View Historical Batch ({conflictResult.batch.batch_number || conflictResult.batch.id})
              </Link>
            </div>
          )}
        </AlertBanner>
      )}

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="batch_number">Batch Number (Optional)</label>
            <input
              id="batch_number"
              type="text"
              placeholder="e.g. BATCH-2026-09-02"
              value={batchNumber}
              onChange={(e) => setBatchNumber(e.target.value)}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div className="form-group">
              <label htmlFor="payments_file">Payments CSV (payments_file) *</label>
              <input
                id="payments_file"
                type="file"
                accept=".csv"
                onChange={(e) => setPaymentsFile(e.target.files?.[0] || null)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="settlements_file">Settlements CSV (settlements_file) *</label>
              <input
                id="settlements_file"
                type="file"
                accept=".csv"
                onChange={(e) => setSettlementsFile(e.target.files?.[0] || null)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="bank_credits_file">Bank Credits CSV (bank_credits_file) *</label>
              <input
                id="bank_credits_file"
                type="file"
                accept=".csv"
                onChange={(e) => setBankCreditsFile(e.target.files?.[0] || null)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="refunds_file">Refunds CSV (refunds_file) *</label>
              <input
                id="refunds_file"
                type="file"
                accept=".csv"
                onChange={(e) => setRefundsFile(e.target.files?.[0] || null)}
              />
            </div>
          </div>

          <div style={{ marginTop: '1.25rem', display: 'flex', gap: '1rem' }}>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Processing Batch...' : 'Submit & Reconcile Batch'}
            </button>
            <Link to="/batches" className="btn btn-outline">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};
