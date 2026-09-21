import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Shell } from "@/components/Shell";
import { OverviewPage } from "@/pages/OverviewPage";
import { InsightsPage } from "@/pages/InsightsPage";
import { InsightDetailPage } from "@/pages/InsightDetailPage";
import { ReportPage } from "@/pages/ReportPage";
import { AskPage } from "@/pages/AskPage";
import { SourcesPage } from "@/pages/SourcesPage";
import { EvaluationPage } from "@/pages/EvaluationPage";
import "./index.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "insights", element: <InsightsPage /> },
      { path: "insights/:id", element: <InsightDetailPage /> },
      { path: "report", element: <ReportPage /> },
      { path: "ask", element: <AskPage /> },
      { path: "sources", element: <SourcesPage /> },
      { path: "evaluation", element: <EvaluationPage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
