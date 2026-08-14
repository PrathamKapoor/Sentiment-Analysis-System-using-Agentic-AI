import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import OrganisationSwitcher from "./OrganisationSwitcher";
import { useTheme } from "../contexts/ThemeContext";

function ThemeIcon({ dark }) {
  return dark ? (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4M16.5 12a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15.2A8 8 0 0 1 8.8 4 8.1 8.1 0 1 0 20 15.2Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>
  );
}

export default function TopNavBar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <nav className="app-topbar navbar px-3">
      <Link className="navbar-brand app-brand" to="/dashboard" aria-label="Sentiment Intelligence dashboard">
        <span className="app-brand-mark" aria-hidden="true">S</span>
        <span><strong>Sentiment</strong><small>Intelligence</small></span>
      </Link>
      <div className="topbar-actions d-flex align-items-center">
        <OrganisationSwitcher />
        <button className="theme-toggle" type="button" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
          <ThemeIcon dark={theme === "dark"} />
        </button>
        <span className="topbar-user">{user?.name}</span>
        <button className="btn btn-sm topbar-logout" onClick={logout}>
          Logout
        </button>
      </div>
    </nav>
  );
}
