import { Outlet } from "react-router-dom";
import { FeatureSubNav, MockDataNotice, PrimaryNavbar } from "@/components/layout";
import { ToastProvider } from "@/components/toast";

/** AuthenticatedLayout: top bar, feature tabs, then the page. */
export function Shell() {
  return (
    <ToastProvider>
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-30">
          <PrimaryNavbar />
          <FeatureSubNav />
        </header>
        <MockDataNotice />
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </ToastProvider>
  );
}
