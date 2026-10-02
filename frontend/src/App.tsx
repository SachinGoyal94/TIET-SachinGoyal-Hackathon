import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import RiskEngine from "./pages/RiskEngine";
import Rebalancer from "./pages/Rebalancer";
import StressTesting from "./pages/StressTesting";
import Architecture from "./pages/Architecture";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/risk-engine" element={<RiskEngine />} />
        <Route path="/rebalancer" element={<Rebalancer />} />
        <Route path="/stress-testing" element={<StressTesting />} />
        <Route path="/architecture" element={<Architecture />} />
      </Routes>
    </Layout>
  );
}
