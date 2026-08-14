import { useAuth } from "../contexts/AuthContext";

export default function OrganisationSwitcher() {
  const { organisations, activeOrganisation, switchOrganisation } = useAuth();

  if (!organisations || organisations.length <= 1) {
    return <span className="organisation-name">{activeOrganisation?.organisationName}</span>;
  }

  return (
    <select
      className="organisation-select form-select form-select-sm w-auto"
      aria-label="Active organisation"
      value={activeOrganisation?.organisationId || ""}
      onChange={(e) => switchOrganisation(e.target.value)}
    >
      {organisations.map((org) => (
        <option key={org.organisationId} value={org.organisationId}>
          {org.organisationName}
        </option>
      ))}
    </select>
  );
}
