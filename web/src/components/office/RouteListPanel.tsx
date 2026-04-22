// web/src/components/office/RouteListPanel.tsx

import type { Route } from "@/lib/api";

interface RouteListPanelProps {
  routes: Route[];
}

function formatFeet(ft: number): string {
  if (ft >= 5280) {
    return (ft / 5280).toFixed(2) + " mi";
  }
  return ft.toLocaleString("en-US", { maximumFractionDigits: 1 }) + " ft";
}

export default function RouteListPanel({ routes }: RouteListPanelProps) {
  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          Routes
          <span className="ml-2 text-gray-400 font-normal text-sm">
            ({routes.length})
          </span>
        </h2>
      </div>

      {routes.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 py-10 text-center text-sm text-gray-400">
          No routes assigned to this job.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Route Name
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Length
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Segments
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {routes.map((route) => (
                <tr key={route.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-800">
                    {route.route_name}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 tabular-nums">
                    {formatFeet(route.length_ft)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-600 tabular-nums">
                    {route.segment_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
