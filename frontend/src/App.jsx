import { Navigate, Route, Routes } from "react-router-dom";
import { AnalysisProvider } from "./lib/AnalysisContext.jsx";
import { Sidebar, Topbar } from "./components/Shell.jsx";
import HomePage from "./pages/Home.jsx";
import DatabasePage from "./pages/Database.jsx";
import OverviewPage from "./pages/Overview.jsx";
import ClaimsPage from "./pages/Claims.jsx";
import AddressPage from "./pages/Address.jsx";
import ProvenancePage from "./pages/Provenance.jsx";
import ConflictsPage from "./pages/Conflicts.jsx";
import TrustPage from "./pages/Trust.jsx";
import ExportPage from "./pages/Export.jsx";
import PaperPage from "./pages/Paper.jsx";
import MethodologyPage from "./pages/Methodology.jsx";
import SourcesPage from "./pages/Sources.jsx";
import AnalysesPage from "./pages/Analyses.jsx";

export default function App() {
  return (
    <AnalysisProvider>
      <div className="app">
        <Sidebar />
        <div className="main-col">
          <Topbar />
          <main className="page">
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/database" element={<DatabasePage />} />
              <Route path="/overview" element={<OverviewPage />} />
              <Route path="/claims" element={<ClaimsPage />} />
              <Route path="/address" element={<AddressPage />} />
              <Route path="/provenance" element={<ProvenancePage />} />
              <Route path="/conflicts" element={<ConflictsPage />} />
              <Route path="/trust" element={<TrustPage />} />
              <Route path="/drift" element={<Navigate to="/trust" replace />} />
              <Route path="/export" element={<ExportPage />} />
              <Route path="/paper" element={<PaperPage />} />
              <Route path="/methodology" element={<MethodologyPage />} />
              <Route path="/sources" element={<SourcesPage />} />
              <Route path="/analyses" element={<AnalysesPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </AnalysisProvider>
  );
}
