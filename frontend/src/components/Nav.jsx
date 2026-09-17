import { Link, useLocation } from "react-router-dom";

const LINKS = [
  { href: "/", label: "Upload" },
  { href: "/audit", label: "Corpus Audit" },
  { href: "/address", label: "Address Inspector" },
  { href: "/provenance", label: "Provenance Explorer" },
  { href: "/drift", label: "Trust-Rule Sensitivity" },
  { href: "/sources", label: "Sources" },
  { href: "/export", label: "Export" },
];

export default function Nav() {
  const { pathname } = useLocation();
  return (
    <div className="topnav">
      <div className="shell">
        <div className="brand">
          THEMIS
          <small>Attribution Reliability Auditor</small>
        </div>
        <nav className="navlinks">
          {LINKS.map((l) => (
            <Link key={l.href} to={l.href} className={pathname === l.href ? "active" : ""}>
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
