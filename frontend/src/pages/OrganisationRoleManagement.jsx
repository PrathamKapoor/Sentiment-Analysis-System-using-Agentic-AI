import { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { organisationApi } from "../services/organisationApi";
import { useToast } from "../contexts/ToastContext";
import DataTable from "../components/DataTable";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import FormInput from "../components/FormInput";

export default function OrganisationRoleManagement() {
  const { activeOrganisation } = useAuth();
  const { showToast } = useToast();
  const [organisation, setOrganisation] = useState(null);
  const [roles, setRoles] = useState(null);
  const [error, setError] = useState(null);
  const [orgName, setOrgName] = useState("");

  const orgId = activeOrganisation?.organisationId;

  const load = () => {
    if (!orgId) return;
    organisationApi.get(orgId).then((resp) => {
      setOrganisation(resp.data.data);
      setOrgName(resp.data.data.name);
    }).catch(setError);
    organisationApi.listRoles(orgId).then((resp) => setRoles(resp.data.data.items)).catch(setError);
  };

  useEffect(load, [orgId]);

  const onSaveName = async (e) => {
    e.preventDefault();
    try {
      await organisationApi.update(orgId, { name: orgName });
      showToast("Organisation updated");
      load();
    } catch (err) {
      setError(err);
    }
  };

  if (!organisation || roles === null) return <LoadingSpinner />;

  return (
    <div>
      <h2>Organisation & Roles</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <form onSubmit={onSaveName} className="card p-3 mb-4" style={{ maxWidth: 480 }}>
        <FormInput
          label="Organisation name"
          value={orgName}
          onChange={(e) => setOrgName(e.target.value)}
        />
        <button className="btn btn-primary" type="submit">Save</button>
      </form>

      <h5>Roles</h5>
      <DataTable
        columns={[
          { key: "name", header: "Name", render: (r) => (r.isCustom ? r.name : <strong>{r.name}</strong>) },
          { key: "type", header: "Type", render: (r) => (r.isCustom ? "Custom" : "Built-in") },
          { key: "permissions", header: "Permissions", render: (r) => (r.permissions || []).join(", ") },
        ]}
        rows={roles}
      />
    </div>
  );
}
