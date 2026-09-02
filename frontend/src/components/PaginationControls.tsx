import React from 'react';

interface PaginationControlsProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
}

export const PaginationControls: React.FC<PaginationControlsProps> = ({
  total,
  limit,
  offset,
  onPageChange,
}) => {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  const handlePrev = () => {
    if (offset > 0) {
      onPageChange(Math.max(0, offset - limit));
    }
  };

  const handleNext = () => {
    if (offset + limit < total) {
      onPageChange(offset + limit);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
      <div className="subtext">
        Showing {total === 0 ? 0 : offset + 1} to {Math.min(offset + limit, total)} of {total} items
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <button className="btn btn-outline" onClick={handlePrev} disabled={offset === 0}>
          Previous
        </button>
        <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>
          Page {currentPage} of {totalPages}
        </span>
        <button className="btn btn-outline" onClick={handleNext} disabled={offset + limit >= total}>
          Next
        </button>
      </div>
    </div>
  );
};
