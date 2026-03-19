import { DashboardShell } from "../components/dashboard-shell";
import { fetchDashboardData } from "../lib/api";

export default async function Home() {
  const data = await fetchDashboardData();
  return <DashboardShell data={data} />;
}
