import { NavLink } from "react-router-dom";

interface Tab {
  to: string;
  label: string;
  hint: string;
}

const TABS: Tab[] = [
  { to: "/dashboard", label: "Queue", hint: "g q" },
  { to: "/floor", label: "Floor map", hint: "g f" },
  { to: "/analytics", label: "Analytics", hint: "g a" },
  { to: "/handoff", label: "Handoff", hint: "g h" },
];

export function NavTabs() {
  return (
    <div className="nav-tabs">
      {TABS.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          className={({ isActive }) => `nav-tab ${isActive ? "active" : ""}`}
        >
          <span className="label">{t.label}</span>
          <span className="hint mono">{t.hint}</span>
        </NavLink>
      ))}
    </div>
  );
}
