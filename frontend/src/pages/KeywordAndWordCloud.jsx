import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { analysisApi } from "../services/analysisApi";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import EmptyState from "../components/EmptyState";
import DataTable from "../components/DataTable";
import AnalysisFilters from "../components/AnalysisFilters";
import FormInput from "../components/FormInput";

const SENTIMENT_COLOR = { positive: "#198754", negative: "#dc3545", neutral: "#6c757d", unanalysed: "#adb5bd" };

function WordCloud({ words }) {
  if (!words.length) return null;
  const max = Math.max(...words.map((w) => w.value));
  return (
    <div className="d-flex flex-wrap gap-2 align-items-center p-3">
      {words.map((w) => (
        <span
          key={w.text}
          style={{
            fontSize: `${12 + (w.value / max) * 32}px`,
            color: SENTIMENT_COLOR[w.sentiment] || "#333",
            fontWeight: 600,
          }}
          title={`${w.text}: ${w.value}`}
        >
          {w.text}
        </span>
      ))}
    </div>
  );
}

export default function KeywordAndWordCloud() {
  const { projectId } = useParams();
  const [keywords, setKeywords] = useState(null);
  const [cloud, setCloud] = useState(null);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({});
  const [search, setSearch] = useState("");
  const [topN, setTopN] = useState(50);

  const load = () => {
    const params = { ...filters, search: search || undefined, topN };
    Promise.all([
      analysisApi.getKeywords(projectId, params),
      analysisApi.getWordCloud(projectId, { ...filters, topN }),
    ])
      .then(([k, c]) => {
        setKeywords(k.data.data.items);
        setCloud(c.data.data.items);
      })
      .catch(setError);
  };
  useEffect(load, [projectId, filters, search, topN]);

  if (keywords === null && !error) return <LoadingSpinner />;

  return (
    <div>
      <h2 className="my-3">Keyword & Word Cloud</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <AnalysisFilters projectId={projectId} filters={filters} onChange={setFilters} />
      <div className="d-flex gap-2 mb-3" style={{ maxWidth: 400 }}>
        <FormInput placeholder="Search keyword..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="form-select" style={{ width: 120 }} value={topN} onChange={(e) => setTopN(e.target.value)}>
          {[20, 50, 100].map((n) => <option key={n} value={n}>Top {n}</option>)}
        </select>
      </div>

      {keywords.length === 0 ? (
        <EmptyState title="No keyword data" description="Upload and process reviews to see keywords." />
      ) : (
        <>
          <div className="card mb-3"><WordCloud words={cloud || []} /></div>
          <DataTable
            columns={[
              { key: "keyword", header: "Keyword" },
              { key: "frequency", header: "Frequency" },
              { key: "sentiment", header: "Sentiment" },
              { key: "positiveCount", header: "Positive" },
              { key: "negativeCount", header: "Negative" },
              { key: "neutralCount", header: "Neutral" },
            ]}
            rows={keywords}
            rowKey="keyword"
          />
        </>
      )}
    </div>
  );
}
