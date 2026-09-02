import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { BatchUploadPage } from '../pages/BatchUploadPage';
import { api, ApiError } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    uploadBatch: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    detail: any;
    constructor(status: number, detail: any) {
      super(detail?.message || 'Error');
      this.status = status;
      this.detail = detail;
    }
  },
}));

describe('BatchUploadPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('client validation requires all four CSV inputs and rejects invalid extension before request', async () => {
    render(
      <BrowserRouter>
        <BatchUploadPage />
      </BrowserRouter>
    );

    const submitBtn = screen.getByRole('button', { name: /Submit & Reconcile Batch/i });

    // Submit with missing files
    fireEvent.click(submitBtn);
    expect(screen.getByText(/Payments CSV file must be selected/i)).toBeInTheDocument();
    expect(api.uploadBatch).not.toHaveBeenCalled();

    // Select invalid extension for payments
    const invalidFile = new File(['dummy content'], 'payments.txt', { type: 'text/plain' });
    fireEvent.change(screen.getByLabelText(/Payments CSV/i), { target: { files: [invalidFile] } });

    fireEvent.click(submitBtn);
    expect(screen.getByText(/must be a CSV file with \.csv extension/i)).toBeInTheDocument();
    expect(api.uploadBatch).not.toHaveBeenCalled();
  });

  it('client validation rejects empty (0 bytes) CSV files before request', async () => {
    render(
      <BrowserRouter>
        <BatchUploadPage />
      </BrowserRouter>
    );

    const emptyFile = new File([], 'payments.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText(/Payments CSV/i), { target: { files: [emptyFile] } });

    const submitBtn = screen.getByRole('button', { name: /Submit & Reconcile Batch/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/cannot be empty \(0 bytes\)/i)).toBeInTheDocument();
    expect(api.uploadBatch).not.toHaveBeenCalled();
  });

  it('HTTP 409 PREVIOUSLY_FAILED shows warning, no success state, a link to the historical batch, and no automatic retry POST', async () => {
    const historicalBatchId = 'historical-failed-batch-123';
    (api.uploadBatch as any).mockRejectedValue(
      new ApiError(409, {
        message: 'A batch with this exact content hash previously failed and cannot be reprocessed.',
        batch: {
          id: historicalBatchId,
          batch_number: 'BATCH-FAILED-001',
          status: 'FAILED',
          disposition: 'PREVIOUSLY_FAILED',
        },
      })
    );

    render(
      <BrowserRouter>
        <BatchUploadPage />
      </BrowserRouter>
    );

    const file1 = new File(['data'], 'payments.csv', { type: 'text/csv' });
    const file2 = new File(['data'], 'settlements.csv', { type: 'text/csv' });
    const file3 = new File(['data'], 'bank_credits.csv', { type: 'text/csv' });
    const file4 = new File(['data'], 'refunds.csv', { type: 'text/csv' });

    fireEvent.change(screen.getByLabelText(/Payments CSV/i), { target: { files: [file1] } });
    fireEvent.change(screen.getByLabelText(/Settlements CSV/i), { target: { files: [file2] } });
    fireEvent.change(screen.getByLabelText(/Bank Credits CSV/i), { target: { files: [file3] } });
    fireEvent.change(screen.getByLabelText(/Refunds CSV/i), { target: { files: [file4] } });

    const submitBtn = screen.getByRole('button', { name: /Submit & Reconcile Batch/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      // 1. Assert conflict warning is displayed
      expect(screen.getByText(/Batch Processing Conflict \(Previously Failed\)/i)).toBeInTheDocument();
      expect(screen.getByText(/A batch with this exact content hash previously failed and cannot be reprocessed\./i)).toBeInTheDocument();

      // 2. Assert no success state
      expect(screen.queryByText(/Batch processed successfully/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Processing Batch\.\.\./i)).not.toBeInTheDocument();

      // 3. Assert renders link to historical batch
      const link = screen.getByRole('link', { name: /View Historical Batch/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', `/batches/${historicalBatchId}`);

      // 4. Assert no automatic retry POST
      expect(api.uploadBatch).toHaveBeenCalledTimes(1);
    });
  });
});
