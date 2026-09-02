import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { BatchListPage } from './pages/BatchListPage';
import { BatchUploadPage } from './pages/BatchUploadPage';
import { BatchDetailPage } from './pages/BatchDetailPage';
import { ExceptionDetailPage } from './pages/ExceptionDetailPage';
import { AuditTimelinePage } from './pages/AuditTimelinePage';

export const App: React.FC = () => {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/batches" replace />} />
          <Route path="/batches" element={<BatchListPage />} />
          <Route path="/batches/upload" element={<BatchUploadPage />} />
          <Route path="/batches/:batchId" element={<BatchDetailPage />} />
          <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
          <Route path="/audit-events" element={<AuditTimelinePage />} />
        </Routes>
      </Layout>
    </Router>
  );
};

export default App;
