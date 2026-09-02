import React from 'react';

interface AlertBannerProps {
  type?: 'info' | 'warning' | 'danger';
  title?: string;
  children: React.ReactNode;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ type = 'info', title, children }) => {
  return (
    <div className={`alert alert-${type}`}>
      {title && <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>{title}</div>}
      <div>{children}</div>
    </div>
  );
};
