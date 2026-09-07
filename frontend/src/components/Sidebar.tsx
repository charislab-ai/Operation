export type ViewKey = "metaverse" | "calendar" | "dashboard";

const items: { key: ViewKey; label: string }[] = [
  { key: "metaverse", label: "Metaverse" },
  { key: "calendar", label: "Calendar" },
  { key: "dashboard", label: "Dashboard" },
];

export default function Sidebar({
  active,
  onChange,
}: {
  active: ViewKey;
  onChange: (key: ViewKey) => void;
}) {
  return (
    <nav className="flex w-48 flex-col gap-1 border-r border-slate-800 bg-slate-950 p-4">
      <div className="mb-4 text-lg font-bold text-brand-purple">CharisLab AI OS</div>
      {items.map((item) => (
        <button
          key={item.key}
          onClick={() => onChange(item.key)}
          className={`rounded-md px-3 py-2 text-left text-sm ${
            active === item.key
              ? "bg-brand-purple text-white"
              : "text-slate-300 hover:bg-slate-800"
          }`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
