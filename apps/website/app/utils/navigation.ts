export interface NavLink {
  href: string;
  label: string;
}

export const NAV_LINKS: NavLink[] = [
  { href: "#product", label: "Démo" },
  { href: "#features", label: "Fonctionnalités" },
  { href: "#states", label: "États" },
  { href: "#architecture", label: "Architecture" },
];

export const FOOTER_LINKS: NavLink[] = NAV_LINKS.filter(
  (link) => link.href !== "#states",
);