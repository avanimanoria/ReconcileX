import React from 'react';

interface StatusBadgeProps {
  type: 'status' | 'priority' | 'match';
  value: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ type, value }) => {
  const badgeClass = `badge badge-${type}-${value.toUpperCase()}`;
  return <span className={badgeClass}>{value}</span>;
};
