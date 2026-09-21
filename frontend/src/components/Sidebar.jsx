import { NavLink } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", roles: null },
  { to: "/projects", label: "Projects", roles: ["Organisation Owner", "Organisation Administrator", "Project Manager"] },
  { to: "/comparison", label: "Compare Projects", roles: null },
  { to: "/evaluation", label: "Model Quality", roles: null },
  { to: "/admin/users", label: "Users", roles: ["Organisation Owner", "Organisation Administrator"] },
  { to: "/admin/organisation", label: "Organisation & Roles", roles: ["Organisation Owner", "Organisation Administrator"] },
];

export default function Sidebar() {
  const { hasRole } = useAuth();

  return (
    <aside className="app-sidebar">
      <span className="sidebar-label">Navigation</span>
      <nav className="nav flex-column" aria-label="Primary navigation">
        {NAV_ITEMS.filter((item) => !item.roles || item.roles.some(hasRole)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `sidebar-link nav-link ${isActive ? "is-active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
