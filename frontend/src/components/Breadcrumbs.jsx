import { Link } from "react-router-dom";

export default function Breadcrumbs({ items }) {
  return (
    <nav aria-label="breadcrumb">
      <ol className="breadcrumb mb-0">
        {items.map((item, idx) => (
          <li
            key={idx}
            className={`breadcrumb-item ${idx === items.length - 1 ? "active" : ""}`}
          >
            {item.to && idx !== items.length - 1 ? (
              <Link to={item.to}>{item.label}</Link>
            ) : (
              item.label
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
