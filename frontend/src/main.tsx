import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { api, type Meta } from "./api";
import { Layout } from "./components/Layout";
import { ErrorBox, MetaContext, useAsync } from "./components/ui";
import { Dashboard } from "./pages/Dashboard";
import { HoldingDetail } from "./pages/HoldingDetail";
import { Import } from "./pages/Import";
import { Accounts, Assets, Transactions } from "./pages/Records";
import { Status } from "./pages/Status";
import "./styles.css";

function App() {
  const meta = useAsync(() => api.get<Meta>("/api/meta"), []);
  if (meta.error) {
    return (
      <main>
        <ErrorBox error={`Can't reach the backend (${meta.error}). Is it running? See README.`} />
      </main>
    );
  }
  if (!meta.data) return null;
  return (
    <MetaContext.Provider value={meta.data}>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/assets/:id" element={<HoldingDetail />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/accounts" element={<Accounts />} />
          <Route path="/assets" element={<Assets />} />
          <Route path="/import" element={<Import />} />
          <Route path="/status" element={<Status />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </Layout>
    </MetaContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
