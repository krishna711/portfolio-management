export default function Card({ title, value, sub, valueClassName }: { title: string; value: string; sub?: string; valueClassName?: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-5">
      <div className="text-sm text-gray-500 dark:text-gray-400">{title}</div>
      <div className={`text-2xl font-semibold mt-2 ${valueClassName || ''}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{sub}</div>}
    </div>
  )
}
