import { Outlet } from "react-router-dom";
import TopNavBar from "../components/TopNavBar";
import Sidebar from "../components/Sidebar";

export default function AppLayout() {
  return (
    <div className="app-shell d-flex flex-column vh-100">
      <TopNavBar />
      <div className="app-body d-flex flex-grow-1 overflow-hidden">
        <Sidebar />
        <main className="app-main flex-grow-1 overflow-auto">
          <div className="app-content">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
