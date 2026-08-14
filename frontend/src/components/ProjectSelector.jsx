import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { projectApi } from "../services/projectApi";

export default function ProjectSelector({ currentProjectId }) {
  const [projects, setProjects] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    projectApi
      .list()
      .then((resp) => setProjects(resp.data.data.items))
      .catch(() => setProjects([]));
  }, []);

  if (projects.length === 0) return null;

  return (
    <select
      className="form-select form-select-sm w-auto me-3"
      value={currentProjectId || ""}
      onChange={(e) => e.target.value && navigate(`/projects/${e.target.value}`)}
    >
      <option value="" disabled>
        Select a project
      </option>
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}
