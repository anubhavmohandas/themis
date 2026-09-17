import { Routes, Route } from "react-router-dom";
import Nav from "./components/Nav.jsx";
import UploadPage from "./pages/Upload.jsx";
import AuditPage from "./pages/Audit.jsx";
import AddressInspectorPage from "./pages/Address.jsx";
import ProvenanceExplorerPage from "./pages/Provenance.jsx";
import DriftPage from "./pages/Drift.jsx";
import SourcesPage from "./pages/Sources.jsx";
import ExportPage from "./pages/Export.jsx";

export default function App() {
  return (
    <>
      <Nav />
      <main className="shell">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/address" element={<AddressInspectorPage />} />
          <Route path="/provenance" element={<ProvenanceExplorerPage />} />
          <Route path="/drift" element={<DriftPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/export" element={<ExportPage />} />
        </Routes>
      </main>
    </>
  );
}
