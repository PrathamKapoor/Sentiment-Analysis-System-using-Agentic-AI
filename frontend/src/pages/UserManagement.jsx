import { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { organisationApi } from "../services/organisationApi";
import { useToast } from "../contexts/ToastContext";
import DataTable from "../components/DataTable";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorAlert from "../components/ErrorAlert";
import FormInput from "../components/FormInput";

export default function UserManagement() {
  const { activeOrganisation } = useAuth();
  const { showToast } = useToast();
  const [members, setMembers] = useState(null);
  const [error, setError] = useState(null);
  const [inviteEmail, setInviteEmail] = useState("");

  const orgId = activeOrganisation?.organisationId;

  const load = () => {
    if (!orgId) return;
    organisationApi
      .listUsers(orgId)
      .then((resp) => setMembers(resp.data.data.items))
      .catch(setError);
  };

  useEffect(load, [orgId]);

  const onInvite = async (e) => {
    e.preventDefault();
    try {
      await organisationApi.inviteUser(orgId, { email: inviteEmail });
      showToast("Invitation created");
      setInviteEmail("");
      load();
    } catch (err) {
      setError(err);
    }
  };

  if (members === null && !error) return <LoadingSpinner />;

  return (
    <div>
      <h2>Users</h2>
      <ErrorAlert error={error} onDismiss={() => setError(null)} />

      <form onSubmit={onInvite} className="d-flex gap-2 mb-3" style={{ maxWidth: 420 }}>
        <FormInput
          type="email"
          placeholder="email@company.com"
          required
          value={inviteEmail}
          onChange={(e) => setInviteEmail(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" style={{ height: 38 }}>
          Invite
        </button>
      </form>

      <DataTable
        columns={[
          { key: "name", header: "Name", render: (m) => m.user?.name },
          { key: "email", header: "Email", render: (m) => m.user?.email },
          { key: "status", header: "Status" },
          { key: "roles", header: "Roles", render: (m) => (m.roles || []).join(", ") || "—" },
        ]}
        rows={members}
        emptyMessage="No members yet — invite one above"
      />
    </div>
  );
}
