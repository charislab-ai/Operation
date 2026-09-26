import { useEffect, useState } from "react";
import { GoogleLogin, CredentialResponse } from "@react-oauth/google";
import Sidebar, { ViewKey } from "./components/Sidebar";
import DirectiveBar from "./components/DirectiveBar";
import DashboardView from "./views/Dashboard/DashboardView";
import WorkOrdersView from "./views/WorkOrders/WorkOrdersView";
import LibraryView from "./views/Library/LibraryView";
import EmployeesView from "./views/Employees/EmployeesView";
import AppManagementView from "./views/AppManagement/AppManagementView";
import MarketingBenchmarksView from "./views/MarketingBenchmarks/MarketingBenchmarksView";
import { getCurrentUser, loginWithGoogle, setSessionToken } from "./lib/api";

export default function App() {
  const [user, setUser] = useState<{ email: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<ViewKey>("dashboard");
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    getCurrentUser()
      .then((me) => setUser({ email: me.email }))
      .catch(() => setSessionToken(null))
      .finally(() => setRestoring(false));
  }, []);

  if (restoring) {
    return <div className="flex h-screen items-center justify-center bg-slate-950" />;
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="flex flex-col items-center gap-4 rounded-xl border border-slate-800 p-10">
          <div className="text-xl font-bold text-brand-purple">CharisLab AI OS</div>
          <GoogleLogin
            onSuccess={async (res: CredentialResponse) => {
              if (!res.credential) return;
              try {
                const loggedIn = await loginWithGoogle(res.credential);
                setSessionToken(loggedIn.token);
                setUser({ email: loggedIn.email });
                setError(null);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
            onError={() => setError("Google 로그인 실패")}
          />
          {error && <div className="text-sm text-red-400">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-900">
      <Sidebar active={active} onChange={setActive} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <DirectiveBar />
        <main className="flex-1 overflow-auto">
          {active === "dashboard" && <DashboardView onNavigate={setActive} />}
          {active === "workOrders" && <WorkOrdersView />}
          {active === "library" && <LibraryView />}
          {active === "employees" && <EmployeesView />}
          {active === "appManagement" && <AppManagementView />}
          {active === "marketingBenchmarks" && <MarketingBenchmarksView />}
        </main>
      </div>
    </div>
  );
}
