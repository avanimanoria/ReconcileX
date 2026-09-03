import React from 'react';
import { NavLink, Link } from 'react-router-dom';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div>
      <header className="app-header">
        <div className="app-brand">
          <Link to="/batches" style={{ color: 'white', textDecoration: 'none' }}>
            ReconcileX Dashboard
          </Link>
        </div>
        <nav className="app-nav">
          <NavLink to="/batches" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Batches
          </NavLink>
          <NavLink to="/batches/upload" className={({ isActive }) => (isActive ? 'active' : '')}>
            Upload CSVs
          </NavLink>
          <NavLink to="/audit-events" className={({ isActive }) => (isActive ? 'active' : '')}>
            Audit Timeline
          </NavLink>
          <NavLink to="/metrics" className={({ isActive }) => (isActive ? 'active' : '')}>
            Evaluation Metrics
          </NavLink>
        </nav>

      </header>
      <main className="container">{children}</main>
    </div>
  );
};
